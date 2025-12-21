from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMModelVariant(models.Model):
    _name = "llm.model.variant"
    _description = "LLM Model Variant"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    provider_id = fields.Many2one(
        "llm.provider",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="provider_id.company_id",
        store=True,
        readonly=True,
    )
    capabilities = fields.Char(
        help="Comma-separated capabilities such as chat, embedding, function_calling",
    )
    pricing_json = fields.Json(help="Pricing metadata returned by the provider")
    function_calling = fields.Boolean(default=False, tracking=True)
    vision_enabled = fields.Boolean(default=False, tracking=True)
    context_window = fields.Integer(
        help="Maximum tokens the model can process in a single request",
        tracking=True,
    )
    enabled = fields.Boolean(default=True)

    @api.constrains("context_window")
    def _check_context_window_positive(self):
        for record in self:
            if record.context_window is not None and record.context_window <= 0:
                raise ValidationError(
                    _("Context window must be a positive integer when specified."),
                )

    _sql_constraints = [
        (
            "name_provider_unique",
            "unique(name, provider_id)",
            "Model variant names must be unique per provider.",
        )
    ]
