from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import SavepointCase


class TestWhatsAppTool(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_service = cls.env["llm.tool.whatsapp"]
        cls.definition_model = cls.env["llm.tool.definition"].sudo()
        cls.tag_model = cls.env["llm.tool.tag"].sudo()
        cls.runner_model = cls.env["llm.mcp.command.runner"].sudo()
        cls.consent_template_model = cls.env["llm.mcp.consent.template"].sudo()
        cls.ledger_model = cls.env["llm.mcp.consent.ledger"].sudo()

        destructive = cls.tag_model.create({"name": "destructive"})
        consent_tag = cls.tag_model.create({"name": "user-consent"})

        cls.consent_template = cls.consent_template_model.create(
            {
                "name": "WhatsApp consent",
                "scope": "tool",
                "default_opt": "opt_in",
            }
        )

        cls.tool_definition = cls.definition_model.create(
            {
                "name": "send_whatsapp_message",
                "action_type": "external_api",
                "description": "Send WhatsApp message via remote API",
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "recipient_number": {"type": "string"},
                        "message_body": {"type": "string"},
                        "media_url": {"type": "string"},
                    },
                    "required": ["recipient_number", "message_body"],
                },
                "tag_ids": [(6, 0, (destructive | consent_tag).ids)],
                "mcp_consent_template_id": cls.consent_template.id,
            }
        )

        cls.runner = cls.runner_model.create(
            {
                "name": "WhatsApp Remote Runner",
                "server_id": cls.env["llm.mcp.server"].create(
                    {"name": "API", "transport_types": "remote_api"}
                ).id,
                "type": "remote_api",
                "entrypoint": "https://api.example.test/messages",
                "retry_policy": {"retries": 1},
                "auth_headers": {"Authorization": "Bearer test"},
            }
        )

    def _grant_consent(self):
        return self.env["llm.mcp.consent.handler"].request_consent(
            self.tool_definition, user=self.env.user, decision="granted"
        )

    def test_successful_send_logs_invocation(self):
        self._grant_consent()
        payload = {
            "recipient_number": "+15551234567",
            "message_body": "Hello!",
        }

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "status": "sent",
                "message_id": "msg-123",
            }

            result = self.tool_service.send_message(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        self.assertEqual(result["status"], "sent")
        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(invocation.status, "success")
        self.assertEqual(invocation.runner_id, self.runner)
        self.assertTrue(invocation.result_json.get("message_id"))

    def test_invalid_recipient_blocks_and_audits(self):
        self._grant_consent()
        payload = {
            "recipient_number": "abc",
            "message_body": "Hello!",
        }

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "sent"}
            with self.assertRaises(ValidationError):
                self.tool_service.send_message(
                    tool=self.tool_definition, payload=payload, runner=self.runner
                )

        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(invocation.status, "failed")
        audit = self.env["llm.mcp.audit.trail"].search(
            [("invocation_id", "=", invocation.id)], limit=1, order="id desc"
        )
        self.assertEqual(audit.event_type, "failed")

    def test_consent_enforced_and_revocation_blocks(self):
        payload = {
            "recipient_number": "+15551234567",
            "message_body": "Hello!",
        }

        with self.assertRaises(UserError):
            self.tool_service.send_message(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        self._grant_consent()

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "sent"}
            self.tool_service.send_message(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        revoke = self.env["llm.mcp.consent.handler"].revoke_consent(
            user=self.env.user, tool=self.tool_definition
        )
        self.assertEqual(revoke.get("status"), "revoked")

        with self.assertRaises(UserError):
            self.tool_service.send_message(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

    def test_retry_simulation(self):
        self._grant_consent()
        payload = {
            "recipient_number": "+15551234567",
            "message_body": "Hello!",
        }

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.side_effect = [Exception("boom"), mock_post.return_value]
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "sent"}

            result = self.tool_service.send_message(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        self.assertEqual(result["status"], "sent")
