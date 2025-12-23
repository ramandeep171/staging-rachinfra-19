from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MCPExecutionRouter(models.AbstractModel):
    _name = "llm.mcp.execution.router"
    _description = "MCP Execution Router"
    _rate_counters = {}

    @api.model
    def _rate_limit_key(self, token, tool, binding):
        return (token or "", tool.id, binding.id)

    def _enforce_rate_limit(self, token, tool, binding):
        limit = binding.rate_limit or 0
        if not limit:
            return True

        now = fields.Datetime.now()
        window_key = now.replace(second=0, microsecond=0)
        key = (self._rate_limit_key(token, tool, binding), window_key)
        count = self._rate_counters.get(key, 0) + 1
        self._rate_counters[key] = count
        if count > limit:
            return False
        return True

    @api.model
    def route(
        self, session_id, tool_key, params=None, user=None, parent_invocation=None, token=None
    ):
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

        if not self._enforce_rate_limit(token, tool, binding):
            invocation_model = self.env["llm.mcp.invocation.record"].sudo()
            start_time = fields.Datetime.now()
            invocation = invocation_model.log_invocation(
                tool_version=version,
                runner=runner,
                params=params,
                status="failed",
                start_time=start_time,
                end_time=start_time,
                consent_ledger=None,
                session_id=session_id,
                parent_invocation=parent_invocation,
                event_details={"rate_limited": True, "binding_id": binding.id},
            )
            invocation._log_event(
                "failed",
                details={"rate_limited": True, "binding_id": binding.id},
                severity="error",
                system_flagged=True,
            )
            from werkzeug.exceptions import TooManyRequests

            raise TooManyRequests("Rate limit exceeded")

        policy_enforcer = self.env["llm.mcp.policy.enforcer"]
        consent_decision = policy_enforcer.enforce_consent_policy(
            user=user, tool=tool, session_id=session_id
        )

        payload = dict(params)
        payload.setdefault("executor_path", binding.executor_path)
        payload.setdefault("timeout", binding.timeout)

        if consent_decision.get("status") != "ALLOW":
            invocation_model = self.env["llm.mcp.invocation.record"].sudo()
            start_time = fields.Datetime.now()
            invocation = invocation_model.log_invocation(
                tool_version=version,
                runner=runner,
                params=payload,
                status="failed",
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
                severity="error",
                system_flagged=True,
            )

            raise UserError(
                consent_decision.get("message") or _("Consent is required for this tool.")
            )

        runner_service = self.env["llm.tool.runner.service"]

        return runner_service.dispatch(
            tool_version=version,
            runner=runner,
            binding=binding,
            payload=payload,
            session_id=session_id,
            user=user,
            consent_ledger=consent_decision.get("ledger"),
            consent_event_details={
                "policy_status": consent_decision.get("status"),
                "message": consent_decision.get("message"),
                "enforced": consent_decision.get("enforced", True),
            },
            parent_invocation=parent_invocation,
        )
