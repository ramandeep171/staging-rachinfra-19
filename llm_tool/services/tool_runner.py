import traceback

from requests import Timeout

from odoo import api, fields, models


class LLMToolRunnerService(models.AbstractModel):
    _name = "llm.tool.runner.service"
    _description = "LLM Tool Runner Service"

    @api.model
    def dispatch(
        self,
        *,
        tool_version,
        runner,
        binding,
        payload=None,
        session_id=None,
        user=None,
        consent_ledger=None,
        consent_event_details=None,
        parent_invocation=None,
    ):
        payload = payload or {}
        user = (user or self.env.user).sudo()
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()
        invocation = invocation_model.log_invocation(
            tool_version=tool_version,
            runner=runner,
            params=payload,
            status="pending",
            start_time=start_time,
            end_time=start_time,
            consent_ledger=consent_ledger,
            session_id=session_id,
            parent_invocation=parent_invocation,
            event_details={"params": payload, "timeout": binding.timeout},
        )

        if consent_event_details is not None:
            invocation._log_event(
                "consent",
                details=consent_event_details,
                severity="info",
                system_flagged=False,
            )

        retry_manager = self.env["llm.mcp.retry.manager"]
        ledger_model = self.env["llm.mcp.consent.ledger"].sudo()
        redaction_engine = self.env["llm.tool.redaction.engine"]
        try:
            enforced_ledger = ledger_model.enforce_consent(
                tool_version.tool_id,
                user=user,
                context_payload={"session_id": session_id, "params": payload},
            )
            if enforced_ledger and enforced_ledger != consent_ledger:
                consent_ledger = enforced_ledger
                invocation.write({"consent_ledger_id": enforced_ledger.id})

            result = retry_manager.execute_with_retry(
                tool=tool_version.tool_id,
                runner=runner,
                binding=binding,
                payload=payload,
                invocation=invocation,
                timeout=binding.timeout,
            )
            end_time = fields.Datetime.now()
            redacted_result = self.env["llm.tool.redaction.engine"].redact_payload(
                tool_version.tool_id, result
            )
            invocation.write(
                {
                    "status": "success",
                    "end_time": end_time,
                    "result_json": redacted_result,
                    "result_redacted": redacted_result,
                }
            )
            invocation._log_event("success", details=redacted_result, severity="info")
            return result
        except (Timeout, TimeoutError) as exc:  # noqa: BLE001 - propagate for visibility
            end_time = fields.Datetime.now()
            redacted_error = redaction_engine.redact_payload(
                tool_version.tool_id, {"error": str(exc), "timeout": binding.timeout}
            )
            invocation.write(
                {
                    "status": "failed",
                    "end_time": end_time,
                    "timeout_flag": True,
                    "exception_trace": traceback.format_exc(),
                    "result_json": redacted_error,
                    "result_redacted": redacted_error,
                }
            )
            invocation._log_event(
                "timeout",
                details=redacted_error,
                severity="error",
                system_flagged=True,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - propagate for visibility
            end_time = fields.Datetime.now()
            redacted_error = redaction_engine.redact_payload(
                tool_version.tool_id, {"error": str(exc)}
            )
            invocation.write(
                {
                    "status": "failed",
                    "end_time": end_time,
                    "exception_trace": traceback.format_exc(),
                    "result_json": redacted_error,
                    "result_redacted": redacted_error,
                }
            )
            invocation._log_event(
                "failed",
                details=redacted_error,
                severity="error",
                system_flagged=True,
            )
            raise
