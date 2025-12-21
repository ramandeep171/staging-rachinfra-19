from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import SavepointCase


class TestRetryLogic(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = cls.env["llm.mcp.server"].create(
            {"name": "Local", "transport_types": "local_agent"}
        )
        cls.command_runner = cls.env["llm.mcp.command.runner"].create(
            {
                "name": "Local Runner",
                "server_id": cls.server.id,
                "type": "local_agent",
                "entrypoint": "noop",
            }
        )

        cls.tool_runner = cls.env["llm.tool.runner"].create(
            {"name": "Local tool runner", "runner_type": "local"}
        )

        cls.tool_definition = cls.env["llm.tool.definition"].create(
            {
                "name": "retry_demo_tool",
                "action_type": "external_api",
                "description": "Route payloads via MCP",
                "schema_json": {
                    "type": "object",
                    "properties": {"echo": {"type": "string"}},
                },
            }
        )

        cls.binding = cls.env["llm.tool.binding"].create(
            {
                "name": "Retry Binding",
                "tool_id": cls.tool_definition.id,
                "runner_id": cls.tool_runner.id,
                "executor_path": "/bin/echo",
                "timeout": 20,
                "max_retries": 1,
                "retry_interval": 0,
                "retry_strategy": "fixed",
            }
        )

        cls.router = cls.env["llm.mcp.execution.router"]

    def test_retry_recovers_after_failure(self):
        with patch.object(
            self.command_runner, "_execute_payload", side_effect=[UserError("boom"), {}]
        ) as exec_mock:
            result = self.router.route(
                session_id="sess-retry", tool_key=self.tool_definition.name, params={}
            )

        self.assertEqual(result, {})
        self.assertEqual(exec_mock.call_count, 2)
        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1)
        retry_events = invocation.audit_trail_ids.filtered(lambda e: e.event_type == "retry")
        self.assertEqual(len(retry_events), 1)
        self.assertEqual(invocation.status, "success")

    def test_retry_exhaustion_raises(self):
        self.binding.write({"max_retries": 1, "retry_interval": 0})
        with patch.object(
            self.command_runner, "_execute_payload", side_effect=UserError("fail")
        ):
            with self.assertRaises(UserError):
                self.router.route(
                    session_id="sess-fail", tool_key=self.tool_definition.name, params={}
                )

        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1)
        exhausted_events = invocation.audit_trail_ids.filtered(
            lambda e: e.event_type == "retry_exhausted"
        )
        self.assertTrue(exhausted_events)
        self.assertEqual(invocation.status, "failed")

    def test_exponential_strategy_computes_delays(self):
        self.binding.write(
            {"max_retries": 2, "retry_interval": 2, "retry_strategy": "exponential"}
        )
        manager = self.env["llm.mcp.retry.manager"]

        with patch.object(type(manager), "_sleep") as sleep_mock, patch.object(
            self.command_runner,
            "_execute_payload",
            side_effect=[UserError("first"), UserError("second"), {}],
        ) as exec_mock:
            result = self.router.route(
                session_id="sess-exp", tool_key=self.tool_definition.name, params={}
            )

        self.assertEqual(result, {})
        self.assertEqual(exec_mock.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep_mock.call_args_list], [2, 4])
