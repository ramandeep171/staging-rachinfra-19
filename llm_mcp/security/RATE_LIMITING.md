# MCP Distributed Rate Limiting

## Key Design
- **Backend preference:** Redis (atomic `INCR` + `EXPIRE`) when `ir.config_parameter` `llm_mcp.redis_url` is set; otherwise fallback to a DB window table for portability.
- **Key shape:** `rl:{token_fp}:{tool_id}:{binding_id}:{minute_epoch}` where `token_fp=sha256(token)[:24]` to avoid storing raw secrets.
- **TTL:** 70s per minute window to tolerate clock skew and late writes.
- **Scope:** Token/user fingerprint + tool + binding per minute => horizontally safe, unique across workers.
- **Metadata:** Track backend, count, and reset time to surface in error responses/audit logs.

## Flow (pseudocode)
```python
minute = now.replace(second=0, microsecond=0)
key = f"rl:{sha256(token)[:24]}:{tool_id}:{binding_id}:{int(minute.timestamp())}"
if redis_url:
    count = redis.incr(key)
    redis.expire(key, 70)
else:
    count, reset_at = db.increment(key, window_start=minute, ttl=70)
if count > limit:
    raise TooManyRequests(meta={"reset_at": reset_at, "backend": backend})
```

## Graceful Rejects
- Respond with `429` and include reset time hint; log `rate_limit` metadata on the invocation record for audit trails.
- DB path opportunistically purges expired windows to prevent unbounded growth without background jobs.
