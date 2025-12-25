from odoo import api, models


class MCPToolRegistryService(models.AbstractModel):
    _inherit = "llm.tool.registry.service"

    @api.model
    def _requires_consent(self, tool):
        requires = super()._requires_consent(tool)
        if requires:
            return requires
        return bool(getattr(tool, "mcp_consent_template_id", False))

    @api.model
    def _get_mcp_template(self, tool):
        template_model = self.env["llm.mcp.consent.template"]
        return template_model._select_template_for_tool(tool)

    @api.model
    def _has_valid_consent(self, tool, user):
        if self.env.context.get("is_mcp"):
            # Trusted MCP tokens bypass runtime consent checks to keep the agent flow unblocked.
            return True
        template = self._get_mcp_template(tool)
        if not template:
            return super()._has_valid_consent(tool, user)

        ledger_model = self.env["llm.mcp.consent.ledger"]
        ledger_entry = ledger_model.search(
            [
                ("tool_id", "=", tool.id),
                ("template_id", "=", template.id),
                ("user_id", "=", user.id),
                ("decision", "=", "granted"),
                ("expired", "=", False),
            ],
            limit=1,
        )
        return bool(ledger_entry)
