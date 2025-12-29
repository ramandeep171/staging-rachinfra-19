"""Tool metadata sanitizer to protect LLM prompts from injection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping


@dataclass
class ToolSanitizer:
    """Sanitize tool metadata before exposing it to LLM prompts."""

    max_name_length: int = 80
    max_description_length: int = 600
    max_properties: int = 32
    max_required: int = 16
    max_enum_items: int = 25
    max_depth: int = 4
    max_schema_nodes: int = 200
    allowed_schema_keys: set[str] = field(
        default_factory=lambda: {
            "type",
            "title",
            "description",
            "properties",
            "required",
            "items",
            "enum",
            "format",
            "minimum",
            "maximum",
            "minLength",
            "maxLength",
            "default",
            "additionalProperties",
            "oneOf",
            "anyOf",
            "allOf",
            "pattern",
            "minItems",
            "maxItems",
        }
    )

    def sanitize_tool(self, tool: Mapping[str, Any]) -> Dict[str, Any]:
        """Return a pruned tool payload with only safe fields."""

        safe_name = self._sanitize_text(
            tool.get("name") or tool.get("tool_key") or "",
            self.max_name_length,
        )
        safe_description = self._sanitize_text(
            tool.get("description") or "",
            self.max_description_length,
        )
        raw_schema = tool.get("input_schema") or tool.get("schema") or {}
        schema_budget = self.max_schema_nodes
        safe_schema, _ = self._sanitize_schema(raw_schema, depth=0, budget=schema_budget)

        return {
            "name": safe_name,
            "description": safe_description,
            "input_schema": safe_schema,
        }

    def sanitize_tools(self, tools: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self.sanitize_tool(tool) for tool in tools]

    def _sanitize_text(self, value: Any, max_length: int) -> str:
        text = value if isinstance(value, str) else str(value)
        text = text.replace("\u0000", "")
        return text[:max_length].strip()

    def _sanitize_schema(
        self, schema: Any, *, depth: int, budget: int
    ) -> tuple[Dict[str, Any], int]:
        """Prune schema to allowed keys, depth, and size budget."""

        if budget <= 0 or depth >= self.max_depth:
            return {}, budget

        if not isinstance(schema, dict):
            return {}, budget

        budget -= 1
        safe: Dict[str, Any] = {}

        for key, value in schema.items():
            if key not in self.allowed_schema_keys:
                continue

            if key in {"title", "description"}:
                safe[key] = self._sanitize_text(value, self.max_description_length)
            elif key == "properties":
                safe[key], budget = self._sanitize_properties(value, depth, budget)
            elif key == "items":
                sanitized_items, budget = self._sanitize_schema(
                    value, depth=depth + 1, budget=budget
                )
                safe[key] = sanitized_items
            elif key == "required":
                safe[key] = self._sanitize_required(value)
            elif key == "enum":
                safe[key] = self._sanitize_enum(value)
            elif key in {"oneOf", "anyOf", "allOf"}:
                sanitized_options: List[Dict[str, Any]] = []
                if isinstance(value, list):
                    for option in value[: self.max_properties]:
                        sanitized_option, budget = self._sanitize_schema(
                            option, depth=depth + 1, budget=budget
                        )
                        sanitized_options.append(sanitized_option)
                safe[key] = sanitized_options
            elif key == "additionalProperties":
                if isinstance(value, bool):
                    safe[key] = value
                elif isinstance(value, dict):
                    sanitized_ap, budget = self._sanitize_schema(
                        value, depth=depth + 1, budget=budget
                    )
                    safe[key] = sanitized_ap
            else:
                safe[key] = value

            if budget <= 0:
                break

        return safe, budget

    def _sanitize_properties(
        self, properties: Any, depth: int, budget: int
    ) -> tuple[Dict[str, Any], int]:
        if not isinstance(properties, dict):
            return {}, budget

        safe_props: Dict[str, Any] = {}
        for prop_name, prop_schema in list(properties.items())[: self.max_properties]:
            sanitized_schema, budget = self._sanitize_schema(
                prop_schema, depth=depth + 1, budget=budget
            )
            safe_props[self._sanitize_text(prop_name, self.max_name_length)] = sanitized_schema
            if budget <= 0:
                break

        return safe_props, budget

    def _sanitize_required(self, required: Any) -> List[str]:
        if not isinstance(required, list):
            return []
        safe_required: List[str] = []
        for item in required[: self.max_required]:
            if isinstance(item, str):
                safe_required.append(self._sanitize_text(item, self.max_name_length))
        return safe_required

    def _sanitize_enum(self, enum_values: Any) -> List[Any]:
        if not isinstance(enum_values, list):
            return []
        sanitized = []
        for val in enum_values[: self.max_enum_items]:
            sanitized.append(val if isinstance(val, (str, int, float)) else str(val))
        return sanitized


DEFAULT_TOOL_SANITIZER = ToolSanitizer()
