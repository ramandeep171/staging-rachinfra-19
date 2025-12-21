from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestToolPermissions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_internal = cls.env.ref("base.group_user")
        cls.group_portal = cls.env.ref("base.group_portal")
        cls.public_user = cls.env.ref("base.public_user")

        user_model = cls.env["res.users"].sudo()
        cls.grouped_user = user_model.create(
            {
                "name": "Grouped User",
                "login": "grouped_user",
                "email": "grouped@example.com",
                "groups_id": [(6, 0, cls.group_internal.ids)],
            }
        )
        cls.outsider_user = user_model.create(
            {
                "name": "Outsider User",
                "login": "outsider_user",
                "email": "outsider@example.com",
                "groups_id": [(6, 0, cls.group_portal.ids)],
            }
        )

        definition_model = cls.env["llm.tool.definition"].sudo()
        cls.group_tool = definition_model.create(
            {
                "name": "restricted_tool",
                "action_type": "external_api",
                "description": "Restricted to internal users",
                "access_group_ids": [(6, 0, cls.group_internal.ids)],
                "schema_json": {"type": "object", "properties": {}},
            }
        )
        cls.open_tool = definition_model.create(
            {
                "name": "open_world_tool",
                "action_type": "external_api",
                "description": "Callable without group membership",
                "is_open_world": True,
                "schema_json": {"type": "object", "properties": {}},
            }
        )

    def test_user_in_group_can_call(self):
        guard = self.env["llm.tool.permission.guard"]
        decision = guard.can_call(self.group_tool, user=self.grouped_user)
        self.assertTrue(decision.get("allowed"))

        registry = self.env["llm.tool.registry.service"]
        tools = registry.list_tools(user=self.grouped_user)
        names = {tool["tool_key"] for tool in tools}
        self.assertIn(self.group_tool.name, names)

    def test_user_not_in_group_blocked_and_hidden(self):
        guard = self.env["llm.tool.permission.guard"]
        decision = guard.can_call(self.group_tool, user=self.outsider_user)
        self.assertFalse(decision.get("allowed"))

        registry = self.env["llm.tool.registry.service"]
        tools = registry.list_tools(user=self.outsider_user)
        names = {tool["tool_key"] for tool in tools}
        self.assertNotIn(self.group_tool.name, names)

        with self.assertRaises(UserError):
            guard.ensure_can_call(self.group_tool, user=self.outsider_user)

    def test_open_world_tool_allows_public(self):
        guard = self.env["llm.tool.permission.guard"]
        decision = guard.can_call(self.open_tool, user=self.public_user)
        self.assertTrue(decision.get("allowed"))

        registry = self.env["llm.tool.registry.service"]
        tools = registry.list_tools(user=self.public_user)
        names = {tool["tool_key"] for tool in tools}
        self.assertIn(self.open_tool.name, names)

    def test_group_change_applies_immediately(self):
        new_group = self.env["res.groups"].sudo().create(
            {"name": "Temporary Access", "implied_ids": [(6, 0, self.group_internal.ids)]}
        )
        temp_user = self.env["res.users"].sudo().create(
            {
                "name": "Temporary User",
                "login": "temp_user",
                "email": "temp@example.com",
                "groups_id": [(6, 0, new_group.ids)],
            }
        )
        guard = self.env["llm.tool.permission.guard"]

        denied = guard.can_call(self.group_tool, user=temp_user)
        self.assertFalse(denied.get("allowed"))

        self.group_tool.write({"access_group_ids": [(6, 0, new_group.ids)]})
        allowed = guard.can_call(self.group_tool, user=temp_user)
        self.assertTrue(allowed.get("allowed"))
