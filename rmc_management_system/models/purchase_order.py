from odoo import api, fields, models, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.onchange('picking_type_id')
    def onchange_picking_type_id(self):
        # Call parent method first
        result = super().onchange_picking_type_id()
        
        # If there's a warning about subcontracting, remove it
        if result and 'warning' in result and result['warning'].get('message', '').find('subcontracting purposes') != -1:
            # Remove the warning by returning empty dict
            return {}
        
        # Return the original result if no subcontracting warning
        return result
