from odoo import models, fields, api

class RmcMaterialBalance(models.Model):
    _name = 'rmc.material.balance'
    _description = 'RMC Material Balance'

    partner_id = fields.Many2one('res.partner', string='Customer/Subcontractor')
    material_type = fields.Selection([('cement', 'Cement'), ('sand', 'Sand'), ('aggregate', 'Aggregate'), ('other', 'Other')], string='Material')
    balance_qty = fields.Float(string='Balance Quantity (kg)', default=0.0)
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    last_updated = fields.Datetime(string='Last Updated', default=fields.Datetime.now)

    def action_recalculate_balance(self):
        """Recalculate balance based on all workorders and sale orders for this partner"""
        for record in self:
            total_balance = 0.0
            
            # Calculate from sale orders (materials received)
            sale_orders = self.env['sale.order'].search([('partner_id', '=', record.partner_id.id)])
            for so in sale_orders:
                for line in so.order_line:
                    if line.product_id and line.product_id.categ_id:
                        categ_name = line.product_id.categ_id.name.lower()
                        material_type = 'other'
                        if 'cement' in categ_name:
                            material_type = 'cement'
                        elif 'sand' in categ_name:
                            material_type = 'sand'
                        elif 'aggregate' in categ_name or 'gravel' in categ_name:
                            material_type = 'aggregate'
                        
                        if material_type == record.material_type:
                            # If customer provides cement, don't add to balance
                            if not (material_type == 'cement' and so.customer_provides_cement):
                                total_balance += line.product_uom_qty
            
            # Calculate from workorders (materials used)
            workorders = self.env['dropshipping.workorder'].search([('partner_id', '=', record.partner_id.id)])
            for wo in workorders:
                for line in wo.workorder_line_ids:
                    if line.product_id and line.product_id.categ_id:
                        categ_name = line.product_id.categ_id.name.lower()
                        material_type = 'other'
                        if 'cement' in categ_name:
                            material_type = 'cement'
                        elif 'sand' in categ_name:
                            material_type = 'sand'
                        elif 'aggregate' in categ_name or 'gravel' in categ_name:
                            material_type = 'aggregate'
                        
                        if material_type == record.material_type:
                            total_balance -= line.quantity_ordered
            
            record.balance_qty = total_balance
            record.last_updated = fields.Datetime.now()

    @api.model
    def _update_balance(self, partner, material_type, qty_change):
        balance = self.search([('partner_id', '=', partner.id), ('material_type', '=', material_type)], limit=1)
        if balance:
            balance.balance_qty += qty_change
            balance.last_updated = fields.Datetime.now()
        else:
            self.create({'partner_id': partner.id, 'material_type': material_type, 'balance_qty': qty_change})
        return True

    def action_test_multiple_updates(self):
        self.env['rmc.material.balance']._update_balance(self.partner_id, 'cement', 300)
        self.env['rmc.material.balance']._update_balance(self.partner_id, 'cement', -150)
        self.env['rmc.material.balance']._update_balance(self.env['res.partner'].search([('name', '=', 'New Partner')], limit=1), 'cement', 100)