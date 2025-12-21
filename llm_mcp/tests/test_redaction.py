from odoo.tests import TransactionCase


class TestRedaction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_model = cls.env["llm.tool.definition"].sudo()
        cls.server_model = cls.env["llm.mcp.server"].sudo()
        cls.runner_model = cls.env["llm.mcp.command.runner"].sudo()

        cls.tool = cls.tool_model.create(
            {
                "name": "secure_tool",
                "action_type": "external_api",
                "description": "Tool with explicit redaction policy",
                "schema_json": {"type": "object", "properties": {}},
                "redaction_policy_json": {"fields": ["api_key", "phone_number"]},
            }
        )

        cls.server = cls.server_model.create({"name": "Redaction Server"})
        cls.runner = cls.runner_model.create(
            {
                "name": "API Runner",
                "server_id": cls.server.id,
                "type": "remote_api",
                "entrypoint": "https://example.invalid/api",
            }
        )

    def test_policy_driven_redaction_on_invocation(self):
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        payload = {"api_key": "secret", "phone_number": "+123", "other": "ok"}
        result = {"status": "ok", "api_key": "returned"}

        invocation = invocation_model.log_invocation(
            tool_version=self.tool.latest_version_id,
            runner=self.runner,
            params=payload,
            result=result,
        )

        self.assertEqual(invocation.params_redacted.get("api_key"), "***")
        self.assertEqual(invocation.params_redacted.get("phone_number"), "***")
        self.assertEqual(invocation.params_redacted.get("other"), "ok")
        self.assertEqual(invocation.result_json.get("api_key"), "***")
        self.assertEqual(invocation.result_redacted.get("status"), "ok")

    def test_tag_based_fallback_applies(self):
        destructive_tag = self.env["llm.tool.tag"].sudo().create({"name": "destructive"})
        fallback_tool = self.tool_model.create(
            {
                "name": "tagged_tool",
                "action_type": "external_api",
                "description": "Tool uses tag defaults",
                "schema_json": {"type": "object", "properties": {}},
                "tag_ids": [(6, 0, destructive_tag.ids)],
            }
        )

        engine = self.env["llm.tool.redaction.engine"]
        redacted = engine.redact_payload(
            fallback_tool, {"token": "abc", "nested": {"phone_number": "123"}}
        )

        self.assertEqual(redacted["token"], "***")
        self.assertEqual(redacted["nested"]["phone_number"], "***")
