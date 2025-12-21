import time

from odoo import api, models


class MCPRetryManager(models.AbstractModel):
    _name = "llm.mcp.retry.manager"
    _description = "MCP Retry Manager"

    def _compute_delay(self, interval, attempt, strategy):
        interval = max(interval or 0, 0)
        if not interval:
            return 0
        if strategy == "exponential":
            return interval * (2 ** (attempt - 1))
        return interval

    def _sleep(self, delay):
        if delay > 0:
            time.sleep(delay)

    @api.model
    def execute_with_retry(self, tool, runner, binding, payload, invocation):
        max_retries = max(binding.max_retries or 0, 0)
        interval = max(binding.retry_interval or 0, 0)
        strategy = binding.retry_strategy or "fixed"

        attempt = 0
        while True:
            try:
                return runner.run_command(tool, payload)
            except Exception as exc:  # noqa: BLE001 - propagate for visibility
                if attempt >= max_retries:
                    invocation._log_event(
                        "retry_exhausted",
                        details={"attempt": attempt, "error": str(exc)},
                        severity="error",
                        system_flagged=True,
                    )
                    raise

                attempt += 1
                delay = self._compute_delay(interval, attempt, strategy)
                invocation._log_event(
                    "retry",
                    details={
                        "attempt": attempt,
                        "delay": delay,
                        "strategy": strategy,
                        "error": str(exc),
                    },
                    severity="warning",
                    system_flagged=True,
                )
                self._sleep(delay)
