from math import floor, ceil
from statistics import mean
from typing import List, Optional

from odoo import api, fields, models


class MCPToolMetricsService(models.AbstractModel):
    _name = "llm.mcp.tool.metrics.service"
    _description = "MCP Tool Metrics Service"

    @staticmethod
    def _percentile(samples: List[int], percentile: float) -> int:
        if not samples:
            return 0
        ordered = sorted(samples)
        k = (len(ordered) - 1) * (percentile / 100.0)
        f = floor(k)
        c = ceil(k)
        if f == c:
            return int(ordered[int(k)])
        return int(ordered[f] + (ordered[c] - ordered[f]) * (k - f))

    @api.model
    def _window_domain(self, tool, window_minutes: Optional[int] = 1440):
        domain = [("tool_id", "=", tool.id)]
        if window_minutes:
            start_at = fields.Datetime.subtract(fields.Datetime.now(), minutes=window_minutes)
            domain.append(("start_time", ">=", start_at))
        return domain

    @api.model
    def collect(self, tool, window_minutes: Optional[int] = 1440):
        """Return success/failure/latency metrics plus a health score for a tool."""

        invocations = (
            self.env["llm.mcp.invocation.record"].sudo().search(self._window_domain(tool, window_minutes))
        )
        invocations = invocations.sorted(lambda r: r.start_time or fields.Datetime.now(), reverse=True)

        success_count = len(invocations.filtered(lambda r: r.status == "success"))
        failure_count = len(invocations.filtered(lambda r: r.status == "failed"))
        timeout_count = len(invocations.filtered(lambda r: r.timeout_flag))
        total_count = len(invocations)

        latencies = [rec.latency_ms for rec in invocations if rec.latency_ms]
        avg_latency_ms = int(mean(latencies)) if latencies else 0
        p95_latency_ms = self._percentile(latencies, 95) if latencies else 0

        success_rate = (success_count / total_count) if total_count else 1.0
        failure_rate = (failure_count / total_count) if total_count else 0.0
        timeout_rate = (timeout_count / total_count) if total_count else 0.0

        metrics = {
            "tool_id": tool.id,
            "window_minutes": window_minutes,
            "total_count": total_count,
            "success_count": success_count,
            "failure_count": failure_count,
            "timeout_count": timeout_count,
            "success_rate": round(success_rate, 4),
            "failure_rate": round(failure_rate, 4),
            "timeout_rate": round(timeout_rate, 4),
            "avg_latency_ms": avg_latency_ms,
            "p95_latency_ms": p95_latency_ms,
            "last_invocation_at": invocations[:1].start_time if invocations else None,
        }

        metrics["health_score"] = self.compute_health_score(metrics)
        return metrics

    @api.model
    def compute_health_score(
        self,
        metrics,
        target_success_rate: float = 0.98,
        latency_slo_ms: int = 2000,
    ) -> float:
        """Combine success, availability, and latency into a 0-100 health score."""

        success_rate = metrics.get("success_rate", 0.0)
        success_score = min(success_rate / target_success_rate, 1.0) if target_success_rate else success_rate

        p95 = metrics.get("p95_latency_ms") or 0
        latency_score = 1.0 if p95 <= latency_slo_ms else max(0.0, latency_slo_ms / float(p95))

        total = metrics.get("total_count", 0)
        timeout_count = metrics.get("timeout_count", 0)
        availability_score = max(0.0, 1 - (timeout_count / float(total))) if total else 1.0

        weighted = (success_score * 0.6) + (latency_score * 0.25) + (availability_score * 0.15)
        return round(weighted * 100, 2)
