from datetime import timedelta

import pytest

import odoo
from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import SavepointCase


IS_ODOO_STUB = getattr(odoo, "__is_stub__", False)
pytestmark = pytest.mark.skipif(IS_ODOO_STUB, reason="Requires real Odoo runtime")


class TestPolicyMiddleware(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_model = cls.env["llm.mcp.consent.template"]
        cls.ledger_model = cls.env["llm.mcp.consent.ledger"]
        cls.tool_model = cls.env["llm.tool.definition"]
        cls.tag_model = cls.env["llm.tool.tag"]
        cls.enforcer = cls.env["llm.mcp.policy.enforcer"]

        cls.user_consent_tag = cls.tag_model.search([("name", "=", "user-consent")], limit=1)
        if not cls.user_consent_tag:
            cls.user_consent_tag = cls.tag_model.create({"name": "user-consent"})

    def test_pass_through_without_template(self):
        tool = self.tool_model.create(
            {
                "name": "no_template_tool",
                "action_type": "read",
                "description": "Does not need consent",
                "schema_json": {"type": "object"},
            }
        )

        decision = self.enforcer.enforce_consent_policy(tool=tool, user=self.env.user)
        self.assertEqual(decision.get("status"), "ALLOW")
        self.assertFalse(decision.get("enforced"))
        self.assertFalse(decision.get("ledger"))

    def test_allow_with_valid_consent(self):
        template = self.template_model.create(
            {"name": "Allow template", "scope": "tool", "default_opt": "opt_in"}
        )
        tool = self.tool_model.create(
            {
                "name": "consented_tool",
                "action_type": "external_api",
                "description": "Requires consent",
                "schema_json": {"type": "object"},
                "mcp_consent_template_id": template.id,
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )
        ledger = self.ledger_model.log_decision(tool, template, "granted", user=self.env.user)

        decision = self.enforcer.enforce_consent_policy(tool=tool, user=self.env.user)
        self.assertEqual(decision.get("status"), "ALLOW")
        self.assertEqual(decision.get("ledger"), ledger)

    def test_expired_consent_blocks(self):
        template = self.template_model.create(
            {"name": "TTL template", "scope": "tool", "default_opt": "opt_in", "ttl_days": 1}
        )
        tool = self.tool_model.create(
            {
                "name": "ttl_tool",
                "action_type": "external_api",
                "description": "TTL check",
                "schema_json": {"type": "object"},
                "mcp_consent_template_id": template.id,
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )
        ledger = self.ledger_model.log_decision(tool, template, "granted", user=self.env.user)
        ledger.write({"timestamp": fields.Datetime.now() - timedelta(days=5)})
        ledger.invalidate_recordset(["expired"])

        decision = self.enforcer.enforce_consent_policy(tool=tool, user=self.env.user)
        self.assertEqual(decision.get("status"), "BLOCK")
        self.assertEqual(decision.get("ledger"), ledger)

    def test_missing_template_raises_for_tagged_tool(self):
        tool = self.tool_model.create(
            {
                "name": "tagged_tool_missing_template",
                "action_type": "external_api",
                "description": "Tagged without template",
                "schema_json": {"type": "object"},
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )

        with self.assertRaises(UserError):
            self.enforcer.enforce_consent_policy(tool=tool, user=self.env.user)

    def test_revoked_consent_blocks_execution(self):
        template = self.template_model.create(
            {"name": "Revokable", "scope": "tool", "default_opt": "opt_in"}
        )
        tool = self.tool_model.create(
            {
                "name": "revokable_tool",
                "action_type": "external_api",
                "description": "Revokable",
                "schema_json": {"type": "object"},
                "mcp_consent_template_id": template.id,
                "tag_ids": [(6, 0, self.user_consent_tag.ids)],
            }
        )
        self.ledger_model.log_decision(tool, template, "granted", user=self.env.user)
        denial = self.ledger_model.log_decision(tool, template, "denied", user=self.env.user)

        decision = self.enforcer.enforce_consent_policy(tool=tool, user=self.env.user)
        self.assertEqual(decision.get("status"), "BLOCK")
        self.assertEqual(decision.get("ledger"), denial)
