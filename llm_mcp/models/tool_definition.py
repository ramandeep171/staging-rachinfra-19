from odoo import fields, models


class LLMToolDefinition(models.Model):
    _inherit = "llm.tool.definition"

    mcp_consent_template_id = fields.Many2one(
        "llm.mcp.consent.template",
        string="MCP Consent Template",
        ondelete="restrict",
        help="Template used to enforce runtime consent when the tool is executed via MCP or agent flows.",
    )

    def _has_any_consent_template(self):
        res = super()._has_any_consent_template()
        if res:
            return res
        return bool(self.mcp_consent_template_id)
