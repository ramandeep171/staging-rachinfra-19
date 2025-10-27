# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .brand_utils import get_variant_brand_ptav


class ProductProduct(models.Model):
    _inherit = "product.product"

    allowed_subcontractor_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Allowed Subcontractors",
        compute="_compute_allowed_subcontractor_ids",
        compute_sudo=True,
    )

    @api.depends(
        "product_template_attribute_value_ids",
        "product_template_attribute_value_ids.subcontractor_map_ids",
        "product_template_attribute_value_ids.subcontractor_map_ids.active",
        "product_template_attribute_value_ids.subcontractor_map_ids.sequence",
        "product_template_attribute_value_ids.subcontractor_map_ids.valid_from",
        "product_template_attribute_value_ids.subcontractor_map_ids.valid_to",
        "product_template_attribute_value_ids.product_attribute_value_id.subcontractor_map_ids",
        "product_template_attribute_value_ids.product_attribute_value_id.subcontractor_map_ids.active",
        "product_template_attribute_value_ids.product_attribute_value_id.subcontractor_map_ids.sequence",
        "product_template_attribute_value_ids.product_attribute_value_id.subcontractor_map_ids.valid_from",
        "product_template_attribute_value_ids.product_attribute_value_id.subcontractor_map_ids.valid_to",
    )
    def _compute_allowed_subcontractor_ids(self):
        for product in self:
            ptav = get_variant_brand_ptav(product)
            if ptav:
                partners = ptav.get_current_subcontractor_maps().mapped("partner_id")
                product.allowed_subcontractor_ids = partners
            else:
                product.allowed_subcontractor_ids = self.env["res.partner"].browse()

    def _select_seller(self, partner_id=False, quantity=0.0, date=None, uom_id=False, params=False):
        """Prioritize Brand subcontractors before falling back to standard suppliers."""
        self.ensure_one()
        seller = False
        if not partner_id:
            seller = self._rmc_select_brand_seller(quantity=quantity, date=date, uom_id=uom_id, params=params)
        return seller or super()._select_seller(
            partner_id=partner_id, quantity=quantity, date=date, uom_id=uom_id, params=params
        )

    def _rmc_select_brand_seller(self, quantity=0.0, date=None, uom_id=False, params=False):
        """Return/prepare a supplierinfo record based on Brand subcontractors."""
        ptav = get_variant_brand_ptav(self)
        if not ptav:
            return False
        mappings = ptav.get_current_subcontractor_maps(reference_date=date)
        if not mappings:
            return False

        company_id = False
        if params and params.get("company_id") is not None:
            company_id = params["company_id"]
        elif self.env.context.get("force_company"):
            company_id = self.env.context["force_company"]
        elif self.env.company:
            company_id = self.env.company.id

        SupplierInfo = self.env["product.supplierinfo"].sudo()
        if company_id:
            company_domain = [company_id, False]
        elif self.env.company:
            company_domain = [self.env.company.id, False]
        else:
            company_domain = [False]

        for mapping in mappings:
            domain = [
                ("partner_id", "=", mapping.partner_id.id),
                ("product_tmpl_id", "=", self.product_tmpl_id.id),
                ("company_id", "in", company_domain),
            ]
            supplier = SupplierInfo.search(domain, limit=1)
            if supplier:
                if supplier.sequence != mapping.sequence:
                    supplier.sequence = mapping.sequence
                return supplier

            supplier_vals = {
                "partner_id": mapping.partner_id.id,
                "product_tmpl_id": self.product_tmpl_id.id,
                "product_id": self.id,
                "min_qty": max(quantity or 1.0, 1.0),
                "sequence": mapping.sequence,
                "delay": 1,
            }
            if company_id:
                supplier_vals["company_id"] = company_id
            supplier = SupplierInfo.create(supplier_vals)
            return supplier
        return False

    def _get_default_subcontractor(self):
        """Return the highest priority subcontractor for this product variant."""
        self.ensure_one()
        ptav = get_variant_brand_ptav(self)
        if not ptav:
            return self.env["res.partner"].browse()
        mapping = ptav.get_current_subcontractor_maps()[:1]
        return mapping.partner_id if mapping else self.env["res.partner"].browse()
