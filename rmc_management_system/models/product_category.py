from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    is_rmc_category = fields.Boolean(
        string="Is RMC Category",
        help="Mark this category as RMC so any products under it are treated as RMC.")
