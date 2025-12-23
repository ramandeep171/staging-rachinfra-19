import json
import time
from typing import Generator, Iterable, Optional

from werkzeug.exceptions import Unauthorized, TooManyRequests

from odoo import http
from odoo.http import request


class MCPGatewayController(http.Controller):
    """Public MCP gateway with strict auth + permission enforcement."""

    HEARTBEAT_INTERVAL = 15

    @staticmethod
    def _extract_token() -> Optional[str]:
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1]
        return request.httprequest.headers.get("X-LLM-Token")

    @staticmethod
    def _require_token() -> str:
        token = MCPGatewayController._extract_token()
        if not token:
            raise Unauthorized("Invalid or missing token")

        env = request.env
        config = env["ir.config_parameter"].sudo()
        expected = (config.get_param("llm_mcp.api_token") or "").strip()
        if expected and token == expected:
            return token

        connection = env["llm.mcp.connection"].sudo().authenticate_token(token)
        if not connection:
            raise Unauthorized("Invalid or missing token")

        request.mcp_connection = connection
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
        "/mcp/tools",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def list_tools(self, **params):
        token = self._require_token()
        user = self._resolve_user(params.get("user_id"))
        request.mcp_user = user
        request.mcp_token = token
        env = request.env(user=user.id).sudo()

        tags_param = params.get("tags") or ""
        tags: Iterable[str] = [tag.strip() for tag in tags_param.split(",") if tag.strip()]
        action_types_param = params.get("action_type") or ""
        action_types: Iterable[str] = [
            action.strip() for action in action_types_param.split(",") if action.strip()
        ]

        tools = env["llm.tool.registry.service"].list_tools(
            user=user,
            tags=tags,
            action_types=action_types,
            session_id=params.get("session_id"),
        )

        return self._json_response({"tools": tools})

    @http.route(
        "/mcp/execute",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def execute(self, **payload):
        token = self._require_token()
        data = payload or request.jsonrequest or {}
        user = self._resolve_user(data.get("user_id"))
        request.mcp_user = user
        request.mcp_token = token
        env = request.env(user=user.id).sudo()

        tool_key = data.get("tool") or data.get("tool_key")
        if not tool_key:
            return self._json_response({"error": "tool is required"}, status=400)

        try:
            result = env["llm.mcp.execution.router"].route(
                session_id=data.get("session_id"),
                tool_key=tool_key,
                params=data.get("params") or {},
                user=user,
                parent_invocation=data.get("parent_invocation"),
                token=token,
            )
        except TooManyRequests as exc:
            return self._json_response({"error": str(exc)}, status=429)
        except Unauthorized as exc:
            return self._json_response({"error": str(exc)}, status=401)
        except Exception as exc:  # noqa: BLE001 - propagate useful error
            return self._json_response({"error": str(exc)}, status=400)

        return self._json_response(result)

    def _sse_event(self, event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data)
        return f"event: {event}\ndata: {payload}\n\n"

    def _stream(self, user, token, session_id=None) -> Generator[bytes, None, None]:
        try:
            env = request.env(user=user.id).sudo()
            tools = env["llm.tool.registry.service"].list_tools(
                user=user, tags=None, action_types=None, session_id=session_id
            )
            yield self._sse_event("tools", {"tools": tools}).encode()

            last_ping = time.time()
            while True:
                now = time.time()
                if now - last_ping >= self.HEARTBEAT_INTERVAL:
                    last_ping = now
                    yield self._sse_event("ping", {"ts": now}).encode()
                time.sleep(1)
        except Exception as exc:  # noqa: BLE001 - streaming must terminate
            yield self._sse_event("error", {"error": str(exc)}).encode()

    @http.route(
        "/mcp/sse",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def sse(self, **params):
        try:
            token = self._require_token()
        except Unauthorized as exc:
            error_body = self._sse_event("error", {"error": str(exc)}).encode()
            return request.make_response(
                error_body,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                status=401,
            )

        user = self._resolve_user(params.get("user_id"))
        request.mcp_user = user
        request.mcp_token = token

        stream = self._stream(user, token, params.get("session_id"))
        return request.make_response(
            stream,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
