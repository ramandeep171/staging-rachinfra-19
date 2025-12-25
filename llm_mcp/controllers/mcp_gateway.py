import json
import logging
import time
from typing import Generator, Iterable, Optional

from werkzeug.exceptions import Unauthorized, TooManyRequests

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


_logger = logging.getLogger(__name__)


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
    def _require_connection():
        token = MCPGatewayController._extract_token()
        if not token:
            raise Unauthorized("Invalid or missing token")

        connection = request.env["llm.mcp.connection"].sudo().authenticate_token(token)
        if not connection or not connection.user_id or not connection.company_id:
            raise Unauthorized("Invalid or missing token")

        request.mcp_connection = connection
        request.mcp_token = token
        return connection, token

    @staticmethod
    def _resolve_user(connection, requested_user_id=None):
        user = connection.user_id
        if not user:
            raise Unauthorized("MCP connection is missing a linked user.")
        if requested_user_id:
            try:
                requested_id = int(requested_user_id)
            except (TypeError, ValueError):
                requested_id = None
            if requested_id and requested_id != user.id:
                _logger.warning(
                    "MCP client attempted to override user to %s on connection %s; ignoring.",
                    requested_id,
                    connection.id,
                )
        return user

    @staticmethod
    def _json_response(payload, status=200):
        body = json.dumps(payload)
        return request.make_response(
            body,
            headers={"Content-Type": "application/json"},
            status=status,
        )

    @staticmethod
    def _json_error(message, *, code="MCP_ERROR", status=400):
        payload = {"error": {"code": code, "message": message}}
        return MCPGatewayController._json_response(payload, status=status)

    @staticmethod
    def _serialize_tools(tools_payload):
        serialized = []
        for tool in tools_payload or []:
            name = tool.get("name") or tool.get("tool_key") or ""
            schema = tool.get("input_schema") or tool.get("schema") or {}
            serialized.append(
                {
                    "name": name,
                    "description": tool.get("description") or "",
                    "input_schema": schema,
                }
            )
        return serialized

    @staticmethod
    def _build_mcp_env(connection, user):
        company = connection.company_id
        if not company:
            raise Unauthorized("MCP connection is missing a company.")

        context = dict(request.env.context or {})
        context.update(
            {
                "uid": user.id,
                "allowed_company_ids": [company.id],
                "company_id": company.id,
                "force_company": company.id,
                "is_mcp": True,
            }
        )
        request.mcp_context = context
        request.mcp_company = company
        request.update_env(user=user.id, context=context)
        return request.env

    @http.route(
        ["/mcp/tools", "/<path:_proxy_path>/mcp/tools"],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        priority=100,
    )
    def list_tools(self, _proxy_path=None, **params):
        try:
            connection, _token = self._require_connection()
            user = self._resolve_user(connection, params.get("user_id"))
            env = self._build_mcp_env(connection, user)
        except Unauthorized as exc:
            return self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401)

        request.mcp_user = user

        tags_param = params.get("tags") or ""
        tags: Iterable[str] = [tag.strip() for tag in tags_param.split(",") if tag.strip()]
        action_types_param = params.get("action_type") or ""
        action_types: Iterable[str] = [
            action.strip() for action in action_types_param.split(",") if action.strip()
        ]

        try:
            raw_tools = env["llm.tool.registry.service"].list_tools(
                user=user,
                tags=tags,
                action_types=action_types,
                session_id=params.get("session_id"),
            )
            tools = self._serialize_tools(raw_tools)
            return self._json_response({"tools": tools})
        except Exception:  # noqa: BLE001 - response must remain JSON
            _logger.exception(
                "Failed to list MCP tools for connection %s (session: %s)",
                connection.id,
                params.get("session_id"),
            )
            return self._json_error(
                "Unable to list tools at this time. Please retry shortly.",
                code="MCP_TOOLS_ERROR",
                status=500,
            )

    @http.route(
        ["/mcp/execute", "/<path:_proxy_path>/mcp/execute"],
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
        priority=100,
    )
    def execute(self, _proxy_path=None, **payload):
        data = payload or request.jsonrequest or {}

        try:
            connection, token = self._require_connection()
            user = self._resolve_user(connection, data.get("user_id"))
            env = self._build_mcp_env(connection, user)
        except Unauthorized as exc:
            return self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401)

        request.mcp_user = user

        tool_key = data.get("tool") or data.get("tool_key")
        if not tool_key:
            return self._json_error("tool is required", code="MCP_INVALID_REQUEST", status=400)

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
            return self._json_error(str(exc), code="MCP_RATE_LIMIT", status=429)
        except Unauthorized as exc:
            return self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401)
        except UserError as exc:
            return self._json_error(str(exc), code="MCP_EXEC_ERROR", status=400)
        except Exception as exc:  # noqa: BLE001 - never leak raw traceback
            _logger.exception(
                "Tool execution failed for %s (session: %s)",
                tool_key,
                data.get("session_id"),
            )
            return self._json_error(
                "Tool execution failed. Check server logs for details.",
                code="MCP_EXEC_ERROR",
                status=500,
            )

        return self._json_response(result)

    def _sse_event(self, event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data)
        return f"event: {event}\ndata: {payload}\n\n"

    def _stream(self, env, user, session_id=None) -> Generator[bytes, None, None]:
        yield self._sse_event("ready", {"protocol": "mcp/1.0", "status": "ok"}).encode()
        try:
            tools = env["llm.tool.registry.service"].list_tools(
                user=user, tags=None, action_types=None, session_id=session_id
            )
            serialized = self._serialize_tools(tools)
            yield self._sse_event("tools", {"tools": serialized}).encode()

            last_ping = time.time()
            while True:
                now = time.time()
                if now - last_ping >= self.HEARTBEAT_INTERVAL:
                    last_ping = now
                    yield self._sse_event("heartbeat", {"ts": now}).encode()
                time.sleep(1)
        except Exception:  # noqa: BLE001 - streaming must terminate gracefully
            _logger.exception(
                "SSE stream failed for connection %s (session: %s)",
                getattr(request, "mcp_connection", False) and request.mcp_connection.id,
                session_id,
            )
            yield self._sse_event(
                "error",
                {
                    "error": {
                        "code": "MCP_SSE_ERROR",
                        "message": "Stream closed due to server error.",
                    }
                },
            ).encode()

    @http.route(
        ["/mcp/sse", "/<path:_proxy_path>/mcp/sse"],
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        priority=100,
    )
    def sse(self, _proxy_path=None, **params):
        try:
            connection, _token = self._require_connection()
            user = self._resolve_user(connection, params.get("user_id"))
            env = self._build_mcp_env(connection, user)
        except Unauthorized as exc:
            error_body = self._sse_event(
                "error",
                {"error": {"code": "MCP_AUTH_ERROR", "message": str(exc)}},
            ).encode()
            return request.make_response(
                error_body,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
                status=401,
            )

        request.mcp_user = user

        stream = self._stream(env, user, params.get("session_id"))
        return request.make_response(
            stream,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
