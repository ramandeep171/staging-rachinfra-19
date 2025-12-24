import itertools
import json
import logging
import types

import pytest

from llm_mcp.controllers.mcp_gateway import MCPGatewayController, TooManyRequests, Unauthorized, request


def _reset_request(headers=None, *, preserve_oauth_map=False):
    request.httprequest.headers = headers or {}
    request.httprequest.method = "GET"
    request.httprequest.host_url = "https://localhost"
    request.httprequest.remote_addr = request.httprequest.__dict__.get("remote_addr", "127.0.0.1")
    request.context = {}
    request.auth_mode = None
    request.env = type(request.env)()
    request.jsonrequest = {}
    if not preserve_oauth_map:
        MCPGatewayController._OAUTH_TOKEN_MAP = {}
    MCPGatewayController._SSE_ACTIVE = {}
    MCPGatewayController._NO_AUTH_REQUESTS = {}
    for attr in ("mcp_connection", "mcp_token", "mcp_context", "mcp_company"):
        if hasattr(request, attr):
            delattr(request, attr)


def _fake_connection():
    user = types.SimpleNamespace(id=42)
    company = types.SimpleNamespace(id=7)

    class _Connection:
        def __init__(self):
            self.id = 99
            self.user_id = user
            self.company_id = company

        def sudo(self):
            return self

        def authenticate_token(self, token):
            self.last_token = token
            return self

    return _Connection()


def test_detects_auth_modes_and_sets_context():
    _reset_request({"Authorization": "Bearer abc"})
    assert MCPGatewayController._detect_auth_mode() == "bearer"

    _reset_request({"Authorization": "OAuth something"})
    assert MCPGatewayController._detect_auth_mode() == "oauth"

    _reset_request({"X-LLM-Token": "token"})
    assert MCPGatewayController._detect_auth_mode() == "bearer"

    _reset_request({})
    assert MCPGatewayController._detect_auth_mode() == "no_auth"

    MCPGatewayController._set_auth_mode("bearer")
    assert request.context["auth_mode"] == "bearer"
    assert request.auth_mode == "bearer"


def test_require_connection_allows_discovery_without_token():
    _reset_request({})
    connection, token = MCPGatewayController._require_connection(allow_no_auth=True)
    assert connection is None
    assert token is None
    assert request.context["auth_mode"] == "no_auth"


def test_require_connection_rejects_missing_token_for_execution():
    _reset_request({})
    with pytest.raises(Unauthorized):
        MCPGatewayController._require_connection(allow_no_auth=False)


def test_json_helpers_and_serialization():
    _reset_request({})
    error_response = MCPGatewayController._json_error("bad", code="TEST", status=418)
    parsed = json.loads(error_response["body"])
    assert parsed == {"error": {"code": "TEST", "message": "bad"}}
    assert error_response["status"] == 418
    assert error_response["headers"]["Content-Type"] == "application/json"

    tools = MCPGatewayController._serialize_tools(
        [
            {"name": "t1", "description": "d", "input_schema": {"type": "object"}},
            {"tool_key": "t2", "schema": {"type": "null"}},
        ]
    )
    assert tools == [
        {"name": "t1", "description": "d", "input_schema": {"type": "object"}},
        {"name": "t2", "description": "", "input_schema": {"type": "null"}},
    ]


def test_sse_event_formatting():
    _reset_request({})
    controller = MCPGatewayController()
    event = controller._sse_event("heartbeat", {"ok": True})
    assert event.startswith("event: heartbeat")
    assert "data: " in event
    assert event.strip().endswith("}")


def test_sse_handshake_includes_ready_event():
    _reset_request({"Authorization": "Bearer token"})

    connection = _fake_connection()

    class _ToolRegistry:
        def list_tools(self, **_kwargs):
            return []

    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = _ToolRegistry()

    controller = MCPGatewayController()
    response = controller.sse()

    assert response["headers"]["Content-Type"] == "text/event-stream"
    assert response["headers"].get("X-Accel-Buffering") == "no"
    assert response["headers"].get("Cache-Control") == "no-cache"
    stream = response["body"]
    first_event = next(stream).decode()
    assert first_event.startswith("event: ready\n")
    assert "data: {\"protocol\": \"mcp/1.0\"" in first_event
    assert hasattr(stream, "__iter__")


