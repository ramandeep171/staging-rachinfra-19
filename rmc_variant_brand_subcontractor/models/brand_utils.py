# -*- coding: utf-8 -*-
from datetime import date

from odoo import _
from odoo.exceptions import UserError


def get_brand_attribute(env):
    """Return the configured Brand attribute record (may be empty)."""
    param = env["ir.config_parameter"].sudo()
    attribute_id = param.get_param("rmc.brand_attribute_id")
    if attribute_id:
        attribute = env["product.attribute"].browse(int(attribute_id))
        if attribute.exists():
            return attribute
    # fallback by name
    return env["product.attribute"].search([("name", "=", "Brand")], limit=1)


def ensure_brand_attribute_configured(env):
    """Raise an explicit error if no brand attribute can be determined."""
    attribute = get_brand_attribute(env)
    if not attribute:
        raise UserError(_("Configure a Brand attribute in settings before using this feature."))
    return attribute


def get_variant_brand_ptav(product):
    """Return the Brand product.template.attribute.value of the given variant."""
    attribute = get_brand_attribute(product.env)
    if not attribute:
        return product.env["product.template.attribute.value"]
    brand_ptavs = product.product_template_attribute_value_ids.filtered(
        lambda ptav: ptav.attribute_id == attribute
    )
    return brand_ptavs[:1]


def is_mapping_current(mapping, reference_date=None):
    """Check if the mapping is active and valid for the reference date (defaults today)."""
    if not mapping.active:
        return False
    reference_date = reference_date or date.today()
    if mapping.valid_from and mapping.valid_from > reference_date:
        return False
    if mapping.valid_to and mapping.valid_to < reference_date:
        return False
    return True
