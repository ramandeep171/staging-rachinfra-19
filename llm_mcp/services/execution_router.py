from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError as JSONSchemaError

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MCPExecutionRouter(models.AbstractModel):
    _name = "llm.mcp.execution.router"
    _description = "MCP Execution Router"
    _max_call_depth = 8
    _max_same_tool_repeats = 3

    @staticmethod
    def _error_envelope(code, message, details=None):
        return {"error": {"code": code, "message": message, "details": details or {}}}

    @staticmethod
    def _normalize_schema(schema):
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}, "required": []}
        if not schema:
            return {"type": "object", "properties": {}, "required": []}
        return schema

    def _resolve_invocation(self, parent_invocation):
        if not parent_invocation:
            return None
        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        if isinstance(parent_invocation, int):
            parent_invocation = invocation_model.browse(parent_invocation)
        if hasattr(parent_invocation, "id") and parent_invocation.exists():
            return parent_invocation
        return None

    def _build_call_chain(self, parent_invocation):
        chain = []
        seen = set()
        current = self._resolve_invocation(parent_invocation)
        while current and current.id not in seen:
            chain.append(current)
            seen.add(current.id)
            if len(chain) >= (self._max_call_depth * 2):
                break
            current = current.parent_invocation_id
        return chain

    def _log_loop_guard(self, invocation, code, details):
        if not invocation:
            return
        try:
            invocation._log_event(
                "failed",
                details={"loop_guard": code, **(details or {})},
                severity="error",
                system_flagged=True,
            )
        except Exception:  # noqa: BLE001 - best-effort logging
            return

    def _enforce_recursion_limits(self, tool, parent_invocation):
        chain = self._build_call_chain(parent_invocation)
        depth = len(chain) + 1

        if self._max_call_depth and depth > self._max_call_depth:
            details = {
                "depth": depth,
                "max_depth": self._max_call_depth,
                "tool": tool.name,
                "call_chain": [inv.tool_id.name for inv in chain[:5]],
            }
            self._log_loop_guard(parent_invocation, "MCP_CALL_DEPTH_EXCEEDED", details)
            return self._error_envelope(
                "MCP_CALL_DEPTH_EXCEEDED",
                _("Tool call depth limit exceeded; execution blocked."),
                details=details,
            )

        same_tool_streak = 0
        for inv in chain:
            if inv.tool_id and inv.tool_id.id == tool.id:
                same_tool_streak += 1
            else:
                break

        if self._max_same_tool_repeats and same_tool_streak >= self._max_same_tool_repeats:
            details = {
                "repeat_count": same_tool_streak + 1,
                "max_repeats": self._max_same_tool_repeats,
                "tool": tool.name,
            }
            self._log_loop_guard(parent_invocation, "MCP_TOOL_REPEAT_GUARD", details)
            return self._error_envelope(
                "MCP_TOOL_REPEAT_GUARD",
                _("Repeated calls to the same tool were blocked to prevent loops."),
                details=details,
            )

        return None

    def _validate_params_against_schema(
        self, tool, version, params, binding, runner, session_id=None
    ):
        schema = self._normalize_schema(tool.schema_json)
        try:
            validator = Draft7Validator(schema)
        except JSONSchemaError as exc:  # developer error, do not expose internals
            invocation_model = self.env["llm.mcp.invocation.record"].sudo()
            now = fields.Datetime.now()
            invocation = invocation_model.log_invocation(
                tool_version=version,
                runner=runner,
                params=params,
                status="failed",
                start_time=now,
                end_time=now,
                session_id=session_id,
                event_details={
                    "schema_error": "invalid_tool_schema",
                    "details": str(exc),
                    "binding_id": binding.id,
                },
            )
            invocation._log_event(
                "failed",
                details={"schema_error": "invalid_tool_schema"},
                severity="error",
                system_flagged=True,
            )
            return self._error_envelope(
                "MCP_SCHEMA_INVALID",
                _("Tool schema is invalid; execution blocked."),
            )

        errors = sorted(validator.iter_errors(params), key=lambda e: e.path)
        if not errors:
            return None

        formatted_errors = []
        for error in errors:
            formatted_errors.append(
                {
                    "path": list(error.absolute_path),
                    "message": error.message,
                    "validator": error.validator,
                }
            )

        invocation_model = self.env["llm.mcp.invocation.record"].sudo()
        start_time = fields.Datetime.now()
        invocation = invocation_model.log_invocation(
            tool_version=version,
            runner=runner,
            params=params,
            status="failed",
            start_time=start_time,
            end_time=start_time,
            session_id=session_id,
            event_details={"validation_errors": formatted_errors, "binding_id": binding.id},
        )
        invocation._log_event(
            "failed",
            details={"validation_errors": formatted_errors},
            severity="error",
            system_flagged=True,
        )

        return self._error_envelope(
            "MCP_SCHEMA_VALIDATION_FAILED",
            _("Tool parameters failed schema validation."),
            details={"errors": formatted_errors},
        )

    def _enforce_rate_limit(self, token, tool, binding):
        limit = binding.rate_limit or 0
        if not limit:
            return True, {"limit": 0}

        limiter = self.env["llm.mcp.rate.limiter"].sudo()
        return limiter.increment_and_check(token or "", tool.id, binding.id, limit)

    @api.model
    def route(
        self, session_id, tool_key, params=None, user=None, parent_invocation=None, token=None
    ):
        params = params or {}
        user = (user or self.env.user).sudo()

        invocation_model = self.env["llm.mcp.invocation.record"].sudo()

        resolver = self.env["llm.mcp.binding.resolver"]
        resolution = resolver.resolve(tool_key)
        tool = resolution["tool"].sudo()
        runner = resolution["runner"]
        version = resolution["version"]
        binding = resolution["binding"]

        parent_invocation_rec = self._resolve_invocation(parent_invocation)

        permission_guard = self.env["llm.tool.permission.guard"]
        permission_guard.ensure_can_call(tool, user=user, session_id=session_id)

        loop_guard_error = self._enforce_recursion_limits(tool, parent_invocation_rec)
        if loop_guard_error:
            return loop_guard_error

        allowed, rate_meta = self._enforce_rate_limit(token, tool, binding)
        if not allowed:
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
                parent_invocation=parent_invocation_rec,
                event_details={
                    "rate_limited": True,
                    "binding_id": binding.id,
                    "rate_limit": rate_meta,
                },
            )
            invocation._log_event(
                "failed",
                details={
                    "rate_limited": True,
                    "binding_id": binding.id,
                    "rate_limit": rate_meta,
                },
                severity="error",
                system_flagged=True,
            )
            from werkzeug.exceptions import TooManyRequests

            raise TooManyRequests(
                "Rate limit exceeded"
                + (
                    f" (resets at {rate_meta.get('reset_at')})"
                    if rate_meta and rate_meta.get("reset_at")
                    else ""
                )
            )

        policy_enforcer = self.env["llm.mcp.policy.enforcer"]
        consent_decision = policy_enforcer.enforce_consent_policy(
            user=user, tool=tool, session_id=session_id
        )

        validation_error = self._validate_params_against_schema(
            tool, version, params, binding, runner, session_id=session_id
        )
        if validation_error:
            return validation_error

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
                parent_invocation=parent_invocation_rec,
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
        try:
            result = runner_service.dispatch(
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
                parent_invocation=parent_invocation_rec,
            )
        except TimeoutError:
            now = fields.Datetime.now()
            invocation = invocation_model.log_invocation(
                tool_version=version,
                runner=runner,
                params=payload,
                status="failed",
                start_time=now,
                end_time=now,
                consent_ledger=consent_decision.get("ledger"),
                session_id=session_id,
                parent_invocation=parent_invocation_rec,
                event_details={
                    "timeout": True,
                    "timeout_seconds": binding.timeout,
                    "binding_id": binding.id,
                },
                timeout_flag=True,
            )
            invocation._log_event(
                "timeout",
                details={
                    "timeout": True,
                    "timeout_seconds": binding.timeout,
                    "binding_id": binding.id,
                },
                severity="error",
                system_flagged=True,
            )
            return self._error_envelope(
                "MCP_EXEC_TIMEOUT",
                _("Tool execution timed out."),
                details={"timeout": binding.timeout},
            )
        except Exception as exc:  # noqa: BLE001 - normalize to safe envelope
            now = fields.Datetime.now()
            invocation = invocation_model.log_invocation(
                tool_version=version,
                runner=runner,
                params=payload,
                status="failed",
                start_time=now,
                end_time=now,
                consent_ledger=consent_decision.get("ledger"),
                session_id=session_id,
                parent_invocation=parent_invocation_rec,
                event_details={"error": str(exc), "binding_id": binding.id},
            )
            invocation._log_event(
                "failed",
                details={"error": str(exc), "binding_id": binding.id},
                severity="error",
                system_flagged=True,
            )
            return self._error_envelope(
                "MCP_EXEC_ERROR",
                _("Tool execution failed."),
                details={"error": str(exc), "binding_id": binding.id},
            )

        packer = self.env["llm.mcp.context.packer"].sudo()
        return packer.pack_tool_result(
            result,
            tool=tool,
            binding=binding,
            session_id=session_id,
        )