def test_sse_heartbeat_emits_periodically(monkeypatch):
    _reset_request({"Authorization": "Bearer token"})

    connection = _fake_connection()

    class _ToolRegistry:
        def list_tools(self, **_kwargs):
            return []

    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = _ToolRegistry()

    controller = MCPGatewayController()
    controller.HEARTBEAT_INTERVAL = 1

    ticks = {"t": 0}

    def fake_time():
        ticks["t"] += 0.6
        return ticks["t"]

    monkeypatch.setattr(MCPGatewayController, "HEARTBEAT_INTERVAL", 1)
    monkeypatch.setattr("llm_mcp.controllers.mcp_gateway.time.sleep", lambda _s: None)
    monkeypatch.setattr("llm_mcp.controllers.mcp_gateway.time.time", fake_time)

    stream = controller._stream(request.env, connection.user_id, session_id="s1")
    events = list(itertools.islice(stream, 3))
    decoded = [evt.decode() for evt in events]
    assert any(evt.startswith("event: heartbeat") for evt in decoded)


def test_tools_contract_is_json_serializable():
    _reset_request({})

    class _ToolRegistry:
        def list_tools(self, **_kwargs):
            return [
                {"name": "t1", "description": "d", "input_schema": {"type": "object"}},
            ]

    request.env["llm.tool.registry.service"] = _ToolRegistry()

    controller = MCPGatewayController()
    response = controller.list_tools()
    payload = json.loads(response["body"])
    assert list(payload.keys()) == ["tools"]
    assert isinstance(payload["tools"], list)
    assert payload["tools"][0] == {
        "name": "t1",
        "description": "d",
        "input_schema": {"type": "object"},
    }


def test_execute_returns_json_error_on_failure():
    _reset_request({"Authorization": "Bearer token"})
    request.httprequest.method = "POST"

    connection = _fake_connection()

    class _ExecutionRouter:
        def route(self, **_kwargs):
            raise RuntimeError("boom")

    request.env["llm.mcp.connection"] = connection
    request.env["llm.mcp.execution.router"] = _ExecutionRouter()

    controller = MCPGatewayController()
    response = controller.execute(tool="demo")
    payload = json.loads(response["body"])
    assert response["headers"]["Content-Type"] == "application/json"
    assert payload["error"]["code"] == "MCP_EXEC_ERROR"
    assert "Tool execution failed" in payload["error"]["message"]


def test_auth_mode_contract_enforced():
    controller = MCPGatewayController()

    # no_auth should allow tool discovery but deny execution
    _reset_request({})
    request.env["llm.tool.registry.service"] = type("_ToolRegistry", (), {"list_tools": lambda *_a, **_k: []})()
    tools_response = controller.list_tools()
    assert json.loads(tools_response["body"]) == {"tools": []}

    _reset_request({})
    with pytest.raises(Unauthorized):
        controller._require_connection()

    # bearer allows both
    _reset_request({"Authorization": "Bearer token"})
    connection = _fake_connection()
    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = type("_ToolRegistry", (), {"list_tools": lambda *_a, **_k: []})()
    request.env["llm.mcp.execution.router"] = type("_Exec", (), {"route": lambda *_a, **_k: {"ok": True}})()

    tools_response = controller.list_tools()
    assert json.loads(tools_response["body"]) == {"tools": []}

    exec_response = controller.execute(tool="demo")
    assert json.loads(exec_response["body"]) == {"ok": True}


def test_oauth_discovery_endpoints_shape():
    controller = MCPGatewayController()

    _reset_request({})
    metadata = json.loads(controller.oauth_authorization_server()["body"])
    assert set(metadata.keys()) == {
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "scopes_supported",
        "response_types_supported",
    }
    assert metadata["scopes_supported"] == ["mcp"]

    oidc = json.loads(controller.openid_configuration()["body"])
    assert oidc["token_endpoint"].endswith("/oauth/token")
    assert oidc["issuer"].startswith("https://")


def test_oauth_token_maps_to_bearer_and_allows_execute():
    controller = MCPGatewayController()

    _reset_request({})
    token_response = controller.oauth_token(mcp_token="base-token")
    payload = json.loads(token_response["body"])
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"
    assert request.context["auth_mode"] == "oauth"

    oauth_token = payload["access_token"]

    _reset_request({"Authorization": f"Bearer {oauth_token}"}, preserve_oauth_map=True)
    connection = _fake_connection()
    request.env["llm.mcp.connection"] = connection
    request.env["llm.mcp.execution.router"] = type(
        "_Exec", (), {"route": lambda *_a, **_k: {"ok": True}}
    )()
    request.env["llm.tool.registry.service"] = type(
        "_ToolRegistry", (), {"list_tools": lambda *_a, **_k: []}
    )()

    exec_response = controller.execute(tool="demo")
    assert json.loads(exec_response["body"]) == {"ok": True}
    assert getattr(connection, "last_token", None) == "base-token"
    assert request.context["auth_mode"] == "oauth"


