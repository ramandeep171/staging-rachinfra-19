from unittest.mock import patch

import pytest

import odoo
from odoo.exceptions import UserError, ValidationError
from odoo.tests import SavepointCase


IS_ODOO_STUB = getattr(odoo, "__is_stub__", False)
pytestmark = pytest.mark.skipif(IS_ODOO_STUB, reason="Requires real Odoo runtime")


class TestCalendarTool(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_service = cls.env["llm.tool.calendar_event"]
        cls.definition_model = cls.env["llm.tool.definition"].sudo()
        cls.tag_model = cls.env["llm.tool.tag"].sudo()
        cls.runner_model = cls.env["llm.mcp.command.runner"].sudo()
        cls.consent_template_model = cls.env["llm.mcp.consent.template"].sudo()

        idempotent = cls.tag_model.create({"name": "idempotent"})
        consent_tag = cls.tag_model.create({"name": "user-consent"})

        cls.consent_template = cls.consent_template_model.create(
            {
                "name": "Calendar Consent",
                "scope": "tool",
                "default_opt": "opt_in",
            }
        )

        cls.tool_definition = cls.definition_model.create(
            {
                "name": "create_google_calendar_event",
                "action_type": "external_api",
                "description": "Create Google Calendar event via remote API",
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_datetime": {"type": "string"},
                        "end_datetime": {"type": "string"},
                        "attendees": {"type": "array"},
                        "location": {"type": "string"},
                        "reminders": {"type": "array"},
                    },
                    "required": ["title", "start_datetime", "end_datetime"],
                },
                "tag_ids": [(6, 0, (idempotent | consent_tag).ids)],
                "mcp_consent_template_id": cls.consent_template.id,
            }
        )

        cls.runner = cls.runner_model.create(
            {
                "name": "Calendar Remote Runner",
                "server_id": cls.env["llm.mcp.server"].create(
                    {"name": "API", "transport_types": "remote_api"}
                ).id,
                "type": "remote_api",
                "entrypoint": "https://api.example.test/calendar/events",
                "retry_policy": {"retries": 1},
                "auth_headers": {"Authorization": "Bearer calendar"},
            }
        )

    def _grant_consent(self):
        return self.env["llm.mcp.consent.handler"].request_consent(
            self.tool_definition, user=self.env.user, decision="granted"
        )

    def _payload(self):
        return {
            "title": "Demo Meeting",
            "start_datetime": "2024-01-01 10:00:00",
            "end_datetime": "2024-01-01 11:00:00",
            "attendees": ["demo@example.com", {"email": "second@example.com"}],
            "location": "HQ",
            "reminders": [15, {"minutes": 30}],
        }

    def test_valid_event_creation_logs_invocation(self):
        self._grant_consent()
        payload = self._payload()

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "status": "created",
                "calendar_event_id": "evt-123",
                "calendar_link": "https://calendar.test/events/evt-123",
            }

            result = self.tool_service.create_event(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        self.assertEqual(result["status"], "created")
        self.assertEqual(result["calendar_event_id"], "evt-123")
        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(invocation.status, "success")
        self.assertEqual(invocation.runner_id, self.runner)
        self.assertEqual(invocation.result_json.get("calendar_event_id"), "evt-123")

    def test_invalid_datetime_raises(self):
        self._grant_consent()
        payload = self._payload()
        payload["end_datetime"] = "bad-value"

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "created"}
            with self.assertRaises(ValidationError):
                self.tool_service.create_event(
                    tool=self.tool_definition, payload=payload, runner=self.runner
                )

        invocation = self.env["llm.mcp.invocation.record"].search([], limit=1, order="id desc")
        self.assertEqual(invocation.status, "failed")

    def test_duplicate_payload_rejected_for_idempotency(self):
        self._grant_consent()
        payload = self._payload()

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"status": "created"}
            self.tool_service.create_event(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        with self.assertRaises(ValidationError):
            self.tool_service.create_event(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

    def test_consent_required_blocks_when_missing(self):
        payload = self._payload()
        with self.assertRaises(UserError):
            self.tool_service.create_event(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

    def test_attendees_and_reminders_parsed(self):
        self._grant_consent()
        payload = self._payload()
        payload["reminders"] = [5]
        payload["attendees"] = [{"email": "valid@example.com"}]

        with patch("llm_mcp.models.command_runner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "status": "created",
                "calendar_event_id": "evt-999",
            }

            result = self.tool_service.create_event(
                tool=self.tool_definition, payload=payload, runner=self.runner
            )

        self.assertEqual(result.get("calendar_event_id"), "evt-999")
