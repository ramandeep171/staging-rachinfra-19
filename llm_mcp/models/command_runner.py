import json

import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class LLMCommandRunner(models.Model):
    _name = "llm.mcp.command.runner"
    _description = "LLM MCP Command Runner"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    server_id = fields.Many2one(
        "llm.mcp.server",
        string="MCP Server",
        required=True,
        ondelete="cascade",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    runner_type = fields.Selection(
        [
            ("local_agent", "Local Agent"),
            ("python_subprocess", "Python Subprocess"),
            ("remote_api", "Remote API"),
            ("http", "HTTP"),
            ("websocket", "Websocket"),
        ],
        required=True,
        default="local_agent",
        tracking=True,
    )
    entrypoint = fields.Char(
        required=True,
        help="Command path, module path or endpoint URL depending on runner type.",
    )
    auth_headers = fields.Json(default=dict, help="Optional auth headers for remote API calls.")
    retry_policy = fields.Json(
        default=lambda self: {"retries": 0},
        help="Retry configuration, e.g. {'retries': 2}.",
    )
    circuit_breaker = fields.Boolean(
        default=False,
        help="If enabled, execution is blocked when the breaker is open or disabled manually.",
    )
    sandbox_mode = fields.Boolean(default=True)
    enabled = fields.Boolean(default=True)
    allowed_tool_ids = fields.Many2many(
        "llm.tool",
        string="Allowed Tools",
        help="Limit this runner to a specific tool set. Empty means no restriction.",
    )

    @api.constrains("entrypoint")
    def _check_entrypoint(self):
        for runner in self:
            if not runner.entrypoint:
                raise ValidationError(_("Entrypoint is required for command runners."))

    @api.constrains("retry_policy")
    def _check_retry_policy(self):
        for runner in self:
            policy = runner.retry_policy or {}
            if not isinstance(policy, dict):
                raise ValidationError(_("Retry policy must be a dictionary."))
            retries = policy.get("retries", 0)
            if not isinstance(retries, int) or retries < 0:
                raise ValidationError(_("Retry count must be a non-negative integer."))

    def _ensure_tool_allowed(self, tool):
        self.ensure_one()
        if self.allowed_tool_ids and tool not in self.allowed_tool_ids:
            raise ValidationError(
                _("Tool %s is not allowed for runner %s")
                % (tool.display_name, self.display_name)
            )

    def _execute_payload(self, payload, timeout=None):
        """Placeholder for actual execution; override or extend when wiring runners."""
        if self.runner_type in {"remote_api", "http", "websocket"}:
            if not self.entrypoint:
                raise UserError(_("Remote API runner requires an entrypoint URL."))

            headers = self.auth_headers or {}
            response = requests.post(
                self.entrypoint,
                json=payload or {},
                headers=headers,
                timeout=timeout,
            )

            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text}

            if response.status_code >= 400:
                raise UserError(
                    body.get("error")
                    or _("Remote API call failed with status %s") % response.status_code
                )

            return body

        if payload.get("force_fail"):
            raise UserError("Simulated failure for testing")
        return {"status": "ok", "payload": payload}

    def run_command(self, tool, payload=None, timeout=None):
        self.ensure_one()
        payload = payload or {}

        if not self.enabled:
            raise UserError(_("Runner %s is disabled") % self.display_name)
        if self.circuit_breaker:
            raise UserError(_("Runner %s is blocked by circuit breaker") % self.display_name)

        self._ensure_tool_allowed(tool)

        policy = self.retry_policy or {}
        retries = policy.get("retries", 0)

        attempt = 0
        while True:
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._execute_payload, payload, timeout)
                    try:
                        return future.result(timeout=timeout)
                    except FuturesTimeout as exc:
                        future.cancel()
                        raise TimeoutError(
                            _("Runner exceeded timeout of %s seconds") % (timeout or "?"),
                        ) from exc
            except Exception as exc:
                attempt += 1
                if attempt > retries:
                    raise
                # loop to retry
                continue

    def action_test_endpoint(self):
        self.ensure_one()
        try:
            tool = self.allowed_tool_ids[:1]
            if not tool:
                tool = self.env["llm.tool"].search([], limit=1)
            if not tool:
                raise UserError(_("No tool available to test this runner."))
            result = self.run_command(tool, {"ping": True})
            message = result if isinstance(result, str) else json.dumps(result)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Endpoint reachable"),
                    "message": message,
                    "sticky": False,
                },
            }
        except Exception as exc:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Endpoint test failed"),
                    "message": str(exc),
                    "type": "danger",
                    "sticky": False,
                },
            }
