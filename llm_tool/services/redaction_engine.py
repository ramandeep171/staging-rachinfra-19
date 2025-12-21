import copy
from typing import Any, Dict, Iterable, Optional, Set

from odoo import models


class LLMToolRedactionEngine(models.AbstractModel):
    _name = "llm.tool.redaction.engine"
    _description = "LLM Tool Redaction Engine"

    DEFAULT_FIELDS: Set[str] = {
        "api_key",
        "access_token",
        "token",
        "auth_token",
        "authorization",
        "password",
        "secret",
        "phone_number",
        "user_input",
    }

    TAG_POLICIES = {
        "destructive": {"fields": {"api_key", "access_token", "token", "phone_number"}},
        "user-consent": {"fields": {"user_input"}},
    }

    REDACTION_TOKEN = "***"

    def _extract_policy_fields(self, policy: Optional[Dict[str, Any]]) -> Set[str]:
        if not policy:
            return set()
        fields = policy.get("fields")
        if isinstance(fields, Iterable) and not isinstance(fields, (str, bytes)):
            return {str(field).lower() for field in fields}
        return set()

    def _tag_policy_fields(self, tool) -> Set[str]:
        if not tool:
            return set()
        tag_names = {tag.name.lower() for tag in (tool.tag_ids or [])}
        fields: Set[str] = set()
        for tag_name, policy in self.TAG_POLICIES.items():
            if tag_name in tag_names:
                fields |= self._extract_policy_fields(policy)
        return fields

    def _tool_policy_fields(self, tool) -> Set[str]:
        if not tool:
            return set()
        return self._extract_policy_fields(getattr(tool, "redaction_policy_json", None))

    def _policy_fields(self, tool) -> Set[str]:
        # Tool-level policy overrides tag fallback; default is no redaction.
        fields = self._tool_policy_fields(tool)
        if fields:
            return fields
        tag_fields = self._tag_policy_fields(tool)
        if tag_fields:
            return tag_fields
        return set()

    def _redact_mapping(self, data: Any, fields: Set[str]):
        if not data or not fields:
            return copy.deepcopy(data) if isinstance(data, (dict, list)) else data

        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if isinstance(key, str) and key.lower() in fields:
                    sanitized[key] = self.REDACTION_TOKEN
                else:
                    sanitized[key] = self._redact_mapping(value, fields)
            return sanitized

        if isinstance(data, list):
            return [self._redact_mapping(item, fields) for item in data]

        return data

    def redact_payload(self, tool, payload: Optional[Dict[str, Any]] = None):
        fields = self._policy_fields(tool)
        if not fields:
            return copy.deepcopy(payload) if isinstance(payload, (dict, list)) else payload

        sanitized = self._redact_mapping(payload or {}, fields)
        return sanitized

    def redact_for_logging(
        self,
        tool,
        params: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        fields = self._policy_fields(tool)
        params_redacted = self._redact_mapping(params or {}, fields)
        result_redacted = self._redact_mapping(result or {}, fields)
        return {
            "params": params_redacted,
            "result": result_redacted,
            "fields": fields or set(),
        }
