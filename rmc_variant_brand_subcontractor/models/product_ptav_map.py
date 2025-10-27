# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.fields import Command

from .brand_utils import get_brand_attribute, is_mapping_current


class RmcPtavSubcontractorMap(models.Model):
    _name = "rmc.ptav.subcontractor.map"
    _description = "Brand Attribute Subcontractor Mapping"
    _order = "sequence, id"

    ptav_id = fields.Many2one(
        comodel_name="product.template.attribute.value",
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
            "ptav_partner_unique",
            "unique(ptav_id, partner_id)",
            "The subcontractor is already mapped to this Brand value.",
        )
    ]

    @api.constrains("ptav_id")
    def _check_brand_attribute(self):
        brand_attribute = get_brand_attribute(self.env)
        for rec in self:
            attribute = rec.ptav_id.attribute_id
            if brand_attribute:
                if attribute != brand_attribute:
                    raise ValidationError(
                        _("Subcontractors can only be linked to the configured Brand attribute values.")
                    )
            else:
                if attribute.name != "Brand":
                    raise ValidationError(
                        _("Subcontractors can only be linked to attribute values named 'Brand' when no Brand attribute is configured.")
                    )

    @api.model
    def _load_demo_brand_mapping(self):
        """Populate illustrative demo data for subcontractor mappings."""
        ProductAttribute = self.env["product.attribute"]
        ProductAttributeValue = self.env["product.attribute.value"]
        ProductTemplate = self.env["product.template"]
        ICP = self.env["ir.config_parameter"].sudo()

        brand_attribute = ProductAttribute.search([("name", "=", "Brand")], limit=1)
        if not brand_attribute:
            brand_attribute = ProductAttribute.create({"name": "Brand", "create_variant": "always"})

        value_ultratech = ProductAttributeValue.search(
            [("name", "=", "Ultratech"), ("attribute_id", "=", brand_attribute.id)], limit=1
        )
        if not value_ultratech:
            value_ultratech = ProductAttributeValue.create(
                {"name": "Ultratech", "attribute_id": brand_attribute.id}
            )

        value_jkc = ProductAttributeValue.search(
            [("name", "=", "JKC"), ("attribute_id", "=", brand_attribute.id)], limit=1
        )
        if not value_jkc:
            value_jkc = ProductAttributeValue.create({"name": "JKC", "attribute_id": brand_attribute.id})

        default_category = self.env.ref("product.product_category_all", raise_if_not_found=False)
        if not default_category:
            # fallback to any existing category, otherwise create a generic one
            default_category = self.env["product.category"].search([], limit=1)
        if not default_category:
            default_category = self.env["product.category"].create({"name": "All Products"})

        product_template = ProductTemplate.search([("name", "=", "RMC Demo Cement")], limit=1)
        if not product_template:
            product_template = ProductTemplate.create(
                {
                    "name": "RMC Demo Cement",
                    "type": "consu",
                    "categ_id": default_category.id,
                    "attribute_line_ids": [
                        Command.create(
                            {
                                "attribute_id": brand_attribute.id,
                                "value_ids": [Command.set([value_ultratech.id, value_jkc.id])],
                            }
                        )
                    ],
                }
            )
        else:
            line = product_template.attribute_line_ids.filtered(lambda l: l.attribute_id == brand_attribute)
            if not line:
                product_template.write(
                    {
                        "attribute_line_ids": [
                            Command.create(
                                {
                                    "attribute_id": brand_attribute.id,
                                    "value_ids": [Command.set([value_ultratech.id, value_jkc.id])],
                                }
                            )
                        ]
                    }
                )
            else:
                missing_values = (value_ultratech | value_jkc) - line.value_ids
                if missing_values:
                    line.write({"value_ids": [Command.link(val.id) for val in missing_values]})

        product_template._create_variant_ids()

        ProductTemplateAttributeValue = self.env["product.template.attribute.value"]
        ptav_ultratech = ProductTemplateAttributeValue.search(
            [
                ("product_tmpl_id", "=", product_template.id),
                ("product_attribute_value_id", "=", value_ultratech.id),
            ],
            limit=1,
        )
        ptav_jkc = ProductTemplateAttributeValue.search(
            [
                ("product_tmpl_id", "=", product_template.id),
                ("product_attribute_value_id", "=", value_jkc.id),
            ],
            limit=1,
        )

        partner_model = self.env["res.partner"]
        subcontractor_a = partner_model.search([("name", "=", "Subcontractor A")], limit=1)
        if not subcontractor_a:
            subcontractor_a = partner_model.create(
                {
                    "name": "Subcontractor A",
                    "is_company": True,
                    "company_type": "company",
                    "is_subcontractor": True,
                    "supplier_rank": 1,
                }
            )
        else:
            subcontractor_a.write({"is_subcontractor": True, "supplier_rank": max(subcontractor_a.supplier_rank, 1)})

        subcontractor_b = partner_model.search([("name", "=", "Subcontractor B")], limit=1)
        if not subcontractor_b:
            subcontractor_b = partner_model.create(
                {
                    "name": "Subcontractor B",
                    "is_company": True,
                    "company_type": "company",
                    "is_subcontractor": True,
                    "supplier_rank": 1,
                }
            )
        else:
            subcontractor_b.write({"is_subcontractor": True, "supplier_rank": max(subcontractor_b.supplier_rank, 1)})

        pav_map_model = self.env["rmc.pav.subcontractor.map"]
        if value_ultratech:
            if not pav_map_model.search(
                [
                    ("product_attribute_value_id", "=", value_ultratech.id),
                    ("partner_id", "=", subcontractor_a.id),
                ]
            ):
                pav_map_model.create(
                    {
                        "product_attribute_value_id": value_ultratech.id,
                        "partner_id": subcontractor_a.id,
                        "sequence": 1,
                    }
                )
            if not pav_map_model.search(
                [
                    ("product_attribute_value_id", "=", value_ultratech.id),
                    ("partner_id", "=", subcontractor_b.id),
                ]
            ):
                pav_map_model.create(
                    {
                        "product_attribute_value_id": value_ultratech.id,
                        "partner_id": subcontractor_b.id,
                        "sequence": 10,
                    }
                )
        if value_jkc:
            if not pav_map_model.search(
                [
                    ("product_attribute_value_id", "=", value_jkc.id),
                    ("partner_id", "=", subcontractor_b.id),
                ]
            ):
                pav_map_model.create(
                    {
                        "product_attribute_value_id": value_jkc.id,
                        "partner_id": subcontractor_b.id,
                        "sequence": 1,
                    }
                )

        ICP.set_param("rmc.brand_attribute_id", brand_attribute.id)


class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"

    subcontractor_map_ids = fields.One2many(
        comodel_name="rmc.ptav.subcontractor.map",
        inverse_name="ptav_id",
        string="Brand Subcontractors",
    )

    def get_current_subcontractor_maps(self, reference_date=None):
        """Return active mappings ordered by priority with attribute fallback."""
        self.ensure_one()
        template_maps = self.subcontractor_map_ids.filtered(
            lambda mapping: is_mapping_current(mapping, reference_date=reference_date)
        )
        if template_maps:
            return template_maps.sorted(key=lambda mapping: (mapping.sequence, mapping.id))
        attribute_value = self.product_attribute_value_id
        if not attribute_value:
            return self.env["rmc.ptav.subcontractor.map"]
        return attribute_value.get_current_subcontractor_maps(reference_date=reference_date)
