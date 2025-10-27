# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    brand_attribute_id = fields.Many2one(
        comodel_name="product.attribute",
        string="Brand Attribute",
        config_parameter="rmc.brand_attribute_id",
        help="Select which product attribute represents the Brand used to drive subcontractor mappings.",
    )
    brand_attribute_warning = fields.Char(
        compute="_compute_brand_attribute_warning",
        readonly=True,
    )

    def _compute_brand_attribute_warning(self):
        param = self.env["ir.config_parameter"].sudo().get_param("rmc.brand_attribute_id")
        warning = _(
            "No Brand attribute has been selected. The system will fall back to an attribute named 'Brand' if present."
        )
        for settings in self:
            settings.brand_attribute_warning = warning if not param else False
