import json
from datetime import timedelta

import pytest

import odoo
from odoo import fields
from odoo.tests import HttpCase


IS_ODOO_STUB = getattr(odoo, "__is_stub__", False)
pytestmark = pytest.mark.skipif(IS_ODOO_STUB, reason="Requires real Odoo runtime")


class TestConsentAPI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("llm_mcp.api_token", "test-token")

        cls.consent_template = cls.env["llm.mcp.consent.template"].sudo().create(
            {
                "name": "Sensitive tool consent",
                "scope": "tool",
                "default_opt": "opt_in",
                "message_html": "<p>Allow execution?</p>",
                "ttl_days": 1,
            }
        )

        cls.tool = cls.env["llm.tool.definition"].sudo().create(
            {
                "name": "send_whatsapp_message",
                "action_type": "external_api",
                "description": "Send WhatsApp message",
                "schema_json": {"type": "object"},
                "mcp_consent_template_id": cls.consent_template.id,
            }
        )

    def _headers(self, token=None):
        return {
            "Authorization": f"Bearer {token or 'test-token'}",
            "Content-Type": "application/json",
        }

    def _post(self, url, payload, token=None):
        return self.url_open(url, data=json.dumps(payload), headers=self._headers(token))

    def test_request_and_grant_consent(self):
        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()

        response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id},
        )
        data = json.loads(response.text)
        self.assertEqual(data["status"], "required")
        self.assertEqual(ledger_model.search_count([("tool_id", "=", self.tool.id)]), 0)

        response_grant = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id, "decision": "granted"},
        )
        data_grant = json.loads(response_grant.text)
        self.assertEqual(data_grant["status"], "granted")
        self.assertTrue(data_grant.get("ledger_id"))
        self.assertEqual(
            ledger_model.search_count(
                [
                    ("tool_id", "=", self.tool.id),
                    ("decision", "=", "granted"),
                ]
            ),
            1,
        )

        response_repeat = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id},
        )
        data_repeat = json.loads(response_repeat.text)
        self.assertEqual(data_repeat["status"], "granted")
        self.assertEqual(
            ledger_model.search_count(
                [
                    ("tool_id", "=", self.tool.id),
                    ("decision", "=", "granted"),
                ]
            ),
            1,
        )

    def test_revoke_blocks_and_ttl_expiry(self):
        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()

        grant_response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id, "decision": "granted"},
        )
        grant_data = json.loads(grant_response.text)
        ledger_id = grant_data.get("ledger_id")

        revoke_response = self._post(
            "/mcp/consent/revoke",
            {"ledger_id": ledger_id, "user_id": self.env.user.id},
        )
        revoke_data = json.loads(revoke_response.text)
        self.assertEqual(revoke_data["status"], "revoked")

        blocked_response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id},
        )
        blocked_data = json.loads(blocked_response.text)
        self.assertEqual(blocked_data["status"], "blocked")

        # Re-approve and expire the entry manually to force TTL enforcement
        approve_response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id, "decision": "granted"},
        )
        approve_data = json.loads(approve_response.text)
        refreshed_ledger = ledger_model.browse(approve_data.get("ledger_id"))
        denial_entry = ledger_model.search(
            [
                ("tool_id", "=", self.tool.id),
                ("decision", "=", "denied"),
            ],
            order="timestamp desc",
            limit=1,
        )
        if denial_entry:
            denial_entry.write({"timestamp": fields.Datetime.now() - timedelta(days=3)})
        refreshed_ledger.write(
            {"timestamp": fields.Datetime.now() - timedelta(days=2)}
        )
        refreshed_ledger.invalidate_recordset(["expired"])

        expired_response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id},
        )
        expired_data = json.loads(expired_response.text)
        self.assertEqual(expired_data["status"], "required")

    def test_invalid_token_rejected(self):
        response = self._post(
            "/mcp/consent/request",
            {"tool_id": self.tool.id, "user_id": self.env.user.id},
            token="invalid",
        )
        self.assertEqual(response.status_code, 403)

