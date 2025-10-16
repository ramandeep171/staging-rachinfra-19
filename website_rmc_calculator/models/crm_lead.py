from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    rmc_volume = fields.Float(string='RMC Volume (m³)')
    rmc_grade_tmpl_id = fields.Many2one('product.template', string='RMC Grade Template')
    rmc_variant_id = fields.Many2one('product.product', string='RMC Variant')
