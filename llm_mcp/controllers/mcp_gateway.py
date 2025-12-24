import json
import logging
import os
import time
from types import SimpleNamespace
from typing import Generator, Iterable, Optional

try:
    from werkzeug.exceptions import Unauthorized, TooManyRequests
except ImportError:
    class Unauthorized(Exception):
        pass

    class TooManyRequests(Exception):
        pass

try:
    from odoo import http
    from odoo.exceptions import UserError
    from odoo.http import request

    _ODOO_RUNTIME = True
except ImportError:

    _ODOO_RUNTIME = False

    class EnvStub(dict):
        def __init__(self):
            super().__init__()
            self.context = {}
            self.user = None

    class RequestStub:
        def __init__(self):
            self.httprequest = SimpleNamespace(
                headers={}, method=None, host_url="https://localhost", remote_addr="127.0.0.1"
            )
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

    class UserError(Exception):
        pass

    request = RequestStub()


_logger = logging.getLogger(__name__)


class MCPGatewayController(http.Controller):
    """Public MCP gateway with strict auth + permission enforcement."""

    HEARTBEAT_INTERVAL = 15
    HEARTBEAT_SLEEP_SLICE = 0.25
    SSE_MAX_PER_IP = 3
    RATE_LIMIT_NO_AUTH = 60
    RATE_LIMIT_WINDOW = 60
    OAUTH_TOKEN_TTL = 300
    _OAUTH_TOKEN_MAP = {}
    _SSE_ACTIVE = {}
    _NO_AUTH_REQUESTS = {}
    _LAST_OAUTH_TOKEN_TS = 0.0
    _RATE_LIMIT_COUNT = 0

    @staticmethod
    def _client_id():
        headers = getattr(request, "httprequest", SimpleNamespace(headers={})).headers
        forwarded = headers.get("X-Forwarded-For") if isinstance(headers, dict) else None
        if forwarded:
            return forwarded.split(",")[0].strip()
        remote_addr = getattr(getattr(request, "httprequest", None), "remote_addr", None)
        return remote_addr or "unknown"

    @staticmethod
    def _set_auth_mode(mode: str):
        context = getattr(request, "context", None)
        if isinstance(context, dict):
            updated = dict(context)
            updated["auth_mode"] = mode
            request.context = updated
        elif context is None:
            request.context = {"auth_mode": mode}
        else:
            setattr(context, "auth_mode", mode)
            request.context = context

        setattr(request, "auth_mode", mode)

    @staticmethod
    def _detect_auth_mode() -> str:
        auth_header = request.httprequest.headers.get("Authorization", "")
        if auth_header:
            if auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1]
                if token in MCPGatewayController._OAUTH_TOKEN_MAP:
                    return "oauth"
                return "bearer"
            return "oauth"

        if request.httprequest.headers.get("X-LLM-Token"):
            return "bearer"

        return "no_auth"

    @staticmethod
    def _extract_token() -> Optional[str]:
        auth_header = request.httprequest.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1]
        return request.httprequest.headers.get("X-LLM-Token")

    @staticmethod
    def _log_access(endpoint: str, *, status: int, tool: Optional[str] = None, outcome: str = "ok"):
        try:
            client_ip = MCPGatewayController._client_id()
            auth_mode = getattr(request, "auth_mode", None) or getattr(request, "context", {}).get(
                "auth_mode"
            )
            payload = {
                "endpoint": endpoint,
                "status": status,
                "auth_mode": auth_mode,
                "tool": tool,
                "client_ip": client_ip,
                "outcome": outcome,
            }
            _logger.info("mcp_access %s", json.dumps(payload, default=str))
        except Exception:  # pragma: no cover - logging must not break handler
            _logger.debug("Failed to emit access log for %s", endpoint, exc_info=True)

    @classmethod
    def _mint_oauth_token(cls, bearer_token: str) -> str:
        now = time.time()
        token = f"oauth-{int(now * 1000)}"
        cls._OAUTH_TOKEN_MAP[token] = (bearer_token, now + cls.OAUTH_TOKEN_TTL)
        cls._LAST_OAUTH_TOKEN_TS = now
        return token

    @classmethod
    def _resolve_oauth_token(cls, token: str) -> Optional[str]:
        if not token:
            return None
        mapped = cls._OAUTH_TOKEN_MAP.get(token)
        now = time.time()
        if mapped and mapped[1] >= now:
            return mapped[0]
        if mapped:
            cls._OAUTH_TOKEN_MAP.pop(token, None)
            _logger.warning("oauth_token_expired %s", json.dumps({"token": "redacted"}))
        return None

    @staticmethod
    def _require_connection(*, allow_no_auth: bool = False):
        auth_mode = MCPGatewayController._detect_auth_mode()
        MCPGatewayController._set_auth_mode(auth_mode)

        token = MCPGatewayController._extract_token()
        if auth_mode == "oauth":
            token = MCPGatewayController._resolve_oauth_token(token)
            if token is None:
                _logger.warning(
                    "oauth_token_invalid %s",
                    json.dumps({"auth_mode": auth_mode, "client_ip": MCPGatewayController._client_id()}),
                )
        if not token:
            if allow_no_auth and auth_mode == "no_auth":
                MCPGatewayController._enforce_no_auth_rate_limit()
                return None, None
            if auth_mode == "no_auth":
                _logger.warning(
                    "no_auth_execute_blocked %s",
                    json.dumps({"client_ip": MCPGatewayController._client_id()}),
                )
            raise Unauthorized("Invalid or missing token")

        connection = request.env["llm.mcp.connection"].sudo().authenticate_token(token)
        if not connection or not connection.user_id or not connection.company_id:
            _logger.warning(
                "auth_failed %s",
                json.dumps({"client_ip": MCPGatewayController._client_id(), "auth_mode": auth_mode}),
            )
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
    def _cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-LLM-Token",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }

    @staticmethod
    def _with_cors(response):
        try:
            headers = None
            if isinstance(response, dict):
                headers = response.setdefault("headers", {})
            elif hasattr(response, "headers"):
                headers = response.headers
            if headers is not None:
                headers.update(MCPGatewayController._cors_headers())
        except Exception:  # pragma: no cover - defensive only
            _logger.debug("Failed to apply CORS headers", exc_info=True)
        return response

    @staticmethod
    def _issuer_base_url():
        host_url = getattr(request.httprequest, "host_url", None)
        if host_url:
            return host_url.rstrip("/")
        return "https://localhost"

    @http.route(
        "/.well-known/oauth-authorization-server",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def oauth_authorization_server(self):
        base = self._issuer_base_url()
        payload = {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "scopes_supported": ["mcp"],
            "response_types_supported": ["code", "token"],
        }
        return self._json_response(payload)

    @http.route(
        "/.well-known/openid-configuration",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def openid_configuration(self):
        base = self._issuer_base_url()
        payload = {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/oauth/token",
            "scopes_supported": ["mcp"],
            "response_types_supported": ["code", "token"],
        }
        return self._json_response(payload)

    @staticmethod
    def _json_error(message, *, code="MCP_ERROR", status=400):
        payload = {"error": {"code": code, "message": message}}
        return MCPGatewayController._json_response(payload, status=status)

    @classmethod
    def _enforce_no_auth_rate_limit(cls):
        client_id = cls._client_id()
        now = time.time()
        window_start, count = cls._NO_AUTH_REQUESTS.get(client_id, (now, 0))
        if now - window_start > cls.RATE_LIMIT_WINDOW:
            window_start, count = now, 0
        count += 1
        cls._NO_AUTH_REQUESTS[client_id] = (window_start, count)
        if count > cls.RATE_LIMIT_NO_AUTH:
            cls._RATE_LIMIT_COUNT += 1
            _logger.warning(
                "no_auth_rate_limited %s",
                json.dumps(
                    {
                        "client_ip": client_id,
                        "count": count,
                        "window": cls.RATE_LIMIT_WINDOW,
                        "total_rate_limited": cls._RATE_LIMIT_COUNT,
                    }
                ),
            )
            raise TooManyRequests("Rate limit exceeded for unauthenticated access")

    @classmethod
    def _register_sse(cls):
        client_id = cls._client_id()
        current = cls._SSE_ACTIVE.get(client_id, 0)
        if current >= cls.SSE_MAX_PER_IP:
            _logger.warning(
                "sse_rejected %s",
                json.dumps({"client_ip": client_id, "active": current, "limit": cls.SSE_MAX_PER_IP}),
            )
            raise TooManyRequests("Too many active streams")
        cls._SSE_ACTIVE[client_id] = current + 1
        return client_id

    @classmethod
    def _release_sse(cls, client_id):
        try:
            if client_id in cls._SSE_ACTIVE:
                cls._SSE_ACTIVE[client_id] = max(
                    cls._SSE_ACTIVE.get(client_id, 1) - 1,
                    0,
                )
        except Exception:  # pragma: no cover - defensive decrement must not raise
            _logger.debug("Failed to release SSE slot for %s", client_id, exc_info=True)

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

    @http.route(
        "/oauth/token",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def oauth_token(self, **payload):
        # Soft OAuth handler: issues short-lived access tokens that internally map to
        # existing MCP bearer tokens. No refresh or persistence is provided.
        data = payload or request.jsonrequest or {}
        bearer_token = (
            data.get("mcp_token")
            or data.get("llm_token")
            or data.get("token")
            or request.httprequest.headers.get("X-LLM-Token")
        )
        if not bearer_token:
            return self._json_error(
                "mcp_token is required",
                code="MCP_AUTH_ERROR",
                status=400,
            )

        access_token = self._mint_oauth_token(bearer_token)
        self._set_auth_mode("oauth")

        response = {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": self.OAUTH_TOKEN_TTL,
            "scope": data.get("scope", "mcp"),
        }
        _logger.info(
            "oauth_token_issued %s",
            json.dumps(
                {
                    "client_ip": self._client_id(),
                    "auth_mode": "oauth",
                    "last_issued": self._LAST_OAUTH_TOKEN_TS,
                }
            ),
        )
        return self._json_response(response)

    @staticmethod
    def _build_mcp_env(connection, user):
        company = connection.company_id
        if not company:
            raise Unauthorized("MCP connection is missing a company.")

        context = dict(request.env.context or {})
        auth_mode = getattr(request, "auth_mode", None)
        if isinstance(request.context, dict):
            auth_mode = request.context.get("auth_mode", auth_mode)
        elif getattr(request, "context", None) is not None:
            auth_mode = getattr(request.context, "auth_mode", auth_mode)
        context.update(
            {
                "uid": user.id,
                "allowed_company_ids": [company.id],
                "company_id": company.id,
                "force_company": company.id,
                "is_mcp": True,
            }
        )
        if auth_mode:
            context["auth_mode"] = auth_mode
        request.mcp_context = context
        request.mcp_company = company
        request.update_env(user=user.id, context=context)
        return request.env

    @http.route(
        "/mcp/tools",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def list_tools(self, **params):
        if request.httprequest.method == "OPTIONS":
            return self._with_cors(request.make_response("", headers=self._cors_headers(), status=204))

        connection = None
        try:
            connection, _token = self._require_connection(allow_no_auth=True)
            if connection:
                user = self._resolve_user(connection, params.get("user_id"))
                env = self._build_mcp_env(connection, user)
            else:
                user = request.env.user
                env = request.env
        except Unauthorized as exc:
            response = self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401)
            self._log_access("/mcp/tools", status=response.get("status", 401), outcome="unauthorized")
            return response

        request.mcp_user = user

        tags_param = params.get("tags") or ""
        tags: Iterable[str] = [tag.strip() for tag in tags_param.split(",") if tag.strip()]
        action_types_param = params.get("action_type") or ""
        action_types: Iterable[str] = [
            action.strip() for action in action_types_param.split(",") if action.strip()
        ]

        connection_id = connection and connection.id
        try:
            raw_tools = env["llm.tool.registry.service"].list_tools(
                user=user,
                tags=tags,
                action_types=action_types,
                session_id=params.get("session_id"),
            )
            tools = self._serialize_tools(raw_tools)
            response = self._with_cors(self._json_response({"tools": tools}))
            self._log_access("/mcp/tools", status=response.get("status", 200), outcome="ok")
            return response
        except Exception:  # noqa: BLE001 - response must remain JSON
            _logger.exception(
                "Failed to list MCP tools for connection %s (session: %s)",
                connection_id,
                params.get("session_id"),
            )
            response = self._with_cors(
                self._json_error(
                    "Unable to list tools at this time. Please retry shortly.",
                    code="MCP_TOOLS_ERROR",
                    status=500,
                )
            )
            self._log_access(
                "/mcp/tools", status=response.get("status", 500), outcome="error", tool=params.get("tool")
            )
            return response

    @http.route(
        "/mcp/execute",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def execute(self, **payload):
        if request.httprequest.method == "OPTIONS":
            return self._with_cors(request.make_response("", headers=self._cors_headers(), status=204))

        data = payload or request.jsonrequest or {}

        try:
            connection, token = self._require_connection()
            user = self._resolve_user(connection, data.get("user_id"))
            env = self._build_mcp_env(connection, user)
        except Unauthorized as exc:
            response = self._with_cors(
                self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401)
            )
            self._log_access(
                "/mcp/execute",
                status=response.get("status", 401),
                tool=data.get("tool"),
                outcome="unauthorized",
            )
            return response

        request.mcp_user = user

        tool_key = data.get("tool") or data.get("tool_key")
        if not tool_key:
            return self._with_cors(
                self._json_error("tool is required", code="MCP_INVALID_REQUEST", status=400)
            )

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
            response = self._with_cors(self._json_error(str(exc), code="MCP_RATE_LIMIT", status=429))
            self._log_access(
                "/mcp/execute",
                status=response.get("status", 429),
                tool=tool_key,
                outcome="rate_limited",
            )
            return response
        except Unauthorized as exc:
            response = self._with_cors(self._json_error(str(exc), code="MCP_AUTH_ERROR", status=401))
            self._log_access(
                "/mcp/execute",
                status=response.get("status", 401),
                tool=tool_key,
                outcome="unauthorized",
            )
            return response
        except UserError as exc:
            response = self._with_cors(self._json_error(str(exc), code="MCP_EXEC_ERROR", status=400))
            self._log_access(
                "/mcp/execute",
                status=response.get("status", 400),
                tool=tool_key,
                outcome="user_error",
            )
            return response
        except Exception as exc:  # noqa: BLE001 - never leak raw traceback
            _logger.exception(
                "Tool execution failed for %s (session: %s)",
                tool_key,
                data.get("session_id"),
            )
            response = self._with_cors(
                self._json_error(
                    "Tool execution failed. Check server logs for details.",
                    code="MCP_EXEC_ERROR",
                    status=500,
                )
            )
            self._log_access(
                "/mcp/execute",
                status=response.get("status", 500),
                tool=tool_key,
                outcome="error",
            )
            return response

        response = self._with_cors(self._json_response(result))
        self._log_access("/mcp/execute", status=response.get("status", 200), tool=tool_key, outcome="ok")
        return response

    def _sse_event(self, event: str, data) -> str:
        payload = data if isinstance(data, str) else json.dumps(data)
        return f"event: {event}\ndata: {payload}\n\n"

    def _sse_response(self, stream, *, status=200):
        response = request.make_response(
            stream,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            status=status,
        )
        return self._with_cors(response)

    def _sse_error_response(self, message, *, code="MCP_SSE_ERROR", status=400):
        def stream():
            yield self._sse_event(
                "error",
                {
                    "error": {
                        "code": code,
                        "message": message,
                    }
                },
            ).encode()

        return self._sse_response(stream(), status=status)

    def _stream(self) -> Generator[bytes, None, None]:
        """Emit the ready event immediately and follow with heartbeat events."""
        yield self._sse_event("ready", {"ok": True}).encode()
        try:
            last_ping = time.time()
            while True:
                now = time.time()
                if now - last_ping >= self.HEARTBEAT_INTERVAL:
                    last_ping = now
                    yield self._sse_event("heartbeat", {}).encode()
                time.sleep(self.HEARTBEAT_SLEEP_SLICE)
        except Exception:  # noqa: BLE001 - streaming must terminate gracefully
            _logger.exception(
                "SSE stream failed for connection %s",
                getattr(request, "mcp_connection", False) and request.mcp_connection.id,
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
        "/mcp/sse",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def sse(self, **params):
        if request.httprequest.method == "OPTIONS":
            return self._with_cors(request.make_response("", headers=self._cors_headers(), status=204))

        client_id = None
        try:
            connection, _token = self._require_connection(allow_no_auth=True)
            if connection:
                user = self._resolve_user(connection, params.get("user_id"))
                self._build_mcp_env(connection, user)
                request.mcp_user = user
            else:
                request.mcp_user = None

            client_id = self._register_sse()

            start_time = time.time()
            _logger.info(
                "sse_open %s",
                json.dumps(
                    {
                        "client_ip": client_id,
                        "auth_mode": getattr(request, "auth_mode", None),
                        "active": self._SSE_ACTIVE.get(client_id, 0),
                    }
                ),
            )

            def guarded_stream():
                reason = "complete"
                try:
                    yield from self._stream()
                except GeneratorExit:
                    reason = "client_disconnect"
                    raise
                except Exception:
                    reason = "error"
                    raise
                finally:
                    MCPGatewayController._release_sse(client_id)
                    duration = time.time() - start_time
                    _logger.info(
                        "sse_close %s",
                        json.dumps(
                            {
                                "client_ip": client_id,
                                "auth_mode": getattr(request, "auth_mode", None),
                                "duration": round(duration, 3),
                                "reason": reason,
                                "active": self._SSE_ACTIVE.get(client_id, 0),
                            }
                        ),
                    )

            stream = guarded_stream()
            response = self._sse_response(stream)
            self._log_access("/mcp/sse", status=response.get("status", 200), outcome="ok")
            return response
        except Unauthorized as exc:
            response = self._sse_error_response(str(exc), code="MCP_AUTH_ERROR", status=401)
            self._log_access("/mcp/sse", status=response.get("status", 401), outcome="unauthorized")
            return response
        except TooManyRequests as exc:
            response = self._sse_error_response(str(exc), code="MCP_RATE_LIMIT", status=429)
            self._log_access("/mcp/sse", status=response.get("status", 429), outcome="rate_limited")
            return response
        except Exception:
            if client_id:
                MCPGatewayController._release_sse(client_id)
            _logger.exception(
                "Unexpected error while establishing MCP SSE stream for %s",
                MCPGatewayController._client_id(),
            )
            response = self._sse_error_response(
                "Unable to establish the MCP stream. Please retry shortly.",
                code="MCP_SSE_ERROR",
                status=500,
            )
            self._log_access("/mcp/sse", status=response.get("status", 500), outcome="error")
            return response
