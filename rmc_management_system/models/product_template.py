from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rmc_product = fields.Boolean(string="Is RMC Product", help="Mark if this is a Ready Mix Concrete product")