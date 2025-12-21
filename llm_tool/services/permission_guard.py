from odoo import _, api, models
from odoo.exceptions import UserError


class ToolPermissionGuard(models.AbstractModel):
    _name = "llm.tool.permission.guard"
    _description = "Tool Permission Guard"

    @api.model
    def can_call(self, tool, user=None, session_id=None):
        """Return a permission decision for the given tool and user.

        The method does not evaluate consent (handled by MCP middleware) but
        focuses on access groups and open-world exposure for token-based agent
        sessions.
        """

        user = (user or self.env.user).sudo()
        if not tool.enabled:
            return {"allowed": False, "reason": "disabled"}

        if tool.is_open_world:
            return {"allowed": True, "reason": "open_world"}

        if tool.access_group_ids:
            if tool.access_group_ids & user.groups_id:
                return {"allowed": True, "reason": "group"}
            return {"allowed": False, "reason": "missing_group"}

        # Default allow when no group restriction or open-world flag is set
        return {"allowed": True, "reason": "unrestricted"}

    @api.model
    def ensure_can_call(self, tool, user=None, session_id=None):
        decision = self.can_call(tool, user=user, session_id=session_id)
        if not decision.get("allowed"):
            raise UserError(
                _("User %(user)s is not allowed to run tool %(tool)s")
                % {"user": (user or self.env.user).name, "tool": tool.display_name}
            )
        return decision
