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


class LLMToolRegistryController(http.Controller):
    @staticmethod
    def _extract_token():
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1]
        return request.httprequest.headers.get("X-LLM-Token")

    @staticmethod
    def _require_token():
        token = LLMToolRegistryController._extract_token()
        expected = request.env["ir.config_parameter"].sudo().get_param(
            "llm_tool.api_token"
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

    @http.route(
        "/mcp/tool_registry",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def tool_registry(self, **params):
        self._require_token()

        user = self._resolve_user(params.get("user_id"))
        env = request.env(user=user.id)

        tags_param = params.get("tags") or ""
        tags = [tag.strip() for tag in tags_param.split(",") if tag.strip()]
        action_types_param = params.get("action_type") or ""
        action_types = [action.strip() for action in action_types_param.split(",") if action.strip()]

        tools = env["llm.tool.registry.service"].list_tools(
            user=user,
            tags=tags,
            action_types=action_types,
            session_id=params.get("session_id"),
        )

        body = json.dumps({"tools": tools})
        return request.make_response(
            body,
            headers={"Content-Type": "application/json"},
        )
