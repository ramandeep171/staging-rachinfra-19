from odoo import models, fields, api
from odoo.exceptions import UserError
import math
import random


class RmcDocketRecipeLine(models.Model):
    _name = 'rmc.docket.recipe.line'
    _description = 'RMC Docket Recipe Line'

    docket_id = fields.Many2one('rmc.docket', string='Docket', ondelete='cascade')
    material_name = fields.Char('Material', required=True)
    qty_per_cum = fields.Float('Qty per Cum', digits='Product Unit of Measure')


class RmcDocketBatchLine(models.Model):
    _name = 'rmc.docket.batch.line'
    _description = 'RMC Docket Batch Line'

    batch_id = fields.Many2one('rmc.docket.batch', string='Batch', ondelete='cascade')
    material_name = fields.Char('Material')
    quantity = fields.Float('Quantity')
