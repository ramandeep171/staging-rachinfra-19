# Copyright 2024 Rachin Infrastructure
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0.html)
import json
import logging
import re
import secrets
from hashlib import sha256
from urllib.parse import urlparse, urlunparse

import requests
from psycopg2 import errors
from odoo import _, api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class LLMMCPConnection(models.Model):
    _name = "llm.mcp.connection"
    _description = "LLM MCP Connection"
    _rec_name = "name"
    _order = "create_date desc"
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Service User",
        required=True,
        default=lambda self: self.env.user,
        help="Requests authenticated with this token run using this user's security context.",
    )
    token = fields.Char(
        string="Token",
        required=False,
        copy=False,
        encryption="fernet",
        searchable=False,
        groups="base.group_system,llm_mcp.group_llm_mcp_admin",
    )
    token_hash = fields.Char(index=True, copy=False)
    token_last4 = fields.Char(copy=False)
    revoked = fields.Boolean(default=False)
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    last_used_at = fields.Datetime()
    last_test_at = fields.Datetime()
    last_test_status = fields.Selection(
        [
            ("success", "Success"),
            ("fail", "Failure"),
        ],
        string="Last Test Status",
    )
    notes = fields.Text()
    sse_url = fields.Char(compute="_compute_connection_endpoints", readonly=True)
    tools_url = fields.Char(compute="_compute_connection_endpoints", readonly=True)
    execute_url = fields.Char(compute="_compute_connection_endpoints", readonly=True)
    request_header_json = fields.Text(
        compute="_compute_connection_endpoints", readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            token = vals.get("token")
            if token:
                vals.setdefault("token_hash", self._compute_token_hash(token))
                vals.setdefault("token_last4", token[-4:])
        return super().create(vals_list)

    def write(self, vals):
        token = vals.get("token")
        if token:
            vals.setdefault("token_hash", self._compute_token_hash(token))
            vals.setdefault("token_last4", token[-4:])
        return super().write(vals)

    def read(self, fields=None, load="_classic_read"):
        results = super().read(fields, load=load)
        if not fields or "token" in fields:
            for values in results:
                if "token" in values:
                    values["token"] = (
                        self._mask_token(values.get("token"))
                        if values.get("token")
                        else False
                    )
        return results

    def action_generate_token(self):
        self.ensure_one()
        token = self._generate_token()
        token_hash = self._compute_token_hash(token)
        token_last4 = token[-4:]
        self.write(
            {
                "token_hash": token_hash,
                "token_last4": token_last4,
                "token": token,
                "revoked": False,
            }
        )
        wizard = self.env["llm.mcp.connection.token.wizard"].create(
            {
                "connection_id": self.id,
                "token_display": token,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("MCP Token"),
            "res_model": "llm.mcp.connection.token.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @staticmethod
    def _compute_token_hash(token: str) -> str:
        return sha256(token.encode()).hexdigest()

    @staticmethod
    def _mask_token(token: str) -> str:
        if not token:
            return False
        suffix = token[-4:]
        return f"****{suffix}"

    def _generate_token(self) -> str:
        self.ensure_one()
        slug = self._slugify_name(self.name)
        random_part = secrets.token_urlsafe(24)
        token = f"mcp_{slug}_{self.env.uid}_{random_part}"
        if len(token) < 32:
            token = f"{token}{secrets.token_urlsafe(32)}"
        return token

    @staticmethod
    def _slugify_name(name: str) -> str:
        if not name:
            return "connection"
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        return slug or "connection"

    @api.depends("token")
    def _compute_connection_endpoints(self):
        base_url = self._compute_https_base_url()
        db_name = self.env.cr.dbname
        for connection in self:
            normalized_base = base_url.rstrip("/") if base_url else ""
            suffix = f"?db={db_name}" if normalized_base else ""
            connection.sse_url = f"{normalized_base}/mcp/sse{suffix}" if normalized_base else False
            connection.tools_url = (
                f"{normalized_base}/mcp/tools{suffix}" if normalized_base else False
            )
            connection.execute_url = (
                f"{normalized_base}/mcp/execute{suffix}" if normalized_base else False
            )
            masked_token = self._mask_token(connection.token) or "****"
            headers = {
                "Authorization": f"Bearer {masked_token}",
                "Content-Type": "application/json",
                "X-Odoo-Database": db_name,
            }
            connection.request_header_json = json.dumps(headers, indent=4)

    def _compute_https_base_url(self):
        config_param = self.env["ir.config_parameter"].sudo()
        base_url = (config_param.get_param("web.base.url") or "").strip()
        if not base_url:
            return ""
        if not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or parsed.path
        path = parsed.path if parsed.netloc else ""
        normalized = urlunparse((scheme, netloc, path.rstrip("/"), "", "", ""))
        return normalized

    def _get_stored_token(self) -> str:
        self.ensure_one()
        token_value = self.token or ""
        if token_value.startswith("****"):
            return ""
        return token_value

    @api.model
    def authenticate_token(self, token: str):
        token = (token or "").strip()
        if not token:
            return self.browse()

        connection = (
            self.sudo()
            .search(
                [
                    ("token_hash", "=", self._compute_token_hash(token)),
                    ("active", "=", True),
                    ("revoked", "=", False),
                ],
                limit=1,
            )
        )
        if connection:
            try:
                with self.env.cr.savepoint():
                    timestamp = fields.Datetime.now()
                    self.env.cr.execute(
                        "UPDATE llm_mcp_connection SET last_used_at=%s WHERE id=%s",
                        (timestamp, connection.id),
                    )
                    connection.invalidate_cache(["last_used_at"])
            except errors.SerializationFailure:
                _logger.debug(
                    "Concurrent MCP connection update skipped for %s", connection.id
                )
        return connection

    def action_test_connection(self):
        self.ensure_one()
        token_value = self._get_stored_token()
        if not token_value:
            raise UserError(
                _("Token is not available. Generate a new token to test the connection."),
            )

        base_url = self._compute_https_base_url()
        if not base_url:
            raise UserError(
                _("Base URL is not configured. Please set web.base.url before testing."),
            )

        tools_url = f"{base_url.rstrip('/')}/mcp/tools"
        headers = {"Authorization": f"Bearer {token_value}", "Content-Type": "application/json"}

        now = fields.Datetime.now()
        status = "fail"
        message = _("Connection test failed.")
        try:
            response = self._perform_connection_test(tools_url, headers)
            if response.status_code == 200:
                status = "success"
            elif response.status_code == 401:
                message = _("Unauthorized: the stored token was rejected.")
            else:
                message = _("Unexpected response: %s") % response.status_code
        except Exception as err:  # noqa: BLE001 - surface controlled error to user
            message = _("Connection test failed: %s") % err

        self.write({"last_test_at": now, "last_test_status": status})

        if status != "success":
            raise UserError(message)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Connection successful"),
                "message": _("MCP tools endpoint responded successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def _perform_connection_test(self, url: str, headers: dict):
        return requests.get(url, headers=headers, timeout=5)


class LLMMCPConnectionTokenWizard(models.TransientModel):
    _name = "llm.mcp.connection.token.wizard"
    _description = "MCP Connection Token Preview"

    connection_id = fields.Many2one("llm.mcp.connection", required=True, ondelete="cascade")
    token_display = fields.Char(readonly=True)
