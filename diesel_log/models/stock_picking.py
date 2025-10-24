# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    diesel_log_id = fields.One2many(
        'diesel.log',
        'picking_id',
        string='Related Diesel Log',
        help='Diesel log entry that generated this picking'
    )
    
    is_fuel_issue = fields.Boolean(
        string='Is Fuel Issue',
        compute='_compute_is_fuel_issue',
        store=True,
        help='True if this picking is a fuel issue operation'
    )
    
    @api.depends('picking_type_id')
    def _compute_is_fuel_issue(self):
        # Get configured fuel operation type
        config = self.env['res.config.settings']
        fuel_operation_type = config._get_fuel_operation_type_id()
        
        for picking in self:
            picking.is_fuel_issue = (
                fuel_operation_type and 
                picking.picking_type_id.id == fuel_operation_type.id
            ) or (
                'fuel' in picking.picking_type_id.name.lower() or
                'diesel' in picking.picking_type_id.name.lower()
            )
    
    def action_view_diesel_log(self):
        """Smart button action to view related diesel log"""
        self.ensure_one()
        if self.diesel_log_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Diesel Log'),
                'res_model': 'diesel.log',
                'res_id': self.diesel_log_id[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False