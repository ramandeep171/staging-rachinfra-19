import json

from odoo import http
from odoo.exceptions import AccessDenied
from odoo.http import request


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
        env = request.env(user=user.id).sudo()

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
