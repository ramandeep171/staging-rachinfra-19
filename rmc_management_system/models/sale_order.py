from odoo import _, models, fields, api
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # RMC Specific Fields
    is_rmc_order = fields.Boolean(string='RMC Order', compute='_compute_is_rmc_order', store=True)
    customer_provides_cement = fields.Boolean(string='Customer Provides Cement', help='Check if the customer will provide cement for this order')
    delivery_coordinates = fields.Char(string='Delivery Coordinates', related='partner_id.delivery_coordinates')
    delivery_address = fields.Char(string='Delivery Address', compute='_compute_delivery_address')
    required_slump = fields.Float(string='Required Slump/Flow (mm)')
    pour_structure = fields.Selection([
        ('rcc', 'RCC'),
        ('pcc', 'PCC'),
        ('foundation', 'Foundation'),
        ('slab', 'Slab'),
        ('beam', 'Beam'),
        ('column', 'Column'),
    ], string='Pour Structure')
    
    # Relations
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='RMC Ticket')
    workorder_ids = fields.One2many('dropshipping.workorder', 'sale_order_id', string='RMC Workorders')
    batch_ids = fields.One2many('rmc.batch', 'sale_order_id', string='Batches')
    # Removed Quality Checks and Weighbridge relations from this module
    
    # Counters
    workorder_count = fields.Integer(string='Workorder Count', compute='_compute_workorder_count', store=True)
    batch_count = fields.Integer(string='Batch Count', compute='_compute_counts')
    quality_check_count = fields.Integer(string='Quality Check Count', compute='_compute_counts')
    is_rmc_product = fields.Boolean(string='Is RMC Product', compute='_compute_is_rmc_product', store=True)
    
    @api.depends('batch_ids')
    def _compute_counts(self):
        for record in self:
            record.batch_count = len(record.batch_ids)
            record.quality_check_count = 0

    @api.depends('workorder_ids')
    def _compute_workorder_count(self):
        for order in self:
            order.workorder_count = len(order.workorder_ids)

    @api.depends('order_line.product_id.categ_id.name')
    def _compute_is_rmc_order(self):
        for order in self:
            is_rmc = False
            for line in order.order_line:
                if line.product_id and line.product_id.categ_id:
                    # Check if product category contains 'RMC' or is RMC related
                    category_name = line.product_id.categ_id.name or ''
                    if 'RMC' in category_name.upper() or 'CONCRETE' in category_name.upper():
                        is_rmc = True
                        break
            order.is_rmc_order = is_rmc

    @api.depends('order_line.product_id.categ_id.name')
    def _compute_is_rmc_product(self):
        """True when any order line product has category exactly 'RMC' (case-insensitive)."""
        for order in self:
            is_rmc = False
            for line in order.order_line:
                product = line.product_id
                if not product or not product.categ_id:
                    continue
                cat_name = (product.categ_id.name or '').strip().lower()
                if cat_name == 'rmc':
                    is_rmc = True
                    break
            order.is_rmc_product = is_rmc

    def action_confirm(self):
        # Ensure cube test condition exists for RMC orders; auto-fill default if missing
        for order in self:
            if order.is_rmc_order and not order.cube_test_condition:
                order.cube_test_condition = 'workorder'

        result = super(SaleOrder, self).action_confirm()

        # Create helpdesk ticket for RMC orders
        if any(line.product_id.categ_id.name == 'RMC' for line in self.order_line):
            self._create_rmc_ticket()

    # Cube tests are created by triggers (workorder/docket) only

        return result

    def action_create_rmc_workorder(self):
        """Manually create RMC workorder from sale order"""
        self.ensure_one()
        if not self.is_rmc_order:
            raise ValidationError(_("This is not an RMC order. Cannot create RMC workorder."))
        
        return self._create_rmc_workorder()

    def action_view_workorders(self):
        """View related workorders"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'RMC Workorders',
            'res_model': 'dropshipping.workorder',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

    def _create_rmc_workorder(self):
        """Internal method to create RMC workorder"""
        self.ensure_one()
        
        # Get RMC products from order lines
        rmc_lines = self.order_line.filtered(
            lambda line: line.product_id and line.product_id.categ_id and 
            ('RMC' in (line.product_id.categ_id.name or '').upper() or 
             'CONCRETE' in (line.product_id.categ_id.name or '').upper())
        )
        
        if not rmc_lines:
            return False
            
        # Calculate total quantity
        total_qty = sum(rmc_lines.mapped('product_uom_qty'))
        
        # Get main product (first RMC product)
        main_product = rmc_lines[0].product_id
        
        # Create workorder
        workorder_vals = {
            'sale_order_id': self.id,
            'product_id': main_product.id,
            'quantity_ordered': total_qty,
            'total_qty': total_qty,
            'unit_price': rmc_lines[0].price_unit,
            'site_type': 'friendly',  # Default, can be changed later
            'state': 'draft',
            'notes': f'Auto-created from Sale Order {self.name}',
        }
        
        # Create workorder lines
        workorder_lines = []
        for line in rmc_lines:
            workorder_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'quantity_ordered': line.product_uom_qty,
                'unit_price': line.price_unit,
            }))
        
        workorder_vals['workorder_line_ids'] = workorder_lines
        
        # Create the workorder
        workorder = self.env['dropshipping.workorder'].create(workorder_vals)
        
        # Create helpdesk ticket if needed
        if workorder:
            self._create_helpdesk_ticket_for_workorder(workorder)
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'RMC Workorder Created',
            'res_model': 'dropshipping.workorder',
            'res_id': workorder.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_helpdesk_ticket_for_workorder(self, workorder):
        """Create helpdesk ticket for the workorder"""
        helpdesk_vals = {
            'name': f'RMC Workorder: {workorder.name}',
            'description': f'Workorder created for Sale Order {self.name}\nQuantity: {workorder.total_qty} M3\nProduct: {workorder.product_id.name}',
            'partner_id': self.partner_id.id,
            'team_id': self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping').id if self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping', raise_if_not_found=False) else False,
            'priority': '2',  # High priority
        }
        
        ticket = self.env['helpdesk.ticket'].create(helpdesk_vals)
        workorder.helpdesk_ticket_id = ticket.id
        
        return ticket

    @api.model_create_multi
    def create(self, vals_list):
        """Standard create; no auto Workorder. Balances still update."""
        orders = super(SaleOrder, self).create(vals_list)
        for order in orders:
            order._update_material_balances()
        return orders

    def write(self, vals):
        result = super(SaleOrder, self).write(vals)
        # Update material balances if order lines changed
        if 'order_line' in vals:
            for order in self:
                order._update_material_balances()
        return result

    def _update_material_balances(self):
        """Update material balances based on sale order lines"""
        for order in self:
            if order.partner_id:
                for line in order.order_line:
                    if line.product_id and line.product_id.categ_id:
                        categ_name = line.product_id.categ_id.name.lower()
                        material_type = 'other'
                        if 'cement' in categ_name:
                            material_type = 'cement'
                        elif 'sand' in categ_name:
                            material_type = 'sand'
                        elif 'aggregate' in categ_name or 'gravel' in categ_name:
                            material_type = 'aggregate'
                        
                        # Add materials received from sale order (unless customer provides cement)
                        if not (material_type == 'cement' and order.customer_provides_cement):
                            self.env['rmc.material.balance']._update_balance(
                                order.partner_id, material_type, line.product_uom_qty)

    def _create_rmc_ticket(self):
        """Create helpdesk ticket for RMC order"""
        ticket_vals = {
            'name': _('RMC Order: %s') % self.name,
            'description': _('RMC order processing for %s') % self.partner_id.name,
            'partner_id': self.partner_id.id,
            'sale_order_id': self.id,
            'stage_id': self.env.ref('helpdesk.stage_new').id,
        }
        ticket = self.env['helpdesk.ticket'].create(ticket_vals)
        self.helpdesk_ticket_id = ticket.id