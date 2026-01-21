# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MaintenanceRequestSpare(models.Model):
    _name = "maintenance.request.spare"
    _description = "Maintenance Request Spare Line"

    request_id = fields.Many2one('maintenance.request', string='Request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    qty = fields.Float(string='Qty', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='UoM')
    picking_id = fields.Many2one('stock.picking', string='Issued Picking', readonly=True)

    @api.onchange('product_id')
    def _onchange_product(self):
        for rec in self:
            if rec.product_id:
                rec.uom_id = rec.product_id.uom_id
                if not rec.description:
                    rec.description = rec.product_id.display_name
