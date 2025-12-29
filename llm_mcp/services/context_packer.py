import base64
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from odoo import api, models


class LLMContextPackingService(models.AbstractModel):
    _name = "llm.mcp.context.packer"
    _description = "Safely pack MCP tool results for LLM consumption"

    _max_inline_bytes = 4096
    _summary_bytes = 1024

    def _json_bytes(self, payload: Any) -> bytes:
        try:
            return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        except Exception:
            # Last-resort serialization to avoid blocking responses
            return str(payload).encode("utf-8")

    def _should_pack(self, raw_bytes: bytes) -> bool:
        return len(raw_bytes) > (self._max_inline_bytes or 0)

    def _store_external(
        self, raw_bytes: bytes, tool, session_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Persist oversized payloads for audit/debug without leaking to LLM."""

        if not tool:
            return None

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        name = f"mcp-result-{tool.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        try:
            attachment = self.env["ir.attachment"].sudo().create(
                {
                    "name": name,
                    "datas": base64.b64encode(raw_bytes),
                    "mimetype": "application/json",
                    "res_model": tool._name,
                    "res_id": tool.id,
                    "description": (
                        f"MCP tool result ({tool.display_name}) for session {session_id}"
                        if session_id
                        else f"MCP tool result for {tool.display_name}"
                    ),
                    "company_id": tool.company_id.id,
                }
            )
        except Exception:  # noqa: BLE001 - best-effort externalization
            return None

        return {
            "attachment_id": attachment.id,
            "sha256": sha256,
            "bytes": len(raw_bytes),
            "name": name,
        }

    @api.model
    def pack_tool_result(
        self, result: Any, *, tool=None, binding=None, session_id: Optional[str] = None
    ):
        """Shrink large results before they reach the LLM context window.

        - Inline small payloads untouched.
        - Summarize and hash oversized payloads; persist full payload to attachment for audit.
        - Never mutate error envelopes to avoid masking failures.
        """

        if isinstance(result, dict) and result.get("error"):
            return result

        raw_bytes = self._json_bytes(result)
        byte_len = len(raw_bytes)

        # Embed lightweight metadata for observability when the payload is small enough
        if not self._should_pack(raw_bytes):
            if isinstance(result, dict):
                meta = result.get("_context_packing", {})
                meta.update(
                    {
                        "packed": False,
                        "bytes": byte_len,
                        "inline_limit": self._max_inline_bytes,
                    }
                )
                result["_context_packing"] = meta
            return result

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        summary_text = raw_bytes[: self._summary_bytes].decode(
            "utf-8", errors="ignore"
        )
        storage_ref = self._store_external(raw_bytes, tool, session_id)

        packed = {
            "summary": summary_text,
            "sha256": sha256,
            "bytes": byte_len,
            "inline_limit": self._max_inline_bytes,
            "truncated": True,
            "packed": True,
            "storage": storage_ref,
            "original_type": type(result).__name__,
        }

        # Prefer a predictable envelope for downstream LLM prompts
        return {"packed_result": packed, "_context_packing": packed}
