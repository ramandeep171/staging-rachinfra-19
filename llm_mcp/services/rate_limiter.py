import hashlib
import logging
from datetime import timedelta
import importlib.util

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MCPRateLimiter(models.AbstractModel):
    _name = "llm.mcp.rate.limiter"
    _description = "Distributed MCP Rate Limiter"

    _window_ttl_seconds = 70

    def _token_fingerprint(self, token: str) -> str:
        material = token or ""
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    def _build_bucket_key(self, token: str, tool_id: int, binding_id: int, minute_epoch: int):
        token_fp = self._token_fingerprint(token)
        return f"rl:{token_fp}:{tool_id}:{binding_id}:{minute_epoch}"

    def _redis_client(self):
        param_model = self.env["ir.config_parameter"].sudo()
        redis_url = param_model.get_param("llm_mcp.redis_url")
        if not redis_url:
            return None

        if not importlib.util.find_spec("redis"):
            _logger.warning("Redis URL configured but redis-py is not installed; using DB fallback")
            return None

        import redis  # type: ignore

        return redis.Redis.from_url(redis_url)

    def _increment_redis(self, client, bucket_key):
        try:
            pipe = client.pipeline()
            pipe.incr(bucket_key)
            pipe.expire(bucket_key, self._window_ttl_seconds)
            count, _ = pipe.execute()
            return int(count)
        except Exception:  # noqa: BLE001 - fallback to DB when Redis is unavailable
            _logger.exception("Redis rate limiting failed; falling back to DB for %s", bucket_key)
            return None

    @api.model
    def increment_and_check(self, token: str, tool_id: int, binding_id: int, limit: int):
        if not limit:
            return True, {"limit": 0}

        now = fields.Datetime.now()
        window_start = now.replace(second=0, microsecond=0)
        minute_epoch = int(window_start.timestamp())
        bucket_key = self._build_bucket_key(token, tool_id, binding_id, minute_epoch)

        client = self._redis_client()
        if client:
            count = self._increment_redis(client, bucket_key)
        else:
            count = None

        reset_at = window_start + timedelta(seconds=self._window_ttl_seconds)
        backend = "redis" if client else "db"

        if count is None:
            window_model = self.env["llm.mcp.rate.limit.window"].sudo()
            count, reset_at = window_model.increment(
                bucket_key, window_start, self._window_ttl_seconds
            )
            backend = "db"

        meta = {
            "bucket_key": bucket_key,
            "count": count,
            "limit": limit,
            "reset_at": reset_at,
            "backend": backend,
        }
        return count <= limit, meta
