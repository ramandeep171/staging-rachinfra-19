import os
from typing import List

try:
    from odoo.tools import config as odoo_config  # type: ignore
except ImportError:  # pragma: no cover - used only when Odoo isn't installed (tests)

    class _FallbackConfig(dict):
        def get(self, key, default=None):
            return default

    odoo_config = _FallbackConfig()  # type: ignore


MCP_ROUTE_PREFIX_PARAM = "mcp_proxy_prefix"
_DEFAULT_PROXY_PREFIXES = ("odoo",)


def _split_prefixes(raw_value: str):
    for chunk in raw_value.split(","):
        cleaned = chunk.strip().strip("/")
        if cleaned:
            yield cleaned


def _configured_prefixes() -> List[str]:
    prefixes = [""]
    seen = {""}

    config_values = filter(
        None,
        (
            odoo_config.get("llm_mcp_route_prefixes"),
            odoo_config.get("llm_mcp_route_prefix"),
            odoo_config.get("http_root"),
        ),
    )
    env_values = filter(
        None,
        (
            os.environ.get("LLM_MCP_ROUTE_PREFIXES"),
            os.environ.get("LLM_MCP_ROUTE_PREFIX"),
        ),
    )

    sources = list(config_values) + list(env_values)
    for source in sources:
        for prefix in _split_prefixes(source):
            if prefix in seen:
                continue
            seen.add(prefix)
            prefixes.append(prefix)

    for default in _DEFAULT_PROXY_PREFIXES:
        if default in seen:
            continue
        seen.add(default)
        prefixes.append(default)
    return prefixes


def mcp_route_paths(path: str) -> List[str]:
    """Return the canonical MCP path plus any configured prefixed variants."""
    if not path.startswith("/"):
        raise ValueError("MCP routes must start with '/'")

    routes = []
    for prefix in _configured_prefixes():
        routes.append(f"/{prefix}{path}" if prefix else path)
    trimmed = path.lstrip("/")
    if trimmed:
        routes.append(f"/<path:{MCP_ROUTE_PREFIX_PARAM}>/{trimmed}")
    return routes
