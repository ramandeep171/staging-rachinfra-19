from typing import Iterable, List, Optional

from odoo import api, models


class ToolRegistryService(models.AbstractModel):
    _name = "llm.tool.registry.service"
    _description = "Tool Registry Service"

    @api.model
    def _prepare_tool_metadata(self, tool, requires_consent: bool) -> dict:
        latest_version = tool.latest_version_id
        return {
            "tool_key": tool.name,
            "description": tool.description or "",
            "version": latest_version.version if latest_version else 1,
            "schema": tool.schema_json or {},
            "tags": tool.tag_ids.mapped("name"),
            "action_type": tool.action_type,
            "consent_required": requires_consent,
            "is_open_world": tool.is_open_world,
            "access_groups": tool.access_group_ids.mapped("display_name"),
        }

    @api.model
    def _requires_consent(self, tool) -> bool:
        if getattr(tool, "requires_user_consent", False):
            return True
        tag_names = {tag.name.lower() for tag in tool.tag_ids}
        if "user-consent" in tag_names:
            return True
        return bool(getattr(tool, "consent_template_id", False))

    @api.model
    def _has_valid_consent(self, tool, user) -> bool:
        # Base module does not track runtime consent decisions.
        return True

    @api.model
    def _passes_group_filter(self, tool, user) -> bool:
        guard = self.env["llm.tool.permission.guard"]
        return guard.can_call(tool, user=user).get("allowed")

    @api.model
    def list_tools(
        self,
        user,
        tags: Optional[Iterable[str]] = None,
        action_types: Optional[Iterable[str]] = None,
        session_id: Optional[str] = None,
    ) -> List[dict]:
        user = (user or self.env.user).sudo()
        tools = self.env["llm.tool.definition"].sudo().search([("enabled", "=", True)])

        tags = {tag.lower() for tag in (tags or []) if tag}
        action_types = {action for action in (action_types or []) if action}

        visible_tools: List[dict] = []

        for tool in tools:
            if tags and not tags.intersection({tag.name.lower() for tag in tool.tag_ids}):
                continue
            if action_types and tool.action_type not in action_types:
                continue
            if not self._passes_group_filter(tool, user):
                continue

            requires_consent = self._requires_consent(tool)
            if requires_consent and not self._has_valid_consent(tool, user):
                continue

            visible_tools.append(self._prepare_tool_metadata(tool, requires_consent))

        return visible_tools
