"""ChatGPT-compatible MCP function adapter and execution contract builder."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin

from odoo import api, models
from odoo.http import request

from ..security.tool_sanitizer import DEFAULT_TOOL_SANITIZER


class MCPChatGPTAdapter(models.AbstractModel):
    _name = "llm.mcp.chatgpt.adapter"
    _description = "MCP adapter for ChatGPT tool/function compatibility"

    DEFAULT_PARAMETERS: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    @api.model
    def _to_function(self, tool: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a tool into a ChatGPT function payload with safety caps."""

        sanitized = DEFAULT_TOOL_SANITIZER.sanitize_tool(tool)
        tool_key = tool.get("tool_key") or tool.get("name") or sanitized["name"]
        description = sanitized.get("description") or ""
        parameters = sanitized.get("input_schema") or self.DEFAULT_PARAMETERS

        return {
            "name": sanitized["name"],
            "description": description,
            "parameters": parameters,
            "strict": True,
            "x-mcp-tool-key": tool_key,
        }

    @api.model
    def list_functions(
        self,
        *,
        user,
        tags: Optional[Iterable[str]] = None,
        action_types: Optional[Iterable[str]] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        registry = self.env["llm.tool.registry.service"]
        tools = registry.list_tools(
            user=user, tags=tags, action_types=action_types, session_id=session_id
        )
        return [self._to_function(tool) for tool in tools]

    @api.model
    def execution_contract(
        self, *, token: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        base_url = request.httprequest.url_root.rstrip("/")
        execute_url = urljoin(base_url + "/", "mcp/execute")
        sse_url = urljoin(base_url + "/", "mcp/sse")

        return {
            "transport": "https",
            "call": {
                "method": "POST",
                "url": execute_url,
                "headers": {"Authorization": f"Bearer {token}"},
                "body": {
                    "tool": "<function.name>",
                    "params": "<json-object>",
                    "session_id": session_id,
                },
            },
            "stream": {
                "method": "GET",
                "url": sse_url,
                "headers": {"Authorization": f"Bearer {token}"},
                "query": {"session_id": session_id} if session_id else {},
                "events": ["ready", "tools", "heartbeat", "close", "error"],
            },
        }
