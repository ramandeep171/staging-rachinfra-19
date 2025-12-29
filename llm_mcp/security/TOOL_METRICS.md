# MCP Tool Reliability Metrics

This module surfaces per-tool reliability signals so MCP operators can spot broken or slow tools before they impact LLM runs.

## Metrics Collected (rolling window)
- `total_count`: total invocations observed in the window (default: last 24h).
- `success_count` / `failure_count`: completed invocations partitioned by status.
- `timeout_count`: failures flagged as timeouts.
- `success_rate`, `failure_rate`, `timeout_rate`: normalized ratios for the window.
- `avg_latency_ms`: arithmetic mean latency across invocations with timing data.
- `p95_latency_ms`: 95th percentile latency to expose tail performance.
- `last_invocation_at`: most recent invocation timestamp for the tool.

## Health Score
The health score compresses reliability into a 0–100 signal:

```
success_score     = min(success_rate / target_success_rate, 1.0)
latency_score     = 1.0 when p95_latency_ms <= latency_slo_ms
                    else max(0, latency_slo_ms / p95_latency_ms)
availability      = 1 - (timeout_count / total_count) when total_count > 0 else 1.0

health_score      = (0.60 * success_score)
                  + (0.25 * latency_score)
                  + (0.15 * availability)
```

Defaults: `target_success_rate=0.98`, `latency_slo_ms=2000`. Scores degrade when the tool fails frequently, exceeds the latency SLO, or times out.

## Usage
`env["llm.mcp.tool.metrics.service"].collect(tool, window_minutes=1440)` returns the metric bundle plus the computed `health_score` for dashboards, alerts, or circuit-breaker decisions.
