import pytest

from llm_mcp.controllers import route_utils


def _clear_env(monkeypatch):
    for var in ("LLM_MCP_ROUTE_PREFIXES", "LLM_MCP_ROUTE_PREFIX"):
        monkeypatch.delenv(var, raising=False)


def test_route_paths_default(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(route_utils, "odoo_config", {}, raising=False)
    assert route_utils.mcp_route_paths("/mcp/sse") == ["/mcp/sse"]


def test_route_paths_from_env(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(route_utils, "odoo_config", {}, raising=False)
    monkeypatch.setenv("LLM_MCP_ROUTE_PREFIXES", "odoo , api/v1 ")
    assert route_utils.mcp_route_paths("/mcp/tools") == [
        "/mcp/tools",
        "/odoo/mcp/tools",
        "/api/v1/mcp/tools",
    ]


def test_route_paths_from_config(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(route_utils, "odoo_config", {"llm_mcp_route_prefix": "/core"})
    assert route_utils.mcp_route_paths("/mcp/execute") == [
        "/mcp/execute",
        "/core/mcp/execute",
    ]


def test_route_path_requires_leading_slash(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValueError):
        route_utils.mcp_route_paths("mcp/sse")
