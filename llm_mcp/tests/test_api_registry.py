import json

from odoo.tests import HttpCase


class TestToolRegistryAPI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("llm_tool.api_token", "test-token")

        tag_model = cls.env["llm.tool.tag"].sudo()
        cls.open_world_tag = tag_model.create({"name": "open-world"})
        cls.user_consent_tag = tag_model.create({"name": "user-consent"})

        cls.consent_template = cls.env["llm.mcp.consent.template"].sudo().create(
            {
                "name": "Consent for sensitive tools",
                "scope": "tool",
                "default_opt": "opt_in",
            }
        )

        definition_model = cls.env["llm.tool.definition"].sudo()
        cls.open_tool = definition_model.create(
            {
                "name": "open_tool",
                "action_type": "read",
                "description": "Open world tool",
                "is_open_world": True,
                "tag_ids": [(6, 0, cls.open_world_tag.ids)],
                "target_model": "res.partner",
            }
        )

        cls.group_tool = definition_model.create(
            {
                "name": "group_tool",
                "action_type": "update",
                "description": "Group limited tool",
                "target_model": "res.partner",
                "access_group_ids": [(6, 0, cls.env.ref("base.group_user").ids)],
            }
        )

        cls.consent_tool = definition_model.create(
            {
                "name": "consent_tool",
                "action_type": "external_api",
                "description": "Consent required tool",
                "schema_json": {"type": "object", "properties": {}},
                "tag_ids": [(6, 0, cls.user_consent_tag.ids)],
                "mcp_consent_template_id": cls.consent_template.id,
            }
        )

    def _headers(self, token=None):
        return {"Authorization": f"Bearer {token or 'test-token'}"}

    def test_tool_visibility_and_filters(self):
        response = self.url_open("/mcp/tool_registry", headers=self._headers())
        data = json.loads(response.text)
        names = {tool["tool_key"] for tool in data["tools"]}

        self.assertIn("open_tool", names)
        self.assertIn("group_tool", names)
        self.assertNotIn("consent_tool", names)

        ledger = self.env["llm.mcp.consent.ledger"].sudo()
        ledger.log_decision(
            tool=self.consent_tool,
            template=self.consent_template,
            decision="granted",
            user=self.env.user,
        )

        filtered_response = self.url_open(
            "/mcp/tool_registry?tags=open-world", headers=self._headers()
        )
        filtered_data = json.loads(filtered_response.text)
        filtered_names = {tool["tool_key"] for tool in filtered_data["tools"]}
        self.assertEqual(filtered_names, {"open_tool"})

        response_after_consent = self.url_open(
            "/mcp/tool_registry", headers=self._headers()
        )
        data_after_consent = json.loads(response_after_consent.text)
        names_after_consent = {tool["tool_key"] for tool in data_after_consent["tools"]}
        self.assertIn("consent_tool", names_after_consent)

        consent_tool_payload = next(
            tool for tool in data_after_consent["tools"] if tool["tool_key"] == "consent_tool"
        )
        self.assertTrue(consent_tool_payload.get("consent_required"))

    def test_invalid_token_rejected(self):
        response = self.url_open(
            "/mcp/tool_registry", headers=self._headers(token="invalid")
        )
        self.assertEqual(response.status_code, 403)
