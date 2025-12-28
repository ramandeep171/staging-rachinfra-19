import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)


class MCPRateLimitWindow(models.Model):
    _name = "llm.mcp.rate.limit.window"
    _description = "MCP Rate Limit Window"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    bucket_key = fields.Char(required=True, index=True)
    window_start = fields.Datetime(required=True, index=True)
    expires_at = fields.Datetime(required=True, index=True)
    count = fields.Integer(default=0)

    _sql_constraints = [
        (
            "llm_mcp_rate_limit_window_unique",
            "unique(company_id, bucket_key, window_start)",
            "Only one rate limit window per company and key is allowed.",
        )
    ]

    @api.model
    def increment(self, bucket_key, window_start, ttl_seconds):
        company = self.env.company or self.env.user.company_id
        if not company:
            company = self.env["res.company"].sudo().browse(self.env.context.get("force_company"))
        company_id = company.id if company else False

        now = fields.Datetime.now()
        expires_at = window_start + timedelta(seconds=ttl_seconds)

        # Opportunistically clean expired rows to keep the table small without a cron.
        self.purge_expired(now, company_id=company_id)

        self.env.cr.execute(
            """
            INSERT INTO llm_mcp_rate_limit_window
                (company_id, bucket_key, window_start, expires_at, count, create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
            ON CONFLICT (company_id, bucket_key, window_start)
            DO UPDATE SET
                count = llm_mcp_rate_limit_window.count + 1,
                expires_at = EXCLUDED.expires_at,
                write_uid = EXCLUDED.write_uid,
                write_date = EXCLUDED.write_date
            RETURNING count, expires_at
            """,
            (
                company_id,
                bucket_key,
                window_start,
                expires_at,
                self.env.uid or SUPERUSER_ID,
                now,
                self.env.uid or SUPERUSER_ID,
                now,
            ),
        )
        result = self.env.cr.fetchone()
        if not result:
            _logger.error("Failed to increment rate limit bucket %s", bucket_key)
            return 0, expires_at
        count, effective_expiry = result
        return int(count), effective_expiry

    @api.model
    def purge_expired(self, now=None, company_id=None):
        now = now or fields.Datetime.now()
        company_id = company_id or (self.env.company and self.env.company.id) or False
        query = "DELETE FROM llm_mcp_rate_limit_window WHERE expires_at < %s"
        params = [now]
        if company_id:
            query += " AND company_id = %s"
            params.append(company_id)
        self.env.cr.execute(query, tuple(params))
