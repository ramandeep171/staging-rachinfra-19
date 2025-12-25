import re
from typing import Any, Dict, Optional

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SendWhatsAppMessageTool(models.AbstractModel):
    _name = "llm.tool.whatsapp"
    _description = "Send WhatsApp Message Tool"

    REQUIRED_FIELDS = {"recipient_number", "message_body"}

    @api.model
    def _resolve_tool(self, tool: Optional[models.Model | str]):
        if isinstance(tool, str):
            tool = (
                self.env["llm.tool.definition"].sudo().search([("name", "=", tool)], limit=1)
            )
        if not tool or tool._name != "llm.tool.definition":
            raise UserError(_("WhatsApp tool definition not found."))
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
            raise UserError(_("No remote API runner configured for WhatsApp messages."))
        if runner.runner_type != "remote_api":
            raise ValidationError(_("WhatsApp tool requires a remote API runner."))
        return runner

    @api.model
    def _ensure_consent(self, tool, user=None):
        handler = self.env["llm.mcp.consent.handler"]
        result = handler.request_consent(tool, user=user)
        if result.get("status") != "granted":
            raise UserError(result.get("message") or _("Consent is required to send WhatsApp messages."))
        ledger_id = result.get("ledger_id")
        return self.env["llm.mcp.consent.ledger"].browse(ledger_id) if ledger_id else None

    @staticmethod
    def _validate_recipient(recipient: str):
        if not recipient or not re.match(r"^\+?\d{6,}$", recipient):
            raise ValidationError(_("Recipient number is invalid for WhatsApp delivery."))

    @api.model
    def _prepare_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        missing = self.REQUIRED_FIELDS - set(payload.keys())
        if missing:
            raise ValidationError(
                _("Missing required fields: %s") % ", ".join(sorted(missing))
            )
        self._validate_recipient(payload.get("recipient_number"))
        return {
            "recipient_number": payload.get("recipient_number"),
            "message_body": payload.get("message_body"),
            "media_url": payload.get("media_url"),
        }

    @api.model
    def send_message(
        self,
        tool: Optional[models.Model | str] = None,
        payload: Optional[Dict[str, Any]] = None,
        runner: Optional[models.Model] = None,
        user: Optional[models.Model] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = (user or self.env.user).sudo()
        tool = self._resolve_tool(tool or "send_whatsapp_message")
        tool.validate_payload(payload or {})

        consent_ledger = self._ensure_consent(tool, user=user)
        runner = self._resolve_runner(runner)
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()

        try:
            prepared_payload = self._prepare_payload(payload or {})
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
                "status": result.get("status", "sent"),
                "message_id": result.get("message_id"),
                "error_code": result.get("error_code"),
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
