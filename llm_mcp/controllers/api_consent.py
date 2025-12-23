import json

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request


class LLMConsentController(http.Controller):
    @staticmethod
    def _extract_token():
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1]
        return request.httprequest.headers.get("X-LLM-Token")

    @staticmethod
    def _require_token():
        token = LLMConsentController._extract_token()
        expected = request.env["ir.config_parameter"].sudo().get_param(
            "llm_mcp.api_token"
        )
        if not token or token != expected:
            raise AccessDenied("Invalid or missing token")
        return token

    @staticmethod
    def _resolve_user(user_id=None):
        if user_id:
            try:
                user = request.env["res.users"].sudo().browse(int(user_id))
                if user.exists():
                    return user
            except (TypeError, ValueError):
                pass
        return request.env.user

    @staticmethod
    def _json_response(payload, status=200):
        body = json.dumps(payload)
        return request.make_response(
            body,
            headers={"Content-Type": "application/json"},
            status=status,
        )

    @http.route(
        "/mcp/consent/request",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def request_consent(self, **payload):
        self._require_token()

        data = payload or request.jsonrequest or {}
        user = self._resolve_user(data.get("user_id"))
        env = request.env(user=user.id)

        tool = env["llm.tool.definition"].browse(data.get("tool_id"))
        if not tool.exists():
            return self._json_response({"error": "Tool not found"}, status=404)

        result = env["llm.mcp.consent.handler"].request_consent(
            tool=tool,
            user=user,
            decision=data.get("decision"),
            context_payload=data.get("context_payload") or {},
        )
        return self._json_response(result)

    @http.route(
        "/mcp/consent/revoke",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def revoke_consent(self, **payload):
        self._require_token()

        data = payload or request.jsonrequest or {}
        user = self._resolve_user(data.get("user_id"))
        env = request.env(user=user.id)

        ledger = None
        ledger_id = data.get("ledger_id")
        if ledger_id:
            ledger = env["llm.mcp.consent.ledger"].browse(ledger_id)
            if not ledger.exists():
                return self._json_response({"error": "Ledger not found"}, status=404)

        tool = None
        tool_id = data.get("tool_id")
        if tool_id:
            tool = env["llm.tool.definition"].browse(tool_id)
            if tool_id and not tool.exists():
                return self._json_response({"error": "Tool not found"}, status=404)

        result = env["llm.mcp.consent.handler"].revoke_consent(
            user=user,
            ledger=ledger,
            tool=tool,
        )
        return self._json_response(result)
