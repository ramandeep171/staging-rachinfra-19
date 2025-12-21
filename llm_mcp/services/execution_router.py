from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MCPExecutionRouter(models.AbstractModel):
    _name = "llm.mcp.execution.router"
    _description = "MCP Execution Router"

    @api.model
    def route(self, session_id, tool_key, params=None, user=None, parent_invocation=None):
        params = params or {}
        user = (user or self.env.user).sudo()

        resolver = self.env["llm.mcp.binding.resolver"]
        resolution = resolver.resolve(tool_key)
        tool = resolution["tool"].sudo()
        runner = resolution["runner"]
        version = resolution["version"]
        binding = resolution["binding"]

        permission_guard = self.env["llm.tool.permission.guard"]
        permission_guard.ensure_can_call(tool, user=user, session_id=session_id)

        policy_enforcer = self.env["llm.mcp.policy.enforcer"]
        consent_decision = policy_enforcer.enforce_consent_policy(
            user=user, tool=tool, session_id=session_id
        )

        payload = dict(params)
        payload.setdefault("executor_path", binding.executor_path)
        payload.setdefault("timeout", binding.timeout)

        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()
        status = "pending" if consent_decision.get("status") == "ALLOW" else "failed"
        invocation = invocation_model.log_invocation(
            tool_version=version,
            runner=runner,
            params=payload,
            status=status,
            start_time=start_time,
            end_time=start_time,
            consent_ledger=consent_decision.get("ledger"),
            session_id=session_id,
            parent_invocation=parent_invocation,
            event_details={
                "policy_status": consent_decision.get("status"),
                "message": consent_decision.get("message"),
                "enforced": consent_decision.get("enforced", True),
            },
        )

        invocation._log_event(
            "consent",
            details={
                "policy_status": consent_decision.get("status"),
                "message": consent_decision.get("message"),
                "enforced": consent_decision.get("enforced", True),
            },
            severity="info"
            if consent_decision.get("status") == "ALLOW"
            else "error",
            system_flagged=consent_decision.get("status") != "ALLOW",
        )

        if consent_decision.get("status") != "ALLOW":
            raise UserError(
                consent_decision.get("message") or _("Consent is required for this tool.")
            )

        retry_manager = self.env["llm.mcp.retry.manager"]

        try:
            result = retry_manager.execute_with_retry(
                tool=tool,
                runner=runner,
                binding=binding,
                payload=payload,
                invocation=invocation,
            )
            end_time = fields.Datetime.now()
            redacted_result = self.env[
                "llm.tool.redaction.engine"
            ].redact_payload(tool, result)
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
