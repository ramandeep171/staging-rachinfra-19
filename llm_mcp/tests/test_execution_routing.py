import pytest

import odoo

from odoo.exceptions import UserError
from odoo.tests import SavepointCase


IS_ODOO_STUB = getattr(odoo, "__is_stub__", False)
pytestmark = pytest.mark.skipif(IS_ODOO_STUB, reason="Requires real Odoo runtime")


class TestExecutionRouting(SavepointCase):
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
                "name": "router_demo_tool",
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
                "name": "Default Binding",
                "tool_id": cls.tool_definition.id,
                "runner_id": cls.tool_runner.id,
                "executor_path": "/bin/echo",
                "timeout": 20,
            }
        )

        cls.router = cls.env["llm.mcp.execution.router"]

    def test_valid_route_executes_and_logs(self):
        result = self.router.route(
            session_id="sess-1",
            tool_key=self.tool_definition.name,
            params={"echo": "hi"},
        )

        self.assertEqual(result.get("status"), "ok")
        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(invocation.status, "success")
        self.assertEqual(invocation.tool_version_id.tool_id, self.tool_definition)

    def test_consent_required_blocks(self):
        template = self.env["llm.mcp.consent.template"].create(
            {"name": "Tool Consent", "scope": "tool", "default_opt": "opt_in"}
        )
        tool = self.env["llm.tool.definition"].create(
            {
                "name": "consent_tool",
                "action_type": "external_api",
                "description": "Requires consent",
                "schema_json": {"type": "object", "properties": {}},
                "mcp_consent_template_id": template.id,
            }
        )
        self.env["llm.tool.binding"].create(
            {
                "name": "Consent Binding",
                "tool_id": tool.id,
                "runner_id": self.tool_runner.id,
                "executor_path": "/bin/echo",
            }
        )

        with self.assertRaises(UserError):
            self.router.route("sess-2", tool_key=tool.name, params={})

    def test_acl_blocks_disallowed_user(self):
        group_system = self.env.ref("base.group_system")
        limited_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Limited",
                "login": "limited@example.com",
                "email": "limited@example.com",
                "groups_id": [(6, 0, self.env.ref("base.group_user").ids)],
            }
        )

        restricted_tool = self.env["llm.tool.definition"].create(
            {
                "name": "restricted_tool",
                "action_type": "external_api",
                "description": "Restricted",
                "schema_json": {"type": "object", "properties": {}},
                "access_group_ids": [(6, 0, group_system.ids)],
            }
        )
        self.env["llm.tool.binding"].create(
            {
                "name": "Restricted Binding",
                "tool_id": restricted_tool.id,
                "runner_id": self.tool_runner.id,
                "executor_path": "/bin/echo",
            }
        )

        with self.assertRaises(UserError):
            self.router.route(
                session_id="sess-3", tool_key=restricted_tool.name, user=limited_user
            )
