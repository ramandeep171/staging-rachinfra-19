from unittest.mock import Mock, patch

import pytest

import odoo
from odoo.exceptions import UserError, ValidationError
from odoo.tests import SavepointCase


IS_ODOO_STUB = getattr(odoo, "__is_stub__", False)
pytestmark = pytest.mark.skipif(IS_ODOO_STUB, reason="Requires real Odoo runtime")


class TestLeadFollowupFlow(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.flow_service = cls.env["llm.flow.lead_followup"]
        cls.whatsapp_service = cls.env["llm.tool.whatsapp"]
        cls.calendar_service = cls.env["llm.tool.calendar_event"]
        cls.definition_model = cls.env["llm.tool.definition"].sudo()
        cls.tag_model = cls.env["llm.tool.tag"].sudo()
        cls.runner_model = cls.env["llm.mcp.command.runner"].sudo()
        cls.consent_template_model = cls.env["llm.mcp.consent.template"].sudo()

        destructive = cls.tag_model.create({"name": "destructive"})
        consent_tag = cls.tag_model.create({"name": "user-consent"})
        idempotent = cls.tag_model.create({"name": "idempotent"})

        cls.whatsapp_consent = cls.consent_template_model.create(
            {"name": "WhatsApp consent", "scope": "tool", "default_opt": "opt_in"}
        )
        cls.calendar_consent = cls.consent_template_model.create(
            {"name": "Calendar consent", "scope": "tool", "default_opt": "opt_in"}
        )

        cls.whatsapp_tool_def = cls.definition_model.create(
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
                "mcp_consent_template_id": cls.whatsapp_consent.id,
            }
        )

        cls.calendar_tool_def = cls.definition_model.create(
            {
                "name": "create_google_calendar_event",
                "action_type": "external_api",
                "description": "Create Google Calendar event",
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_datetime": {"type": "string"},
                        "end_datetime": {"type": "string"},
                    },
                    "required": ["title", "start_datetime", "end_datetime"],
                },
                "tag_ids": [(6, 0, (idempotent | consent_tag).ids)],
                "mcp_consent_template_id": cls.calendar_consent.id,
            }
        )

        cls.flow_def = cls.definition_model.create(
            {
                "name": "lead_followup_flow",
                "action_type": "method",
                "description": "Chain lead follow-up actions",
                "target_model": "res.partner",
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "integer"},
                        "message_body": {"type": "string"},
                        "followup_time": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "attendees": {"type": "array"},
                        "location": {"type": "string"},
                        "media_url": {"type": "string"},
                    },
                    "required": ["lead_id", "message_body", "followup_time"],
                },
            }
        )

        cls.flow_runner = cls.runner_model.create(
            {
                "name": "Lead Flow Runner",
                "server_id": cls.env["llm.mcp.server"].create(
                    {"name": "Local", "transport_types": "local_agent"}
                ).id,
                "type": "local_agent",
                "entrypoint": "local://lead_flow",
            }
        )

        # Subtool runners (remote)
        cls.remote_runner = cls.runner_model.create(
            {
                "name": "Remote API",
                "server_id": cls.env["llm.mcp.server"].create(
                    {"name": "API", "transport_types": "remote_api"}
                ).id,
                "type": "remote_api",
                "entrypoint": "https://api.example.test/endpoint",
                "auth_headers": {"Authorization": "Bearer token"},
            }
        )

    def _grant_consent(self):
        handler = self.env["llm.mcp.consent.handler"]
        handler.request_consent(self.whatsapp_tool_def, user=self.env.user, decision="granted")
        handler.request_consent(self.calendar_tool_def, user=self.env.user, decision="granted")

    def _lead(self, mobile="+15551234567", email="demo@example.com"):
        return self.env["res.partner"].create({"name": "Demo Lead", "mobile": mobile, "email": email})

    def _payload(self, lead):
        return {
            "lead_id": lead.id,
            "message_body": "Hello!",
            "followup_time": "2024-01-01 10:00:00",
            "duration_minutes": 60,
            "attendees": ["demo@example.com"],
            "location": "HQ",
        }

    def test_flow_success_sequences_steps_and_links_children(self):
        self._grant_consent()
        lead = self._lead()
        payload = self._payload(lead)

        first_response = Mock(status_code=200)
        first_response.json.return_value = {"status": "sent", "message_id": "msg-1"}
        second_response = Mock(status_code=200)
        second_response.json.return_value = {
            "status": "created",
            "calendar_event_id": "evt-1",
            "calendar_link": "https://calendar.test/evt-1",
        }

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.side_effect = [first_response, second_response]
            result = self.flow_service.run_flow(
                tool=self.flow_def, payload=payload, runner=self.flow_runner
            )

        self.assertEqual(result["whatsapp"]["status"], "sent")
        self.assertEqual(result["calendar"]["calendar_event_id"], "evt-1")

        flow_invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        children = self.env["llm.mcp.invocation.record"].search(
            [("parent_invocation_id", "=", flow_invocation.id)]
        )
        self.assertEqual(flow_invocation.status, "success")
        self.assertGreaterEqual(len(children), 2)

    def test_flow_skips_whatsapp_when_no_mobile(self):
        self._grant_consent()
        lead = self._lead(mobile=False)
        payload = self._payload(lead)

        calendar_response = Mock(status_code=200)
        calendar_response.json.return_value = {
            "status": "created",
            "calendar_event_id": "evt-2",
            "calendar_link": "https://calendar.test/evt-2",
        }

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.side_effect = [calendar_response]
            result = self.flow_service.run_flow(
                tool=self.flow_def, payload=payload, runner=self.flow_runner
            )

        self.assertTrue(result["whatsapp"]["skipped"])
        self.assertEqual(result["whatsapp"]["reason"], "missing_mobile")
        self.assertEqual(result["calendar"]["calendar_event_id"], "evt-2")

    def test_flow_blocks_when_consent_missing(self):
        lead = self._lead()
        payload = self._payload(lead)

        with self.assertRaises(UserError):
            self.flow_service.run_flow(tool=self.flow_def, payload=payload, runner=self.flow_runner)

        flow_invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(flow_invocation.status, "failed")

    def test_validation_blocks_bad_payload(self):
        lead = self._lead()
        payload = self._payload(lead)
        payload["duration_minutes"] = -1

        with self.assertRaises(ValidationError):
            self.flow_service.run_flow(tool=self.flow_def, payload=payload, runner=self.flow_runner)