def test_bearer_behavior_remains_intact():
    controller = MCPGatewayController()

    _reset_request({"Authorization": "Bearer legacy"})
    assert MCPGatewayController._detect_auth_mode() == "bearer"

    connection = _fake_connection()
    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = type(
        "_ToolRegistry", (), {"list_tools": lambda *_a, **_k: []}
    )()
    request.env["llm.mcp.execution.router"] = type(
        "_Exec", (), {"route": lambda *_a, **_k: {"ok": True}}
    )()

    exec_response = controller.execute(tool="demo")
    assert json.loads(exec_response["body"]) == {"ok": True}
    assert getattr(connection, "last_token", None) == "legacy"


def test_sse_first_event_has_no_prefix_and_heartbeat_after_ready(monkeypatch):
    _reset_request({"Authorization": "Bearer token"})

    connection = _fake_connection()

    class _ToolRegistry:
        def list_tools(self, **_kwargs):
            return []

    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = _ToolRegistry()

    controller = MCPGatewayController()
    controller.HEARTBEAT_INTERVAL = 1
    monkeypatch.setattr("llm_mcp.controllers.mcp_gateway.time.sleep", lambda _s: None)

    ticks = {"t": 0}

    def fake_time():
        ticks["t"] += 0.6
        return ticks["t"]

    monkeypatch.setattr("llm_mcp.controllers.mcp_gateway.time.time", fake_time)

    response = controller.sse()
    stream = response["body"]

    first = next(stream).decode()
    assert first.startswith("event: ready\n")

    next_event = next(stream).decode()
    assert next_event.startswith("event: tools")

    heartbeat_event = next(stream).decode()
    assert heartbeat_event.startswith("event: heartbeat")


def test_options_preflight_returns_cors_headers():
    controller = MCPGatewayController()

    _reset_request({"Origin": "https://client"})
    request.httprequest.method = "OPTIONS"
    response = controller.list_tools()
    assert response["status"] == 204
    assert response["headers"]["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"

    _reset_request({"Origin": "https://client"})
    request.httprequest.method = "OPTIONS"
    response = controller.execute()
    assert response["status"] == 204
    assert "Authorization" in response["headers"]["Access-Control-Allow-Headers"]

    _reset_request({"Origin": "https://client", "Authorization": "Bearer token"})
    request.httprequest.method = "OPTIONS"
    response = controller.sse()
    assert response["status"] == 204
    assert response["headers"].get("Access-Control-Allow-Origin") == "*"


def test_no_auth_rate_limit(monkeypatch):
    controller = MCPGatewayController()
    _reset_request({})
    monkeypatch.setattr(MCPGatewayController, "RATE_LIMIT_NO_AUTH", 1)

    request.env["llm.tool.registry.service"] = type(
        "_ToolRegistry", (), {"list_tools": lambda *_a, **_k: []}
    )()

    first = controller.list_tools()
    assert first["status"] == 200

    with pytest.raises(TooManyRequests):
        controller._require_connection(allow_no_auth=True)


def test_sse_logs_open_and_close(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    controller = MCPGatewayController()
    _reset_request({"Authorization": "Bearer token"})

    connection = _fake_connection()

    class _ToolRegistry:
        def list_tools(self, **_kwargs):
            return []

    request.env["llm.mcp.connection"] = connection
    request.env["llm.tool.registry.service"] = _ToolRegistry()

    response = controller.sse()
    stream = response["body"]

    next(stream)  # ready
    stream.close()  # trigger closure logging

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "sse_open" in messages
    assert "sse_close" in messages


def test_rate_limit_emits_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    controller = MCPGatewayController()
    _reset_request({})
    monkeypatch.setattr(MCPGatewayController, "RATE_LIMIT_NO_AUTH", 0)

    with pytest.raises(TooManyRequests):
        controller._require_connection(allow_no_auth=True)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "no_auth_rate_limited" in messages


def test_no_auth_execute_attempt_warns(caplog):
    caplog.set_level(logging.WARNING)
    controller = MCPGatewayController()
    _reset_request({})

    with pytest.raises(Unauthorized):
        controller._require_connection()

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "no_auth_execute_blocked" in messages


def test_oauth_token_issue_logged(caplog):
    caplog.set_level(logging.INFO)
    controller = MCPGatewayController()
    _reset_request({})

    response = controller.oauth_token(mcp_token="base-token")
    assert response["status"] == 200

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "oauth_token_issued" in messages
