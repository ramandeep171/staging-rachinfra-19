from odoo.exceptions import ValidationError
from odoo.tests import SavepointCase


class TestSchemaBuilder(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.builder = cls.env["llm.tool.schema.builder"]
        cls.tool_model = cls.env["llm.tool.definition"]

    def test_generate_schema_from_model_fields(self):
        schema = self.builder.generate_from_model("res.partner")

        self.assertEqual(schema.get("type"), "object")
        self.assertIn("name", schema.get("properties", {}))
        self.assertEqual(schema["properties"]["name"].get("type"), "string")
        self.assertIn("name", schema.get("required", []))

    def test_custom_schema_override_on_create(self):
        manual_schema = {
            "type": "object",
            "properties": {"custom": {"type": "string"}},
            "required": ["custom"],
        }
        tool = self.tool_model.create(
            {
                "name": "custom_schema_tool",
                "action_type": "read",
                "description": "Custom schema read",
                "target_model": "res.partner",
                "schema_json": manual_schema,
            }
        )

        self.assertEqual(tool.schema_json, manual_schema)
        self.assertTrue(tool.latest_version_id)
        self.assertEqual(
            tool.latest_version_id.schema_hash,
            tool._compute_schema_hash(manual_schema),
        )

    def test_schema_version_rehash_on_change(self):
        tool = self.tool_model.create(
            {
                "name": "auto_schema_tool",
                "action_type": "read",
                "description": "Auto schema generation",
                "target_model": "res.partner",
            }
        )

        first_version = tool.latest_version_id
        tool.write({"description": "Updated description"})
        self.assertEqual(tool.latest_version_id.id, first_version.id)

        tool.write(
            {
                "schema_json": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                }
            }
        )
        self.assertGreater(tool.latest_version_id.version, first_version.version)
        self.assertNotEqual(
            tool.latest_version_id.schema_hash, first_version.schema_hash
        )

    def test_validate_payload_errors(self):
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        }
        self.builder.validate_payload(schema, {"count": 5})

        with self.assertRaises(ValidationError):
            self.builder.validate_payload(schema, {"count": "oops"})

        with self.assertRaises(ValidationError):
            self.builder.validate_payload(schema, {})
