from typing import Any, Dict

from odoo import _, api, models
from odoo.exceptions import ValidationError


class SchemaBuilderService(models.AbstractModel):
    _name = "llm.tool.schema.builder"
    _description = "LLM Tool Schema Builder"

    _EXCLUDED_FIELDS = {
        "id",
        "display_name",
        "create_uid",
        "create_date",
        "write_uid",
        "write_date",
        "message_follower_ids",
        "message_partner_ids",
        "message_ids",
    }

    _TYPE_MAPPING = {
        "char": "string",
        "text": "string",
        "html": "string",
        "selection": "string",
        "integer": "integer",
        "float": "number",
        "monetary": "number",
        "boolean": "boolean",
        "many2one": "integer",
        "one2many": "array",
        "many2many": "array",
        "date": "string",
        "datetime": "string",
    }

    @api.model
    def generate_from_model(self, model_name: str) -> Dict[str, Any]:
        model = self.env[model_name]
        properties = {}
        required = []
        for name in sorted(model._fields):
            field = model._fields[name]
            if name in self._EXCLUDED_FIELDS:
                continue
            if field.readonly and not field.states:
                continue
            json_type = self._TYPE_MAPPING.get(field.type)
            if not json_type:
                continue

            field_schema: Dict[str, Any] = {"type": json_type}
            if json_type == "array":
                field_schema["items"] = {"type": "integer"}
            if field.type == "selection" and field.selection:
                field_schema["enum"] = [value for value, _label in field.selection]
            if field.help:
                field_schema["description"] = field.help

            properties[name] = field_schema
            if field.required and not field.default:
                required.append(name)

        return {"type": "object", "properties": properties, "required": required}

    @api.model
    def prepare_schema_for_create(self, vals: Dict[str, Any]) -> Dict[str, Any]:
        if "schema_json" in vals:
            return vals.get("schema_json") or {}
        target_model = vals.get("target_model")
        if target_model:
            return self.generate_from_model(target_model)
        return {}

    @api.model
    def prepare_schema_for_write(
        self, tool, vals: Dict[str, Any]
    ) -> Dict[str, Any]:
        if "schema_json" in vals:
            return vals.get("schema_json") or {}
        if vals.get("target_model"):
            return self.generate_from_model(vals["target_model"])
        if not tool.schema_json and tool.target_model:
            return self.generate_from_model(tool.target_model)
        return tool.schema_json or {}

    @api.model
    def validate_payload(self, schema: Dict[str, Any], payload: Dict[str, Any]):
        payload = payload or {}
        schema = schema or {}
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for key in required:
            if key not in payload:
                raise ValidationError(
                    _("Missing required parameter: %(param)s", param=key)
                )

        for key, value in payload.items():
            definition = properties.get(key)
            if not definition:
                continue
            expected_type = definition.get("type")
            if expected_type == "string" and not isinstance(value, str):
                raise ValidationError(
                    _("Parameter %(param)s should be a string", param=key)
                )
            if expected_type == "integer" and not isinstance(value, int):
                raise ValidationError(
                    _("Parameter %(param)s should be an integer", param=key)
                )
            if expected_type == "number" and not isinstance(value, (int, float)):
                raise ValidationError(
                    _("Parameter %(param)s should be a number", param=key)
                )
            if expected_type == "boolean" and not isinstance(value, bool):
                raise ValidationError(
                    _("Parameter %(param)s should be a boolean", param=key)
                )
            if expected_type == "array" and not isinstance(value, list):
                raise ValidationError(
                    _("Parameter %(param)s should be an array", param=key)
                )

    @api.model
    def compute_hash(self, schema: Dict[str, Any]) -> str:
        return self.env["llm.tool.definition"]._compute_schema_hash(schema)
