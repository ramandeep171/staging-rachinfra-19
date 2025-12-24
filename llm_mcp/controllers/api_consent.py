import json
import os
from types import SimpleNamespace

try:
    from odoo import http
    from odoo.exceptions import AccessDenied
    from odoo.http import request
    _ODOO_RUNTIME = True
except ImportError:

    _ODOO_RUNTIME = False

    class EnvStub(dict):
        def __init__(self):
            super().__init__()
            self.context = {}
            self.user = None

        def __call__(self, *args, **kwargs):
            return self

    class RequestStub:
        def __init__(self):
            self.httprequest = SimpleNamespace(headers={}, method=None)
            self.env = EnvStub()
            self.jsonrequest = {}
            self.context = {}

        def make_response(self, body, headers=None, status=200):
            return {"body": body, "headers": headers or {}, "status": status}

        def update_env(self, user=None, context=None):
            if user is not None:
                self.env.user = user
            if context is not None:
                self.env.context = context

    class http:  # type: ignore
        class Controller:  # pragma: no cover - minimal stub for pytest
            pass

        @staticmethod
        def route(*_args, **_kwargs):  # pragma: no cover - minimal stub for pytest
            def decorator(func):
                return func

            return decorator

    class AccessDenied(Exception):
        pass

    request = RequestStub()


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
