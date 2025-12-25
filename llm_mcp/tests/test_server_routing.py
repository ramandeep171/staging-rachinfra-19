from odoo.exceptions import UserError, ValidationError
from odoo.tests import SavepointCase


class TestMCPServerRouting(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server_model = cls.env["llm.mcp.server"]
        cls.runner_model = cls.env["llm.mcp.command.runner"]
        cls.tool_model = cls.env["llm.tool"]

        cls.server = cls.server_model.create(
            {
                "name": "Remote API Server",
                "transport_types": "remote_api",
                "host_config_json": {"base_url": "https://api.example.com"},
            }
        )

        cls.tool = cls.tool_model.create(
            {
                "name": "send_whatsapp_message",
                "description": "Send WhatsApp message",
                "implementation": "mcp",
                "mcp_server_id": cls.server.id,
            }
        )

    def test_runner_attached_and_routing(self):
        runner = self.runner_model.create(
            {
                "name": "Remote API Runner",
                "server_id": self.server.id,
                "type": "remote_api",
                "entrypoint": "https://api.example.com/tools",
                "retry_policy": {"retries": 1},
                "allowed_tool_ids": [(6, 0, self.tool.ids)],
            }
        )

        result = self.server.execute_tool(self.tool.name, {"ping": True})
        self.assertEqual(result.get("status"), "ok")
        self.assertIn(runner, self.server.command_runner_ids)

    def test_runner_tool_scope_enforced(self):
        other_tool = self.tool_model.create(
            {
                "name": "calendar_event_creator",
                "description": "Create calendar event",
                "implementation": "mcp",
                "mcp_server_id": self.server.id,
            }
        )
        runner = self.runner_model.create(
            {
                "name": "Scoped Runner",
                "server_id": self.server.id,
                "type": "remote_api",
                "entrypoint": "https://api.example.com/tools",
                "allowed_tool_ids": [(6, 0, other_tool.ids)],
            }
        )

        with self.assertRaises(ValidationError):
            runner.run_command(self.tool, {})

        with self.assertRaises(UserError):
            self.server.execute_tool("unknown_tool", {})

    def test_retry_policy_honored(self):
        runner = self.runner_model.create(
            {
                "name": "Retry Runner",
                "server_id": self.server.id,
                "type": "remote_api",
                "entrypoint": "https://api.example.com/tools",
                "retry_policy": {"retries": 2},
            }
        )

        with self.assertRaises(UserError):
            runner.run_command(self.tool, {"force_fail": True})
