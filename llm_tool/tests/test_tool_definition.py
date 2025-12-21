from odoo.exceptions import ValidationError
from odoo.tests import SavepointCase


class TestToolDefinition(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition_model = cls.env["llm.tool.definition"]
        cls.binding_model = cls.env["llm.tool.binding"]
        cls.version_model = cls.env["llm.tool.version"]
        cls.tag_model = cls.env["llm.tool.tag"]
        cls.runner_model = cls.env["llm.tool.runner"]
        cls.consent_model = cls.env["llm.tool.consent.config"]

        cls.runner = cls.runner_model.create(
            {
                "name": "Local Runner",
                "runner_type": "local",
            }
        )
        cls.user_consent_tag = cls.tag_model.create({"name": "user-consent"})
        cls.open_world_tag = cls.tag_model.create({"name": "open-world"})
        cls.consent_template = cls.consent_model.search([], limit=1)
        if not cls.consent_template:
            cls.consent_template = cls.consent_model.create({"name": "Default Consent"})

    def test_definition_and_binding_create_version(self):
        tool = self.definition_model.create(
            {
                "name": "send_whatsapp_message",
                "action_type": "external_api",
                "description": "Send WhatsApp message via connector",
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["phone", "body"],
                },
                "tag_ids": [(6, 0, self.open_world_tag.ids)],
            }
        )

        binding = self.binding_model.create(
            {
                "name": "Default binding",
                "tool_id": tool.id,
                "runner_id": self.runner.id,
                "executor_path": "/opt/bin/whatsapp",
                "timeout": 30,
            }
        )

        self.assertTrue(binding.version_id)
        self.assertEqual(binding.tool_id, tool)
        self.assertEqual(
            binding.version_id.schema_hash,
            tool._compute_schema_hash(tool.schema_json),
        )

    def test_user_consent_tag_requires_template(self):
        with self.assertRaises(ValidationError):
            self.definition_model.create(
                {
                    "name": "schedule_event",
                    "action_type": "create",
                    "description": "Create calendar event",
                    "target_model": "calendar.event",
                    "tag_ids": [(6, 0, self.user_consent_tag.ids)],
                }
            )

    def test_invalid_schema_hash_raises(self):
        tool = self.definition_model.create(
            {
                "name": "lead_followup_flow",
                "action_type": "method",
                "description": "Lead follow-up chain",
                "target_model": "crm.lead",
                "schema_json": {"type": "object", "properties": {}},
                "consent_template_id": self.consent_template.id,
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )

        with self.assertRaises(ValidationError):
            self.version_model.create(
                {
                    "tool_id": tool.id,
                    "version": 99,
                    "schema_hash": "bogus",
                }
            )
