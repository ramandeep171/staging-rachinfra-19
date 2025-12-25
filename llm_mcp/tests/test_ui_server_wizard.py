from odoo.exceptions import AccessError
from odoo.tests import SavepointCase


class TestMCPServerWizard(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool = cls.env["llm.tool"].create(
            {
                "name": "sample_tool",
                "description": "Sample tool",
                "implementation": "mcp",
            }
        )

    def test_wizard_creates_server_and_runner(self):
        wizard = self.env["llm.mcp.server.wizard"].create(
            {
                "name": "Wizard Server",
                "transport_types": "http",
                "audit_flags": "enforce",
                "host_config_json": {"base_url": "https://mcp.example.com"},
                "runner_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "HTTP Runner",
                            "type": "http",
                            "entrypoint": "https://mcp.example.com/run",
                            "allowed_tool_ids": [(6, 0, self.tool.ids)],
                        },
                    )
                ],
            }
        )

        action = wizard.action_create_server()
        server = self.env["llm.mcp.server"].browse(action["res_id"])
        self.assertEqual(server.transport_types, "http")
        self.assertEqual(server.audit_flags, "enforce")
        self.assertEqual(server.command_runner_ids.name, "HTTP Runner")
        self.assertEqual(server.command_runner_ids.allowed_tool_ids, self.tool)

        runner = server.command_runner_ids
        runner.unlink()
        self.assertTrue(self.tool.exists())

    def test_non_admin_cannot_manage_server(self):
        user_demo = self.env["res.users"].create(
            {
                "name": "MCP Demo User",
                "login": "mcp_demo",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

        with self.assertRaises(AccessError):
            self.env["llm.mcp.server"].with_user(user_demo).create(
                {
                    "name": "Blocked Server",
                    "transport_types": "stdio",
                    "command": "echo",
                }
            )
