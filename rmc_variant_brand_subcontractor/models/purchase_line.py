# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .brand_utils import get_variant_brand_ptav


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    x_subcontractor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Subcontractor (Brand-locked)",
        help=_("Comes from the product variant's Brand value mapping."),
    )

    @api.onchange("product_id")
    def _onchange_product_id_subcontractor(self):
        if not self.product_id:
            self.x_subcontractor_id = False
            return {"domain": {"x_subcontractor_id": [("id", "=", False)]}}
        brand_ptav = get_variant_brand_ptav(self.product_id)
        if not brand_ptav:
            self.x_subcontractor_id = False
            return {
                "warning": {
                    "title": _("No Brand Value"),
                    "message": _(
                        "The selected product variant does not have a Brand attribute value. "
                        "Configure the Brand on the product to enable subcontractor defaults."
                    ),
                },
                "domain": {"x_subcontractor_id": [("id", "=", False)]},
            }
        allowed = self.product_id.allowed_subcontractor_ids
        seller_partners = self.product_id.seller_ids.mapped("partner_id")
        domain_partners = allowed | seller_partners
        if not allowed:
            self.x_subcontractor_id = False
            result = {
                "domain": {"x_subcontractor_id": [("id", "in", seller_partners.ids or [0])]}
            }
            if not seller_partners:
                result["warning"] = {
                    "title": _("No Brand Subcontractor"),
                    "message": _(
                        "No subcontractors are mapped to the Brand value '%s'."
                    )
                    % brand_ptav.name,
                }
            return result
        self.x_subcontractor_id = self.product_id._get_default_subcontractor()
        return {
            "domain": {
                "x_subcontractor_id": [
                    ("id", "in", domain_partners.ids or [0])
                ]
            }
        }

    @api.constrains("x_subcontractor_id", "product_id")
    def _check_x_subcontractor_id(self):
        for line in self:
            if line.x_subcontractor_id and line.product_id:
                allowed = line.product_id.allowed_subcontractor_ids
                if allowed and line.x_subcontractor_id not in allowed:
                    seller_partners = line.product_id.seller_ids.mapped("partner_id")
                    if line.x_subcontractor_id in seller_partners:
                        continue
                    raise ValidationError(
                        _(
                            "The subcontractor '%(partner)s' is not allowed for the Brand value of '%(product)s'."
                        )
                        % {
                            "partner": line.x_subcontractor_id.display_name,
                            "product": line.product_id.display_name,
                        }
                    )
