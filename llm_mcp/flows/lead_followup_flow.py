from datetime import timedelta
from typing import Any, Dict, Optional

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LeadFollowupFlow(models.AbstractModel):
    _name = "llm.flow.lead_followup"
    _description = "Lead Follow-up Flow"

    REQUIRED_FIELDS = {"lead_id", "message_body", "followup_time"}

    @api.model
    def _resolve_tool(self, tool: Optional[models.Model | str]):
        if isinstance(tool, str):
            tool = (
                self.env["llm.tool.definition"].sudo().search([("name", "=", tool)], limit=1)
            )
        if not tool or tool._name != "llm.tool.definition":
            raise UserError(_("Lead follow-up flow definition not found."))
        return tool.sudo()

    @api.model
    def _resolve_runner(self, runner: Optional[models.Model] = None):
        runner = runner.sudo() if runner else None
        if runner and runner._name != "llm.mcp.command.runner":
            raise ValidationError(_("Runner must be an MCP command runner."))

        if runner is None:
            runner = self.env["llm.mcp.command.runner"].sudo().search(
                [("enabled", "=", True)], order="CASE WHEN type='local_agent' THEN 0 ELSE 1 END, id", limit=1
            )
        if not runner:
            raise UserError(_("No command runner configured for lead follow-up flow."))
        return runner

    @staticmethod
    def _validate_attendees(attendees):
        validated = []
        for attendee in attendees or []:
            email = attendee
            if isinstance(attendee, dict):
                email = attendee.get("email")
            if not email or "@" not in str(email):
                raise ValidationError(_("Attendee email is invalid."))
            validated.append(str(email))
        return validated

    @api.model
    def _prepare_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        missing = self.REQUIRED_FIELDS - set(payload.keys())
        if missing:
            raise ValidationError(_("Missing required fields: %s") % ", ".join(sorted(missing)))

        try:
            followup_dt = fields.Datetime.from_string(payload.get("followup_time"))
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(_("Invalid follow-up datetime: %s") % payload.get("followup_time")) from exc

        duration = payload.get("duration_minutes") or 60
        if not isinstance(duration, int) or duration <= 0:
            raise ValidationError(_("Duration must be a positive integer (minutes)."))

        end_dt = followup_dt + timedelta(minutes=duration)

        attendees = self._validate_attendees(payload.get("attendees"))

        return {
            "lead_id": payload.get("lead_id"),
            "message_body": payload.get("message_body"),
            "followup_time": fields.Datetime.to_string(followup_dt),
            "end_time": fields.Datetime.to_string(end_dt),
            "attendees": attendees,
            "location": payload.get("location"),
            "media_url": payload.get("media_url"),
        }

    @api.model
    def _fetch_lead(self, lead_id: int):
        lead = self.env["res.partner"].sudo().browse(lead_id)
        if not lead or not lead.exists():
            raise ValidationError(_("Lead record was not found."))
        return lead

    @api.model
    def _tool_by_name(self, name: str):
        return (
            self.env["llm.tool.definition"].sudo().search([("name", "=", name)], limit=1)
        )

    @api.model
    def run_flow(
        self,
        tool: Optional[models.Model | str] = None,
        payload: Optional[Dict[str, Any]] = None,
        runner: Optional[models.Model] = None,
        user: Optional[models.Model] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = (user or self.env.user).sudo()
        tool_def = self._resolve_tool(tool or "lead_followup_flow")
        tool_def.validate_payload(payload or {})

        runner = self._resolve_runner(runner)
        payload = self._prepare_payload(payload or {})

        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()

        invocation = invocation_model.log_invocation(
            tool_version=tool_def.latest_version_id,
            runner=runner,
            params=payload,
            status="pending",
            start_time=start_time,
            end_time=start_time,
            session_id=session_id,
            event_details={"step": "flow_start"},
        )

        results: Dict[str, Any] = {"flow": tool_def.name}

        try:
            lead = self._fetch_lead(payload["lead_id"])
            lead_info = {
                "id": lead.id,
                "name": lead.name,
                "mobile": lead.mobile,
                "email": lead.email,
            }
            results["lead"] = lead_info
            invocation._log_event(
                "success", details={"step": "retrieve_lead", "lead_id": lead.id}
            )

            whatsapp_tool_def = self._tool_by_name("send_whatsapp_message")
            calendar_tool_def = self._tool_by_name("create_google_calendar_event")

            if not whatsapp_tool_def or not calendar_tool_def:
                raise UserError(
                    _("WhatsApp or Calendar tool definitions are missing for the flow."),
                )

            whatsapp_result: Dict[str, Any]
            if lead.mobile:
                whatsapp_service = self.env["llm.tool.whatsapp"].with_context(
                    parent_invocation=invocation.id
                )
                whatsapp_result = whatsapp_service.send_message(
                    tool=whatsapp_tool_def,
                    payload={
                        "recipient_number": lead.mobile,
                        "message_body": payload["message_body"],
                        "media_url": payload.get("media_url"),
                    },
                    runner=None,
                    user=user,
                    session_id=session_id,
                )
                results["whatsapp"] = {"skipped": False, **whatsapp_result}
            else:
                results["whatsapp"] = {
                    "skipped": True,
                    "reason": "missing_mobile",
                }
                invocation._log_event(
                    "warning",
                    details={"step": "send_whatsapp_message", "reason": "missing_mobile"},
                    severity="warning",
                    system_flagged=True,
                )

            calendar_service = self.env["llm.tool.calendar_event"].with_context(
                parent_invocation=invocation.id
            )
            calendar_result = calendar_service.create_event(
                tool=calendar_tool_def,
                payload={
                    "title": _("Follow-up with %s") % (lead.name or lead.display_name),
                    "start_datetime": payload["followup_time"],
                    "end_datetime": payload["end_time"],
                    "attendees": payload.get("attendees") or lead.email and [lead.email] or [],
                    "location": payload.get("location"),
                    "reminders": [],
                },
                runner=None,
                user=user,
                session_id=session_id,
            )
            results["calendar"] = calendar_result

            end_time = fields.Datetime.now()
            invocation.write(
                {
                    "status": "success",
                    "end_time": end_time,
                    "result_json": results,
                }
            )
            invocation._log_event("success", details={"step": "flow_complete"})
            return results
        except Exception as exc:  # noqa: BLE001
            end_time = fields.Datetime.now()
            invocation.write(
                {
                    "status": "failed",
                    "end_time": end_time,
                    "exception_trace": str(exc),
                    "result_json": results,
                }
            )
            invocation._log_event(
                "failed",
                details={"error": str(exc)},
                severity="error",
                system_flagged=True,
            )
            raise
