from odoo import fields, models


class RmcProductBrand(models.Model):
    _name = "rmc.product.brand"
    _description = "RMC Product Brand"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    description = fields.Text()

    _sql_constraints = [
        ("rmc_product_brand_name_uniq", "unique(name)", "Brand name must be unique."),
    ]
