from datetime import datetime
from typing import Any, Dict, List, Optional

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CreateGoogleCalendarEventTool(models.AbstractModel):
    _name = "llm.tool.calendar_event"
    _description = "Create Google Calendar Event Tool"

    REQUIRED_FIELDS = {"title", "start_datetime", "end_datetime"}

    @api.model
    def _resolve_tool(self, tool: Optional[models.Model | str]):
        if isinstance(tool, str):
            tool = (
                self.env["llm.tool.definition"].sudo().search([("name", "=", tool)], limit=1)
            )
        if not tool or tool._name != "llm.tool.definition":
            raise UserError(_("Calendar event tool definition not found."))
        return tool.sudo()

    @api.model
    def _resolve_runner(self, runner: Optional[models.Model] = None):
        runner = runner.sudo() if runner else None
        if runner and runner._name != "llm.mcp.command.runner":
            raise ValidationError(_("Runner must be an MCP command runner."))

        if runner is None:
            runner = self.env["llm.mcp.command.runner"].sudo().search(
                [("type", "=", "remote_api"), ("enabled", "=", True)], limit=1
            )
        if not runner:
            raise UserError(_("No remote API runner configured for calendar events."))
        if runner.runner_type != "remote_api":
            raise ValidationError(_("Calendar tool requires a remote API runner."))
        return runner

    def _requires_consent(self, tool):
        tag_names = {tag.name.lower() for tag in tool.tag_ids}
        return "user-consent" in tag_names or bool(tool.mcp_consent_template_id)

    @api.model
    def _ensure_consent(self, tool, user=None):
        if not self._requires_consent(tool):
            return None
        handler = self.env["llm.mcp.consent.handler"]
        result = handler.request_consent(tool, user=user)
        if result.get("status") != "granted":
            raise UserError(result.get("message") or _("Consent is required to create events."))
        ledger_id = result.get("ledger_id")
        return self.env["llm.mcp.consent.ledger"].browse(ledger_id) if ledger_id else None

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        try:
            return fields.Datetime.from_string(value)
        except Exception as exc:  # noqa: BLE001 - surface parsing failure
            raise ValidationError(_("Invalid datetime format: %s") % value) from exc

    @staticmethod
    def _normalize_attendees(attendees: Optional[List[Any]]) -> List[Dict[str, str]]:
        normalized = []
        for attendee in attendees or []:
            email = attendee
            if isinstance(attendee, dict):
                email = attendee.get("email")
            if not email or "@" not in str(email):
                raise ValidationError(_("Attendee email is invalid."))
            normalized.append({"email": str(email)})
        return normalized

    @staticmethod
    def _normalize_reminders(reminders: Optional[List[Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for reminder in reminders or []:
            minutes = reminder
            if isinstance(reminder, dict):
                minutes = reminder.get("minutes")
            if minutes is None:
                continue
            if not isinstance(minutes, int) or minutes < 0:
                raise ValidationError(_("Reminder minutes must be a non-negative integer."))
            normalized.append({"minutes": minutes})
        return normalized

    @api.model
    def _prepare_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        missing = self.REQUIRED_FIELDS - set(payload.keys())
        if missing:
            raise ValidationError(_("Missing required fields: %s") % ", ".join(sorted(missing)))

        start_dt = self._parse_datetime(payload.get("start_datetime"))
        end_dt = self._parse_datetime(payload.get("end_datetime"))
        if end_dt <= start_dt:
            raise ValidationError(_("End datetime must be after start datetime."))

        attendees = self._normalize_attendees(payload.get("attendees"))
        reminders = self._normalize_reminders(payload.get("reminders"))

        prepared = {
            "title": payload.get("title"),
            "start_datetime": fields.Datetime.to_string(start_dt),
            "end_datetime": fields.Datetime.to_string(end_dt),
            "location": payload.get("location"),
            "attendees": attendees,
            "reminders": reminders,
        }
        return prepared

    def _check_idempotency(self, tool_version, payload):
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        redacted = invocation_model._redact_payload(tool_version.tool_id, payload)
        existing = invocation_model.search(
            [
                ("tool_version_id", "=", tool_version.id),
                ("status", "=", "success"),
            ],
            order="id desc",
        )
        for record in existing:
            try:
                if record.params_redacted == redacted:
                    raise ValidationError(
                        _("Duplicate calendar event payload detected; refusing duplicate creation."),
                    )
            except Exception:
                continue

    @api.model
    def create_event(
        self,
        tool: Optional[models.Model | str] = None,
        payload: Optional[Dict[str, Any]] = None,
        runner: Optional[models.Model] = None,
        user: Optional[models.Model] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = (user or self.env.user).sudo()
        tool = self._resolve_tool(tool or "create_google_calendar_event")
        tool.validate_payload(payload or {})

        consent_ledger = self._ensure_consent(tool, user=user)
        runner = self._resolve_runner(runner)
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()

        try:
            prepared_payload = self._prepare_payload(payload or {})
            self._check_idempotency(tool.latest_version_id, prepared_payload)
        except Exception as exc:  # noqa: BLE001 - log validation failure
            invocation = invocation_model.log_invocation(
                tool_version=tool.latest_version_id,
                runner=runner,
                params=payload or {},
                status="failed",
                start_time=start_time,
                end_time=start_time,
                consent_ledger=consent_ledger,
                session_id=session_id,
                event_details={"error": str(exc)},
            )
            invocation._log_event(
                "failed",
                details={"error": str(exc)},
                severity="error",
                system_flagged=True,
            )
            raise

        invocation = invocation_model.log_invocation(
            tool_version=tool.latest_version_id,
            runner=runner,
            params=prepared_payload,
            status="pending",
            start_time=start_time,
            end_time=start_time,
            consent_ledger=consent_ledger,
            session_id=session_id,
        )

        try:
            result = runner.run_command(self.env["llm.tool"], prepared_payload)
            end_time = fields.Datetime.now()
            invocation.write(
                {
                    "status": "success",
                    "end_time": end_time,
                    "result_json": result,
                }
            )
            invocation._log_event("success", details=result, severity="info")
            return {
                "status": result.get("status", "created"),
                "calendar_event_id": result.get("calendar_event_id"),
                "calendar_link": result.get("calendar_link"),
            }
        except Exception as exc:  # noqa: BLE001 - propagate for test visibility
            end_time = fields.Datetime.now()
            invocation.write(
                {
                    "status": "failed",
                    "end_time": end_time,
                    "exception_trace": str(exc),
                }
            )
            invocation._log_event(
                "failed",
                details={"error": str(exc)},
                severity="error",
                system_flagged=True,
            )
            raise
