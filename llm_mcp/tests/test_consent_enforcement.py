from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import SavepointCase


class TestConsentEnforcement(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_model = cls.env["llm.mcp.consent.template"]
        cls.ledger_model = cls.env["llm.mcp.consent.ledger"]
        cls.tool_model = cls.env["llm.tool.definition"]
        cls.tag_model = cls.env["llm.tool.tag"]

        cls.user_consent_tag = cls.tag_model.search([("name", "=", "user-consent")], limit=1)
        if not cls.user_consent_tag:
            cls.user_consent_tag = cls.tag_model.create({"name": "user-consent"})

        cls.template = cls.template_model.create(
            {
                "name": "Tool Consent",
                "scope": "tool",
                "default_opt": "opt_in",
                "ttl_days": 2,
                "message_html": "<p>Allow execution?</p>",
            }
        )

        cls.tool = cls.tool_model.create(
            {
                "name": "send_whatsapp_message",
                "action_type": "external_api",
                "description": "Send WhatsApp message",
                "schema_json": {"type": "object"},
                "mcp_consent_template_id": cls.template.id,
                "tag_ids": [(6, 0, cls.user_consent_tag.ids)],
            }
        )

    def test_consent_logged_and_reused(self):
        ledger = self.ledger_model.log_decision(
            self.tool,
            self.template,
            decision="granted",
            user=self.env.user,
            context_payload={"reason": "manual approval"},
        )
        self.assertFalse(ledger.expired)

        reused = self.ledger_model.enforce_consent(self.tool, user=self.env.user)
        self.assertEqual(reused, ledger)

    def test_ttl_expiry_blocks_execution(self):
        ledger = self.ledger_model.log_decision(
            self.tool,
            self.template,
            decision="granted",
            user=self.env.user,
        )
        ledger.write({"timestamp": fields.Datetime.now() - timedelta(days=5)})
        ledger.invalidate_recordset(["expired"])

        with self.assertRaises(UserError):
            self.ledger_model.enforce_consent(self.tool, user=self.env.user)

    def test_opt_out_autogrants(self):
        opt_out_template = self.template_model.create(
            {
                "name": "Global Opt-out",
                "scope": "tool",
                "default_opt": "opt_out",
                "ttl_days": 0,
            }
        )
        tool_opt_out = self.tool_model.create(
            {
                "name": "calendar_event_creator",
                "action_type": "create",
                "description": "Create calendar event",
                "target_model": "calendar.event",
                "mcp_consent_template_id": opt_out_template.id,
            }
        )

        ledger = self.ledger_model.enforce_consent(
            tool_opt_out,
            user=self.env.user,
            context_payload={"auto": True},
        )
        self.assertEqual(ledger.decision, "granted")
        self.assertFalse(ledger.expired)

    def test_missing_template_blocks_tagged_tool(self):
        tool_missing_template = self.tool_model.create(
            {
                "name": "lead_followup_flow",
                "action_type": "method",
                "description": "Lead followup flow",
                "target_model": "crm.lead",
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )
        with self.assertRaises(UserError):
            self.ledger_model.enforce_consent(tool_missing_template, user=self.env.user)
