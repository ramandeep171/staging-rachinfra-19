# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .brand_utils import is_mapping_current


class RmcPavSubcontractorMap(models.Model):
    _name = "rmc.pav.subcontractor.map"
    _description = "Brand Attribute Value Subcontractor Mapping"
    _order = "sequence, id"

    product_attribute_value_id = fields.Many2one(
        comodel_name="product.attribute.value",
        string="Attribute Value",
        required=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Subcontractor",
        required=True,
        domain=[("is_subcontractor", "=", True)],
    )
    sequence = fields.Integer(default=10, help="Lower values have higher priority.")
    valid_from = fields.Date()
    valid_to = fields.Date()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "pav_partner_unique",
            "unique(product_attribute_value_id, partner_id)",
            "The subcontractor is already mapped to this Brand value.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_brand_attribute()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._check_brand_attribute()
        return res

    def _check_brand_attribute(self):
        """Ensure only Brand attribute values are used."""
        param_value = self.env["ir.config_parameter"].sudo().get_param("rmc.brand_attribute_id")
        brand_attribute = False
        if param_value:
            try:
                brand_attribute = int(param_value)
            except (TypeError, ValueError):
                brand_attribute = False
        for record in self:
            attribute_id = record.product_attribute_value_id.attribute_id.id
            if brand_attribute and attribute_id != brand_attribute:
                raise ValidationError(
                    _("Subcontractors can only be linked to the configured Brand attribute values.")
                )
            if not brand_attribute and record.product_attribute_value_id.attribute_id.name != "Brand":
                raise ValidationError(
                    _("Subcontractors can only be linked to attribute values named 'Brand' when no Brand attribute is configured.")
                )

    def get_current_subcontractor_maps(self, reference_date=None):
        valid = self.filtered(lambda mapping: is_mapping_current(mapping, reference_date=reference_date))
        return valid.sorted(key=lambda mapping: (mapping.sequence, mapping.id))


class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"

    subcontractor_map_ids = fields.One2many(
        comodel_name="rmc.pav.subcontractor.map",
        inverse_name="product_attribute_value_id",
        string="Brand Subcontractors",
    )

    def get_current_subcontractor_maps(self, reference_date=None):
        self.ensure_one()
        return self.subcontractor_map_ids.get_current_subcontractor_maps(reference_date=reference_date)
