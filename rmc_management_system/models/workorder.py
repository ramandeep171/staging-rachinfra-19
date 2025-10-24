from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta
import base64

class DropshippingWorkorder(models.Model):
    _name = 'dropshipping.workorder'
    _description = 'Dropshipping RMC Workorder'
    _order = 'date_order desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Workorder Number', required=True, copy=False, readonly=True, default='New')
    date_order = fields.Datetime(string='Order Date', required=True, default=fields.Datetime.now)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='sale_order_id.partner_id', store=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    quantity_ordered = fields.Float(string='Quantity Ordered')
    # Delivered should reflect all dockets' Quantity Produced for this workorder
    quantity_delivered = fields.Float(string='Quantity Delivered', compute='_compute_delivered_and_remaining', store=False)
    quantity_remaining = fields.Float(string='Quantity Remaining', compute='_compute_delivered_and_remaining', store=False)
    total_qty = fields.Float(string='Total Qty')
    site_type = fields.Selection([('friendly', 'Friendly'), ('unfriendly', 'Unfriendly')], string='Site Type')
    unit_price = fields.Float(string='Unit Price')
    total_amount = fields.Float(string='Total Amount', compute='_compute_total', store=True)
    delivery_date = fields.Datetime(string='Delivery Date')
    delivery_location = fields.Char(string='Delivery Location')
    delivery_coordinates = fields.Char(string='Delivery Coordinates')
    notes = fields.Text(string='Notes')
    subcontractor_id = fields.Many2one('res.partner', string='Subcontractor')
    # Allowed subcontractor partners (partners that have an entry in rmc.subcontractor)
    allowed_subcontractor_partner_ids = fields.Many2many(
        'res.partner', string='Allowed Subcontractors', compute='_compute_allowed_subcontractors', store=False)
    # Mapped RMC subcontractor record for the selected partner (used for domaining plants)
    rmc_subcontractor_id = fields.Many2one('rmc.subcontractor', string='RMC Subcontractor', compute='_compute_rmc_subcontractor', store=False)
    # Selected plant of the chosen RMC subcontractor
    subcontractor_plant_id = fields.Many2one('rmc.subcontractor.plant', string='Plant')
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Main Helpdesk Ticket')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('assigned_to_subcontractor', 'Assigned to Subcontractor'),
        ('pending_acceptance', 'Pending Acceptance'),
        ('accepted', 'Accepted'),
        ('in_progress', 'In Progress'),
        ('breakdown', 'Breakdown'),
        ('diverted', 'Diverted'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    # Reporting & notifications
    date_completed = fields.Datetime(string='Completed On', tracking=True)
    wo_report_root_message_id = fields.Many2one('mail.message', string='WO Report Root Message', readonly=True)
    cube7_last_sent = fields.Datetime(string='Cube 7-Day Sent On', readonly=True)
    cube28_last_sent = fields.Datetime(string='Cube 28-Day Sent On', readonly=True)
    report_cc_emails = fields.Char(string='Report CC Emails')
    report_bcc_emails = fields.Char(string='Report BCC Emails')
    completion_template_id = fields.Many2one('mail.template', string='Completion Email Template')
    cube7_template_id = fields.Many2one('mail.template', string='Cube 7-Day Email Template')
    cube28_template_id = fields.Many2one('mail.template', string='Cube 28-Day Email Template')
    workorder_line_ids = fields.One2many('dropshipping.workorder.line', 'workorder_id', string='Workorder Lines')
    ingredient_balance_ids = fields.One2many('dropshipping.ingredient.balance', 'workorder_id', string='Ingredient Balances')
    ticket_ids = fields.One2many('dropshipping.workorder.ticket', 'workorder_id', string='Tickets')
    # Convenience: list the actual Helpdesk tickets linked via workorder tickets
    helpdesk_ticket_ids = fields.Many2many(
        'helpdesk.ticket', string='Helpdesk Tickets', compute='_compute_helpdesk_tickets', store=False)
    warehouse_shift_ids = fields.One2many('dropshipping.warehouse.shift', 'workorder_id', string='Warehouse Shifts')
    cement_balance = fields.Float(string='Cement Balance (Kg)', compute='_compute_cement_balance', store=True)
    inventory_status = fields.Char(string='Inventory Status', compute='_compute_inventory_status', store=True)
    suggested_subcontractor_id = fields.Many2one('res.partner', string='Suggested Subcontractor')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Recipe selection at Workorder level; will propagate to dockets
    recipe_id = fields.Many2one('mrp.bom', string='Recipe')

    # Delivered-to-date for this SO (excluding current workorder)
    so_delivered_to_date = fields.Float(string='SO Delivered To Date', compute='_compute_so_delivered_to_date', store=False)

    # Pump selection
    pump_required = fields.Boolean(string='Pump Required?')
    pump_provider_id = fields.Many2one('rmc.subcontractor', string='Pump Provider')
    pump_id = fields.Many2one('rmc.subcontractor.pump', string='Selected Pump')

    # Delivery Variances smart button
    delivery_variance_count = fields.Integer(string='Delivery Variances', compute='_compute_counts', store=False)

    # Smart button counters
    docket_count = fields.Integer(string='Dockets', compute='_compute_counts', store=False)
    ticket_count_btn = fields.Integer(string='Tickets', compute='_compute_counts', store=False)
    truck_loading_count = fields.Integer(string='Truck Loadings', compute='_compute_counts', store=False)
    batch_count_btn = fields.Integer(string='Batches', compute='_compute_counts', store=False)
    po_count = fields.Integer(string='Purchase Orders', compute='_compute_counts', store=False)
    vendor_bill_count = fields.Integer(string='Vendor Bills', compute='_compute_counts', store=False)
    invoice_count = fields.Integer(string='Invoices', compute='_compute_counts', store=False)

    @api.model
    def _get_subcontractor_domain(self):
        rmc_subcontractor_partners = self.env['rmc.subcontractor'].search([]).mapped('partner_id').ids
        return [('id', 'not in', rmc_subcontractor_partners)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dropshipping.workorder') or 'WO/0000'
        records = super(DropshippingWorkorder, self).create(vals_list)
        # Server-side defaults: if subcontractor set at creation time, default pump provider and top plant
        for record in records:
            record._assign_defaults_from_subcontractor()
        for record in records:
            self._generate_tickets(record)
            # Update material balances for workorder creation
            record._update_material_balances()
            # Create cube tests when trigger is workorder-wise
            so = record.sale_order_id
            if so and so.is_rmc_order and so.cube_test_condition == 'workorder':
                qc_model = self.env['quality.cube.test']
                # duplicate guard: if any non-retest tests exist for this workorder, skip
                existing = qc_model.search([
                    ('sale_order_id', '=', so.id),
                    ('workorder_id', '=', record.id),
                    ('retest_of_id', '=', False),
                ], limit=1)
                if not existing:
                    today = fields.Date.context_today(self)
                    common = {
                        'sale_order_id': so.id,
                        'test_condition': 'workorder',
                        'cubes_per_test': 3,
                        'user_id': so.cube_test_user_id.id,
                        'notes': so.cube_test_notes,
                        'workorder_id': record.id,
                    }
                    qc_model.create(dict(common, casting_date=today, day_type='7'))
                    qc_model.create(dict(common, casting_date=today, day_type='28'))
        return records

    

    def _assign_defaults_from_subcontractor(self):
        """When a subcontractor partner is chosen, default pump provider to mapped RMC subcontractor
        and default plant to the first available plant. Safe to call anytime; skips if already set.
        """
        for rec in self:
            if not rec.subcontractor_id:
                continue
            # If already set, don't override
            if rec.pump_provider_id and rec.subcontractor_plant_id:
                continue
            rmc_sub = self.env['rmc.subcontractor'].search([('partner_id', '=', rec.subcontractor_id.id)], limit=1)
            if not rmc_sub:
                # Best effort: create a minimal mapping so domains work
                try:
                    rmc_sub = self.env['rmc.subcontractor'].create({
                        'name': rec.subcontractor_id.name or 'Subcontractor',
                        'partner_id': rec.subcontractor_id.id,
                    })
                except Exception:
                    rmc_sub = self.env['rmc.subcontractor']
            if rmc_sub:
                if not rec.pump_provider_id:
                    rec.pump_provider_id = rmc_sub.id
                if not rec.subcontractor_plant_id:
                    top_plant = rmc_sub.plant_ids[:1]
                    rec.subcontractor_plant_id = top_plant.id if top_plant else False

    def _sync_state_from_tickets(self):
        """Keep workorder.state in sync with its tickets:
        - If any ticket is in_progress/assigned/draft => state=in_progress.
        - If all tickets are completed (or cancelled) and at least one exists => state=completed.
        - If no tickets, keep current state.

        DISABLED: This auto-sync is disabled to maintain manual state control via buttons.
        """
        # Commenting out auto-sync logic to prevent automatic state changes
        # for wo in self:
        #     tickets = wo.ticket_ids
        #     if not tickets:
        #         continue
        #     states = set(tickets.mapped('state'))
        #     if any(s in {'in_progress', 'assigned', 'draft'} for s in states):
        #         if wo.state != 'in_progress':
        #             wo.state = 'in_progress'
        #     elif all(s in {'completed', 'cancelled'} for s in states):
        #         if wo.state != 'completed':
        #             wo.state = 'completed'
        pass

    @api.model
    def _generate_tickets(self, workorder):
        # Generate based on Quantity Delivered if provided, else fallback to Total Qty
        total_qty = workorder.quantity_delivered or workorder.total_qty
        ticket_size = 6 if workorder.site_type == 'unfriendly' else 7
        num_tickets = int(total_qty // ticket_size)
        last_qty = total_qty % ticket_size
        if last_qty > 0:
            num_tickets += 1
        tickets_created = []
        rmc_team = self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping', raise_if_not_found=False)
        for i in range(num_tickets):
            qty = ticket_size if i < num_tickets - 1 else (last_qty or ticket_size)
            ticket_vals = {
                'name': f'Ticket {i+1} for WO {workorder.name}',
                'description': f'Auto-generated ticket for Workorder {workorder.name}\nQuantity: {qty} M3\nSite Type: {workorder.site_type}\nCustomer: {workorder.partner_id.name}\nSale Order: {workorder.sale_order_id.name}',
                'partner_id': workorder.partner_id.id,
                'team_id': rmc_team.id if rmc_team else False,
                'priority': '2',
                'sale_order_id': workorder.sale_order_id.id,
                'rmc_quantity': qty,
            }
            ticket = self.env['helpdesk.ticket'].create(ticket_vals)
            tickets_created.append(ticket.id)
            workorder_ticket_vals = {
                'workorder_id': workorder.id,
                'name': f'Ticket {i+1}',
                'quantity': qty,
                'helpdesk_ticket_id': ticket.id,
                'state': 'draft',
                'delivery_location': workorder.delivery_location,
                'delivery_coordinates': workorder.delivery_coordinates,
                'notes': f'Auto-generated for quantity {qty} M3',
            }
            self.env['dropshipping.workorder.ticket'].create(workorder_ticket_vals)
            # Update RMC material balance for cement
            if workorder.partner_id:
                self.env['rmc.material.balance']._update_balance(workorder.partner_id, 'cement', -qty * 0.05)
        if tickets_created:
            workorder.helpdesk_ticket_id = tickets_created[0]
        return tickets_created

    def _compute_so_delivered_to_date(self):
        for wo in self:
            total = 0.0
            if wo.sale_order_id:
                others = self.search([('sale_order_id', '=', wo.sale_order_id.id), ('id', '!=', wo.id)])
                total = sum(others.mapped('quantity_delivered'))
            wo.so_delivered_to_date = total

    @api.depends('quantity_ordered')
    def _compute_delivered_and_remaining(self):
        for record in self:
            # Sum of Quantity Produced across linked dockets
            dockets = self.env['rmc.docket'].search([('workorder_id', '=', record.id)])
            delivered = sum(float(d.quantity_produced or 0.0) for d in dockets)
            record.quantity_delivered = delivered
            record.quantity_remaining = float(record.quantity_ordered or 0.0) - delivered

    @api.depends('quantity_ordered', 'unit_price')
    def _compute_total(self):
        for record in self:
            record.total_amount = record.quantity_ordered * record.unit_price

    @api.depends('partner_id')
    def _compute_cement_balance(self):
        for record in self:
            cement_balance = 0.0
            if record.partner_id:
                # Get cement balance from RMC material balances
                cement_balance_record = self.env['rmc.material.balance'].search([
                    ('partner_id', '=', record.partner_id.id),
                    ('material_type', '=', 'cement')
                ], limit=1)
                if cement_balance_record:
                    cement_balance = cement_balance_record.balance_qty
            record.cement_balance = cement_balance

    @api.depends('warehouse_shift_ids.shift_date')
    def _compute_inventory_status(self):
        for record in self:
            latest_shift = record.warehouse_shift_ids.sorted('shift_date', reverse=True)[:1]
            if latest_shift:
                record.inventory_status = f"Shifted to {latest_shift.to_location_id.name} on {latest_shift.shift_date}"
            else:
                record.inventory_status = "No shifts"

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        if self.sale_order_id:
            self.partner_id = self.sale_order_id.partner_id
            lines = []
            for line in self.sale_order_id.order_line:
                if line.product_id.type == 'product':
                    lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'quantity_ordered': line.product_uom_qty,
                        'unit_price': line.price_unit,
                    }))
            self.workorder_line_ids = lines
            if self.sale_order_id.order_line:
                first_line = self.sale_order_id.order_line[0]
                self.product_id = first_line.product_id
                self.quantity_ordered = first_line.product_uom_qty
                self.unit_price = first_line.price_unit
                self.total_qty = first_line.product_uom_qty

    def action_regenerate_tickets(self):
        for record in self:
            record.ticket_ids.unlink()
            self._generate_tickets(record)
        return True

    def _compute_counts(self):
        for wo in self:
            # Dockets linked to this workorder
            dockets = self.env['rmc.docket'].search([('workorder_id', '=', wo.id)])
            wo.docket_count = len(dockets)
            # Tickets
            wo.ticket_count_btn = len(wo.ticket_ids)
            # Truck loadings via dockets
            wo.truck_loading_count = self.env['rmc.truck_loading'].search_count([('docket_id', 'in', dockets.ids)])
            # Docket batches via dockets
            wo.batch_count_btn = self.env['rmc.docket.batch'].search_count([('docket_id', 'in', dockets.ids)])
            # Purchase Orders by origin
            wo.po_count = self.env['purchase.order'].search_count([('origin', '=', wo.name)])
            # Vendor Bills linked by invoice_origin
            wo.vendor_bill_count = self.env['account.move'].search_count([('move_type', '=', 'in_invoice'), ('invoice_origin', 'ilike', wo.name or '')])
            # Customer invoices via docket link
            wo.invoice_count = self.env['account.move'].search_count([('move_type', '=', 'out_invoice'), ('docket_id', 'in', dockets.ids)])
            # Delivery variances via truck loadings under these dockets
            tl_ids = self.env['rmc.truck_loading'].search([('docket_id', 'in', dockets.ids)]).ids
            wo.delivery_variance_count = self.env['rmc.delivery_variance'].search_count([('truck_loading_id', 'in', tl_ids)])

    def _compute_helpdesk_tickets(self):
        for wo in self:
            wo.helpdesk_ticket_ids = [(6, 0, wo.ticket_ids.mapped('helpdesk_ticket_id').ids)]

    # Smart button actions
    def action_open_dockets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Dockets',
            'res_model': 'rmc.docket',
            'view_mode': 'list,form',
            'domain': [('workorder_id', '=', self.id)],
            'context': {'default_workorder_id': self.id, 'default_sale_order_id': self.sale_order_id.id},
        }

    def action_open_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tickets',
            'res_model': 'helpdesk.ticket',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.ticket_ids.mapped('helpdesk_ticket_id').ids)],
        }

    def action_open_truck_loadings(self):
        self.ensure_one()
        docket_ids = self.env['rmc.docket'].search([('workorder_id', '=', self.id)]).ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Truck Loadings',
            'res_model': 'rmc.truck_loading',
            'view_mode': 'list,form',
            'domain': [('docket_id', 'in', docket_ids)],
        }

    def action_open_batches(self):
        self.ensure_one()
        docket_ids = self.env['rmc.docket'].search([('workorder_id', '=', self.id)]).ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Docket Batches',
            'res_model': 'rmc.docket.batch',
            'view_mode': 'list,form',
            'domain': [('docket_id', 'in', docket_ids)],
        }

    def action_open_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('origin', '=', self.name)],
            'context': {'search_default_purchase_permits': 1},
        }

    def action_open_vendor_bills(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bills',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('move_type', '=', 'in_invoice'), ('invoice_origin', 'ilike', self.name or '')],
            'context': {'default_move_type': 'in_invoice'},
        }

    def action_open_invoices(self):
        self.ensure_one()
        docket_ids = self.env['rmc.docket'].search([('workorder_id', '=', self.id)]).ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Customer Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('move_type', '=', 'out_invoice'), ('docket_id', 'in', docket_ids)],
            'context': {'default_move_type': 'out_invoice'},
        }

    def action_simulate_breakdown(self):
        self.state = 'breakdown'
        self._suggest_subcontractor()

    def action_send_for_acceptance(self):
        """Move WO from assigned_to_subcontractor to pending_acceptance."""
        for record in self:
            if record.state == 'assigned_to_subcontractor':
                record.state = 'pending_acceptance'
                record.message_post(
                    body=_('Work Order sent to subcontractor for acceptance.'),
                    subject=_('Pending Acceptance')
                )

    def action_accept_wo(self):
        """Subcontractor accepts the WO - moves to accepted state."""
        for record in self:
            if record.state == 'pending_acceptance':
                record.state = 'accepted'
                record.message_post(
                    body=_('Work Order accepted by subcontractor %s.') % (record.subcontractor_id.name or 'N/A'),
                    subject=_('Work Order Accepted')
                )

    def action_reject_wo(self):
        """Subcontractor rejects the WO - moves back to draft for reassignment."""
        for record in self:
            if record.state == 'pending_acceptance':
                record.state = 'draft'
                record.message_post(
                    body=_('Work Order rejected by subcontractor. Back to Draft.'),
                    subject=_('Work Order Rejected')
                )

    def action_start_progress(self):
        """Move from accepted to in_progress."""
        for record in self:
            if record.state == 'accepted':
                record.state = 'in_progress'
                record.message_post(
                    body=_('Work Order moved to In Progress.'),
                    subject=_('In Progress')
                )

    def action_resync_state(self):
        """Resync workorder ticket states based on linked helpdesk ticket stages,
        then recompute the workorder state accordingly.
        """
        for wo in self:
            for wot in wo.ticket_ids:
                hd = wot.helpdesk_ticket_id
                if not hd or not hd.stage_id:
                    continue
                stage_name = (hd.stage_id.name or '').lower()
                new_state = None
                if any(w in stage_name for w in ['solved', 'done', 'closed', 'complete']):
                    new_state = 'completed'
                elif 'cancel' in stage_name:
                    new_state = 'cancelled'
                elif 'progress' in stage_name:
                    new_state = 'in_progress'
                elif 'assign' in stage_name:
                    new_state = 'assigned'
                if new_state and wot.state != new_state:
                    wot.write({'state': new_state})
            wo._sync_state_from_tickets()
        return True

    def _suggest_subcontractor(self):
        if not self.suggested_subcontractor_id:
            subcontractors = self.env['res.partner'].search([('is_company', '=', True)], limit=1)
            if subcontractors:
                self.suggested_subcontractor_id = subcontractors[0]

    def _create_rfq_for_subcontractor(self):
        """Create RFQ (Purchase Order in draft) for the assigned subcontractor.
        RFQ will reference the Work Order, not the Sale Order.
        """
        self.ensure_one()
        if not self.subcontractor_id:
            return False

        # Check if RFQ already exists for this WO
        existing_po = self.env['purchase.order'].search([
            ('origin', '=', self.name),
            ('partner_id', '=', self.subcontractor_id.id),
            ('state', '=', 'draft')
        ], limit=1)

        if existing_po:
            # RFQ already exists
            return existing_po

        # Prepare PO lines from workorder lines or main product
        po_lines = []
        if self.workorder_line_ids:
            for line in self.workorder_line_ids:
                if line.product_id:
                    # Get UOM - try uom_po_id first, fallback to uom_id
                    uom = line.product_id.uom_po_id if hasattr(line.product_id, 'uom_po_id') and line.product_id.uom_po_id else line.product_id.uom_id
                    po_lines.append((0, 0, {
                        'product_id': line.product_id.id,
                        'name': line.product_id.name or 'RMC Product',
                        'product_qty': line.quantity_ordered,
                        'product_uom_id': uom.id if uom else False,
                        'price_unit': line.unit_price or 0.0,
                        'date_planned': self.delivery_date or fields.Datetime.now(),
                    }))
        elif self.product_id:
            # Fallback to main product if no lines
            # Get UOM - try uom_po_id first, fallback to uom_id
            uom = self.product_id.uom_po_id if hasattr(self.product_id, 'uom_po_id') and self.product_id.uom_po_id else self.product_id.uom_id
            po_lines.append((0, 0, {
                'product_id': self.product_id.id,
                'name': self.product_id.name or 'RMC Product',
                'product_qty': self.quantity_ordered or self.total_qty,
                'product_uom_id': uom.id if uom else False,
                'price_unit': self.unit_price or 0.0,
                'date_planned': self.delivery_date or fields.Datetime.now(),
            }))

        if not po_lines:
            # No products to order
            return False

        # Create RFQ with WO reference
        po_vals = {
            'partner_id': self.subcontractor_id.id,
            'origin': self.name,  # WO reference, not SO
            'date_order': fields.Datetime.now(),
            'order_line': po_lines,
        }

        po = self.env['purchase.order'].create(po_vals)

        # Post message on WO
        self.message_post(
            body=_('RFQ %s created automatically for subcontractor %s') % (po.name, self.subcontractor_id.name),
            subject=_('RFQ Created')
        )

        return po

    @api.depends()
    def _compute_allowed_subcontractors(self):
        """Restrict selectable subcontractors to partners present in rmc.subcontractor.
        If none exist yet, fall back to vendor partners so the user can bootstrap
        by selecting a vendor (we will auto-create rmc.subcontractor on change).
        """
        sub_partners = self.env['rmc.subcontractor'].search([]).mapped('partner_id').ids
        if not sub_partners:
            # Bootstrap: allow vendor partners when no rmc.subcontractor defined yet
            sub_partners = self.env['res.partner'].search([('supplier_rank', '>', 0)]).ids
        for rec in self:
            rec.allowed_subcontractor_partner_ids = [(6, 0, sub_partners)]

    @api.depends('subcontractor_id')
    def _compute_rmc_subcontractor(self):
        for rec in self:
            rmc_sub = False
            if rec.subcontractor_id:
                rmc_sub = self.env['rmc.subcontractor'].search([('partner_id', '=', rec.subcontractor_id.id)], limit=1)
            rec.rmc_subcontractor_id = rmc_sub.id if rmc_sub else False

    def action_divert_create_po(self):
        if not self.suggested_subcontractor_id:
            return
        po = self.env['purchase.order'].create({
            'partner_id': self.suggested_subcontractor_id.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.total_qty,
                'price_unit': 0.0,
            })],
        })
        self.state = 'diverted'
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_shift_to_customer_warehouse(self):
        for record in self:
            if not record.product_id or not record.quantity_ordered:
                continue
            from_loc = self.env.ref('stock.stock_location_stock', raise_if_not_found=False)
            if not from_loc:
                warehouse = self.env['stock.warehouse'].search([], limit=1)
                from_loc = warehouse.lot_stock_id if warehouse else None
            if not from_loc:
                raise ValueError("No stock location found. Please configure a warehouse.")
            parent_location = self.env['stock.move']._get_default_parent_location(record.company_id or self.env.company)
            customer_loc = self.env['stock.location'].create({
                'name': f'{record.partner_id.name} Warehouse',
                'usage': 'internal',
                'location_id': parent_location.id,
                'company_id': (record.company_id or self.env.company).id,
            })
            shift = self.env['dropshipping.warehouse.shift'].create({
                'workorder_id': record.id,
                'product_id': record.product_id.id,
                'quantity_shifted': record.quantity_ordered,
                'from_location_id': from_loc.id,
                'to_location_id': customer_loc.id,
            })
            move = self.env['stock.move'].create({
                'name': f'Shift {record.product_id.name} to {customer_loc.name}',
                'product_id': record.product_id.id,
                'product_uom_qty': record.quantity_ordered,
                'product_uom': record.product_id.uom_id.id,
                'location_id': from_loc.id,
                'location_dest_id': customer_loc.id,
                'state': 'draft',
            })
            move._action_confirm()
            move._action_assign()
            move._action_done()
            self.env['stock.quant']._update_available_quantity(record.product_id, from_loc, -record.quantity_ordered)
            self.env['stock.quant']._update_available_quantity(record.product_id, customer_loc, record.quantity_ordered)
        return True

    # Smart button: Delivery Variances
    def action_open_delivery_variances(self):
        self.ensure_one()
        docket_ids = self.env['rmc.docket'].search([('workorder_id', '=', self.id)]).ids
        tl_ids = self.env['rmc.truck_loading'].search([('docket_id', 'in', docket_ids)]).ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Delivery Variances',
            'res_model': 'rmc.delivery_variance',
            'view_mode': 'list,form',
            'domain': [('truck_loading_id', 'in', tl_ids)],
        }

    @api.onchange('subcontractor_plant_id')
    def _onchange_subcontractor_plant_confirm(self):
        """Plant selection no longer auto-confirms the workorder."""
        # State transitions are now handled manually via buttons
        pass

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_for_pump(self):
        """Default pump provider and plant to mapped RMC Subcontractor for selected partner if available."""
        for rec in self:
            if rec.subcontractor_id:
                rmc_sub = self.env['rmc.subcontractor'].search([('partner_id', '=', rec.subcontractor_id.id)], limit=1)
                if not rmc_sub:
                    # Auto-create a minimal rmc.subcontractor to keep the workflow going
                    try:
                        rmc_sub = self.env['rmc.subcontractor'].create({
                            'name': rec.subcontractor_id.name or 'Subcontractor',
                            'partner_id': rec.subcontractor_id.id,
                        })
                    except Exception:
                        rmc_sub = self.env['rmc.subcontractor']
                if rmc_sub:
                    rec.pump_provider_id = rmc_sub.id
                    # Default plant as top (ordered) plant if any
                    top_plant = rmc_sub.plant_ids[:1]
                    rec.subcontractor_plant_id = top_plant.id if top_plant else False
                    return {'domain': {'subcontractor_plant_id': [('subcontractor_id', '=', rmc_sub.id)]}}
                else:
                    rec.subcontractor_plant_id = False
                    return {'domain': {'subcontractor_plant_id': []}}
            else:
                rec.pump_provider_id = False
                rec.subcontractor_plant_id = False
                return {'domain': {'subcontractor_plant_id': []}}

    @api.onchange('pump_provider_id')
    def _onchange_pump_provider_set_domain(self):
        for rec in self:
            if rec.pump_provider_id:
                return {'domain': {'pump_id': [('subcontractor_id', '=', rec.pump_provider_id.id)]}}
            else:
                return {'domain': {'pump_id': []}}

    def _ensure_pump_ticket(self):
        """Create a pump ticket when pump is required and selected, if not already present."""
        for rec in self:
            if not (rec.pump_required and rec.pump_id):
                continue
            # Check if a pump ticket already exists
            existing = rec.ticket_ids.filtered(lambda t: getattr(t, 'is_pump', False))
            if existing:
                # Update pump reference if changed
                existing.write({'pump_id': rec.pump_id.id})
                continue
            # Create Helpdesk ticket and Workorder ticket for pump
            rmc_team = self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping', raise_if_not_found=False)
            hd = self.env['helpdesk.ticket'].create({
                'name': f'Pump for {rec.name}',
                'description': f'Pump requirement for Workorder {rec.name}\nProvider: {rec.pump_provider_id.name or "-"}\nPump: {rec.pump_id.pump_code or rec.pump_id.id}',
                'partner_id': rec.partner_id.id,
                'team_id': rmc_team.id if rmc_team else False,
                'priority': '2',
                'sale_order_id': rec.sale_order_id.id,
            })
            self.env['dropshipping.workorder.ticket'].create({
                'workorder_id': rec.id,
                'name': f'Pump Ticket for {rec.name}',
                'quantity': 0.0,
                'helpdesk_ticket_id': hd.id,
                'state': 'assigned',
                'delivery_location': rec.delivery_location,
                'delivery_coordinates': rec.delivery_coordinates,
                'notes': 'Auto-generated pump ticket',
                'is_pump': True,
                'pump_id': rec.pump_id.id,
            })
        return True

    def write(self, vals):
        # Perform write
        res = super(DropshippingWorkorder, self).write(vals)
        # Regenerate tickets if total parameters changed (merge logic from earlier write)
        if any(field in vals for field in ['total_qty', 'site_type']):
            for record in self:
                record.ticket_ids.unlink()
                self._generate_tickets(record)
        # Update material balances if quantities changed
        if 'workorder_line_ids' in vals or 'quantity_ordered' in vals:
            for record in self:
                record._update_material_balances()
        # Special case: if marking completed and every_six not yet hit 6 dockets, create tests on last docket
        if vals.get('state') == 'completed':
            for record in self:
                so = record.sale_order_id
                if not (so and so.is_rmc_order and so.cube_test_condition == 'every_six'):
                    continue
                dockets = self.env['rmc.docket'].search([('workorder_id', '=', record.id)], order='docket_date asc,id asc')
                if not dockets:
                    continue
                if len(dockets) < 6:
                    last = dockets[-1]
                    existing = self.env['quality.cube.test'].search_count([
                        ('workorder_id', '=', record.id),
                        ('docket_id', '=', last.id),
                        ('retest_of_id', '=', False),
                    ])
                    if not existing:
                        last._trigger_cube_tests_for_docket('every_six')
        # When marking a WO completed, stamp date and send completion report email
        if vals.get('state') == 'completed':
            for record in self:
                if not record.date_completed:
                    record.date_completed = fields.Datetime.now()
                try:
                    record._send_workorder_completion_email()
                except Exception as e:
                    record.message_post(body=_('Failed to send completion report: %s') % (e,))
        # If subcontractor changed, propagate to tickets and dockets
        if 'subcontractor_id' in vals:
            for record in self:
                rmc_sub = self.env['rmc.subcontractor'].search([('partner_id', '=', record.subcontractor_id.id)], limit=1)
                # Default pump provider if missing
                if rmc_sub and not record.pump_provider_id:
                    record.pump_provider_id = rmc_sub.id
                # Update helpdesk tickets linked via workorder.ticket_ids
                if record.ticket_ids:
                    rec_tickets = self.env['helpdesk.ticket'].browse(record.ticket_ids.mapped('helpdesk_ticket_id').ids)
                    if rec_tickets:
                        rec_tickets.write({'assigned_subcontractor_id': rmc_sub.id if rmc_sub else False})
                # Update existing dockets for this workorder
                dockets = self.env['rmc.docket'].search([('workorder_id', '=', record.id)])
                if dockets:
                    dockets.write({'subcontractor_id': rmc_sub.id if rmc_sub else False})
                # Default plant if missing
                if rmc_sub and not record.subcontractor_plant_id:
                    top_plant = rmc_sub.plant_ids[:1]
                    record.subcontractor_plant_id = top_plant.id if top_plant else False

                # NEW: Auto-transition to 'assigned_to_subcontractor' and create RFQ
                if record.subcontractor_id and record.state == 'draft':
                    record.state = 'assigned_to_subcontractor'
                    # Auto-create RFQ for this subcontractor
                    record._create_rfq_for_subcontractor()
        # If plant selected (programmatically or via form save), keep the current flow
        # Plant selection no longer auto-confirms; it stays in assigned_to_subcontractor
        if 'subcontractor_plant_id' in vals:
            for record in self:
                # Just ensure plant is set, state changes are handled elsewhere
                pass
        # If pump is toggled on or pump selection changed, ensure pump ticket exists
        if any(k in vals for k in ['pump_required', 'pump_id']):
            for rec in self:
                rec._ensure_pump_ticket()
        return res

    # -----------------
    # Reporting helpers
    # -----------------
    def _ensure_workorder_completion_report(self):
        """Ensure the Workorder Completion QWeb template and report action exist.
        Creates minimal versions if missing so printing can proceed.
        """
        self.ensure_one()
        env = self.sudo().env
        view_xmlid = 'rmc_management_system.report_workorder_completion_tmpl'
        report_xmlid = 'rmc_management_system.report_workorder_completion'

        # QWeb template
        # Prefer search by key to avoid broken xmlid placeholder records
        view = env['ir.ui.view'].search([
            ('type', '=', 'qweb'),
            ('key', '=', 'rmc_management_system.report_workorder_completion_tmpl')
        ], limit=1)
        if not view:
            # If xmlid exists but points to missing id, ignore and recreate view then fix xmlid below
            view_ref = env.ref(view_xmlid, raise_if_not_found=False)
            if view_ref and not view_ref.exists():
                view_ref = False
            # Minimal but valid template; users can upgrade later to load full XML
            arch = (
                '<t t-name="rmc_management_system.report_workorder_completion_tmpl">'
                '  <t t-call="web.html_container">'
                '    <t t-foreach="docs" t-as="wo">'
                '      <t t-call="web.external_layout">'
                '        <div class="page">'
                '          <h2>Workorder Completion Summary</h2>'
                '          <p>'
                '            <strong>Customer:</strong> <span t-esc="wo.partner_id.name"/>'
                '            &#160;|&#160; <strong>Sale Order:</strong> <span t-esc="wo.sale_order_id.name"/>'
                '            &#160;|&#160; <strong>Workorder:</strong> <span t-esc="wo.name"/>'
                '          </p>'
                '        </div>'
                '      </t>'
                '    </t>'
                '  </t>'
                '</t>'
            )
            view = env['ir.ui.view'].create({
                'name': 'report_workorder_completion_tmpl',
                'type': 'qweb',
                'key': 'rmc_management_system.report_workorder_completion_tmpl',
                'arch': arch,
            })
        # Ensure/repair xmlid for the view
        imd_view = env['ir.model.data'].sudo().search([
            ('module', '=', 'rmc_management_system'),
            ('name', '=', 'report_workorder_completion_tmpl')
        ], limit=1)
        if imd_view:
            if (imd_view.model != 'ir.ui.view') or (imd_view.res_id != view.id):
                imd_view.write({'model': 'ir.ui.view', 'res_id': view.id})
        else:
            env['ir.model.data'].sudo().create({
                'name': 'report_workorder_completion_tmpl',
                'module': 'rmc_management_system',
                'model': 'ir.ui.view',
                'res_id': view.id,
                'noupdate': True,
            })

        # Report action
        # Prefer search to avoid broken xmlid
        report = env['ir.actions.report'].search([
            ('model', '=', 'dropshipping.workorder'),
            ('report_name', '=', 'rmc_management_system.report_workorder_completion_tmpl'),
        ], limit=1)
        if not report:
            # If xmlid exists but points to a missing record, ignore it and create fresh
            report_ref = env.ref(report_xmlid, raise_if_not_found=False)
            if report_ref and not report_ref.exists():
                report_ref = False
            report = env['ir.actions.report'].create({
                'name': 'Workorder Completion Summary',
                'model': 'dropshipping.workorder',
                'report_type': 'qweb-pdf',
                'report_name': 'rmc_management_system.report_workorder_completion_tmpl',
                'print_report_name': "('Workorder_%s_Summary' % (object.name or ''))",
            })
        # Ensure/repair xmlid for the report
        imd_report = env['ir.model.data'].sudo().search([
            ('module', '=', 'rmc_management_system'),
            ('name', '=', 'report_workorder_completion')
        ], limit=1)
        if imd_report:
            if (imd_report.model != 'ir.actions.report') or (imd_report.res_id != report.id):
                imd_report.write({'model': 'ir.actions.report', 'res_id': report.id})
        else:
            env['ir.model.data'].sudo().create({
                'name': 'report_workorder_completion',
                'module': 'rmc_management_system',
                'model': 'ir.actions.report',
                'res_id': report.id,
                'noupdate': True,
            })
        return True
    def _get_workorder_completion_report_action(self):
        """Return the ir.actions.report for Workorder Completion.
        Prefer xmlid, but fallback to search by model/report_name so it still works
        if the external id hasn't been registered yet but the record exists.
        """
        # Prefer search (robust to broken xmlid)
        report = self.env['ir.actions.report'].sudo().search([
            ('model', '=', 'dropshipping.workorder'),
            ('report_name', '=', 'rmc_management_system.report_workorder_completion_tmpl'),
        ], limit=1)
        if report:
            return report
        # Fallback to xmlid, but ensure it actually exists
        report = self.env.ref('rmc_management_system.report_workorder_completion', raise_if_not_found=False)
        if report and report.exists():
            return report
        return False
    def _get_company_defaults(self):
        ICP = self.env['ir.config_parameter'].sudo()
        def _get_tmpl(key):
            val = ICP.get_param(key)
            try:
                return self.env['mail.template'].browse(int(val)) if val else False
            except Exception:
                return False
        return {
            'completion_template': _get_tmpl('rmc.template.wo_completion_id'),
            'cube7_template': _get_tmpl('rmc.template.cube7_id'),
            'cube28_template': _get_tmpl('rmc.template.cube28_id'),
            'default_cc': ICP.get_param('rmc.report.cc_emails') or False,
            'default_bcc': ICP.get_param('rmc.report.bcc_emails') or False,
        }

    def _render_workorder_completion_pdf(self):
        self.ensure_one()
        # Always call with xmlid first to support enterprise override signature
        report_xmlid = 'rmc_management_system.report_workorder_completion'
        # Ensure the report/action exists (self-heal if needed)
        if not self.env.ref(report_xmlid, raise_if_not_found=False):
            self._ensure_workorder_completion_report()
        try:
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(report_xmlid, [self.id])
        except Exception:
            # Final fallback: try with the action record if available (community signature)
            report = self._get_workorder_completion_report_action()
            if not report:
                return False, False
            pdf_content, _ = report._render_qweb_pdf([self.id])
        filename = f"Workorder_{self.name}_Summary.pdf"
        return pdf_content, filename

    @api.model
    def _normalize_email_list(self, value):
        """Coerce any iterable of emails into the comma-separated string format
        expected by the mail gateway."""
        if not value:
            return ''
        if isinstance(value, str):
            return value
        try:
            from collections.abc import Iterable
            if isinstance(value, Iterable):
                return ','.join(str(v).strip() for v in value if v)
        except Exception:
            return str(value)
        return str(value)

    @api.model
    def _normalize_email_any(self, value):
        """Accept strings, list-like strings or iterables and always return a
        comma-separated string."""
        if not value:
            return ''
        if isinstance(value, str):
            txt = value.strip()
            if txt.startswith('[') and txt.endswith(']'):
                try:
                    import ast
                    parsed = ast.literal_eval(txt)
                    return self._normalize_email_list(parsed)
                except Exception:
                    return value
            return value
        return self._normalize_email_list(value)

    def action_print_completion_summary(self):
        self.ensure_one()
        report = self._get_workorder_completion_report_action()
        if not report:
            # Attempt to create missing report and try again
            self._ensure_workorder_completion_report()
            report = self._get_workorder_completion_report_action()
        if not report:
            raise UserError(_('Workorder Completion report could not be created. Please contact your administrator.'))
        return report.report_action(self)

    def _send_workorder_completion_email(self):
        for wo in self:
            partner = wo.partner_id
            if not partner or not partner.email:
                wo.message_post(body=_('Skipped completion email: customer email missing.'))
                continue
            # Render PDF
            pdf, filename = wo._render_workorder_completion_pdf()
            if not pdf:
                wo.message_post(body=_('Workorder Completion PDF template not found.'))
                continue
            # Create attachment
            attach = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf).decode('utf-8'),
                'mimetype': 'application/pdf',
                'res_model': wo._name,
                'res_id': wo.id,
            })
            defaults = wo._get_company_defaults()
            body = _('Please find attached the Workorder Completion Summary for %s.') % (wo.name,)
            subject = _('Workorder %s - Completion Summary') % (wo.name,)
            to_val = wo._normalize_email_any(partner.email)
            cc_val = wo._normalize_email_any(wo.report_cc_emails or defaults['default_cc'])
            bcc_val = wo._normalize_email_any(wo.report_bcc_emails or defaults['default_bcc'])

            # Post a chatter note for history (no email sending here)
            msg = wo.message_post(
                body=body,
                subject=subject,
                message_type='comment',
                attachment_ids=[attach.id],
            )
            if msg and not wo.wo_report_root_message_id:
                wo.wo_report_root_message_id = msg.id

            # Build outbound email using mail.mail to avoid chatter split issues
            mail_values = {
                'subject': subject,
                'body_html': f'<p>{body}</p>',
                'body': body,
                'attachment_ids': [(4, attach.id)],
                'auto_delete': False,
                'model': wo._name,
                'res_id': wo.id,
            }
            if to_val:
                mail_values['email_to'] = to_val
            else:
                mail_values['partner_ids'] = [(4, partner.id)]
            if isinstance(cc_val, str) and cc_val.strip():
                mail_values['email_cc'] = cc_val
            if isinstance(bcc_val, str) and bcc_val.strip():
                mail_values['email_bcc'] = bcc_val
            sender = defaults.get('email_from') or wo.company_id.email or self.env.user.email_formatted
            if sender:
                mail_values['email_from'] = sender
            mail = self.env['mail.mail'].create(mail_values)
            try:
                mail.send()
            except Exception as mail_exc:
                wo.message_post(body=_('Workorder completion email failed to send: %s') % mail_exc)

    def _send_cube_followup(self, day_type):
        """Send cube tests for given day_type ('7' or '28') as a reply to the same thread."""
        self.ensure_one()
        if not self.date_completed:
            return False
        partner = self.partner_id
        if not partner or not partner.email:
            self.message_post(body=_('Skipped cube %s-day email: customer email missing.') % day_type)
            return False
        tests = self.env['quality.cube.test'].search([
            ('workorder_id', '=', self.id),
            ('day_type', '=', str(day_type)),
            ('retest_of_id', '=', False),
        ])
        if not tests:
            self.message_post(body=_('No %s-day cube tests found to send.') % day_type)
            return False
        report_xmlid = 'rmc_management_system.report_quality_cube_test'
        if not self.env.ref(report_xmlid, raise_if_not_found=False):
            self.message_post(body=_('Cube Test Report template missing.'))
            return False
        try:
            pdf, _ = self.env['ir.actions.report']._render_qweb_pdf(report_xmlid, tests.ids)
        except Exception:
            # Fallback to bound action call if enterprise override not present
            report = self.env.ref(report_xmlid, raise_if_not_found=False)
            if not report:
                self.message_post(body=_('Cube Test Report template missing.'))
                return False
            pdf, _ = report._render_qweb_pdf(tests.ids)
        filename = f"Cube_Tests_{self.name}_{day_type}Day.pdf"
        attach = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(pdf).decode('utf-8'),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        defaults = self._get_company_defaults()
        body = _('Please find attached the %s-Day Cube Test Report for %s.') % (day_type, self.name)
        subject = _('Workorder %s - %s-Day Cube Test Report') % (self.name, day_type)

        to_val = self._normalize_email_any(partner.email)
        cc_val = self._normalize_email_any(self.report_cc_emails or defaults['default_cc'])
        bcc_val = self._normalize_email_any(self.report_bcc_emails or defaults['default_bcc'])

        self.message_post(
            body=body,
            subject=subject,
            message_type='comment',
            attachment_ids=[attach.id],
            parent_id=self.wo_report_root_message_id.id if self.wo_report_root_message_id else False,
        )

        mail_values = {
            'subject': subject,
            'body_html': f'<p>{body}</p>',
            'body': body,
            'attachment_ids': [(4, attach.id)],
            'auto_delete': False,
            'model': self._name,
            'res_id': self.id,
        }
        if to_val:
            mail_values['email_to'] = to_val
        else:
            mail_values['partner_ids'] = [(4, partner.id)]
        if isinstance(cc_val, str) and cc_val.strip():
            mail_values['email_cc'] = cc_val
        if isinstance(bcc_val, str) and bcc_val.strip():
            mail_values['email_bcc'] = bcc_val
        sender = defaults.get('email_from') or self.company_id.email or self.env.user.email_formatted
        if sender:
            mail_values['email_from'] = sender
        mail = self.env['mail.mail'].create(mail_values)
        try:
            mail.send()
        except Exception as mail_exc:
            self.message_post(body=_('Cube %s-day email failed to send: %s') % (day_type, mail_exc))

        if str(day_type) == '7':
            self.cube7_last_sent = fields.Datetime.now()
        else:
            self.cube28_last_sent = fields.Datetime.now()
        return True

    def action_update_balance(self):
        for record in self:
            if record.partner_id:
                # Update cement balance in RMC material balances
                self.env['rmc.material.balance']._update_balance(record.partner_id, 'cement', -200)
        return True

    def action_update_qc(self):
        self.env['rmc.field.service.task']._auto_update_qc()
        return True

    def _update_material_balances(self):
        """Update material balances based on workorder lines"""
        for record in self:
            if record.partner_id:
                for line in record.workorder_line_ids:
                    if line.product_id and line.product_id.categ_id:
                        categ_name = line.product_id.categ_id.name.lower()
                        material_type = 'other'
                        if 'cement' in categ_name:
                            material_type = 'cement'
                        elif 'sand' in categ_name:
                            material_type = 'sand'
                        elif 'aggregate' in categ_name or 'gravel' in categ_name:
                            material_type = 'aggregate'
                        
                        # Deduct materials used in workorder
                        self.env['rmc.material.balance']._update_balance(
                            record.partner_id, material_type, -line.quantity_ordered)

    def action_test_move(self):
        origin_loc = self.env.ref('stock.stock_location_stock')
        dest_loc = self.env.ref('stock.stock_location_customers')
        product = self.env.ref('product.product_product_4')
        if origin_loc and dest_loc and product:
            self.env['stock.move']._create_move(origin_loc, dest_loc, product, 500)
        return True

    # Sanitize email fields for any chatter messages on Workorder
    def message_post(self, **kwargs):
        # Coerce email_to/email_cc/email_bcc to comma-separated strings if lists are passed
        for key in ('email_to', 'email_cc', 'email_bcc'):
            val = kwargs.get(key)
            if not val:
                continue
            # Already a string
            if isinstance(val, str):
                continue
            # Iterable -> join
            try:
                from collections.abc import Iterable
                if isinstance(val, Iterable):
                    kwargs[key] = ','.join(str(v) for v in val if v)
                    continue
            except Exception:
                kwargs[key] = str(val)
                continue
            # Fallback: stringify
            kwargs[key] = str(val)
        return super(DropshippingWorkorder, self).message_post(**kwargs)

class DropshippingWorkorderLine(models.Model):
    _name = 'dropshipping.workorder.line'
    _description = 'Dropshipping Workorder Line'

    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    product_id = fields.Many2one('product.product', string='Product')
    quantity_ordered = fields.Float(string='Quantity Ordered')
    quantity_delivered = fields.Float(string='Quantity Delivered')
    unit_price = fields.Float(string='Unit Price')
    total_amount = fields.Float(string='Total Amount', compute='_compute_total', store=True)

    @api.depends('quantity_ordered', 'unit_price')
    def _compute_total(self):
        for record in self:
            record.total_amount = record.quantity_ordered * record.unit_price

class DropshippingIngredientBalance(models.Model):
    _name = 'dropshipping.ingredient.balance'
    _description = 'Dropshipping Ingredient Balance'

    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    material_type = fields.Selection([
        ('cement', 'Cement'),
        ('sand', 'Sand'),
        ('aggregate', 'Aggregate'),
    ], string='Material Type')
    balance_qty = fields.Float(string='Balance Quantity')
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    last_updated = fields.Datetime(string='Last Updated', default=fields.Datetime.now)

class DropshippingWorkorderTicket(models.Model):
    _name = 'dropshipping.workorder.ticket'
    _description = 'Dropshipping Workorder Ticket'

    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    name = fields.Char(string='Ticket Name')
    quantity = fields.Float(string='Quantity')
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Helpdesk Ticket')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    delivery_date = fields.Datetime(string='Delivery Date')
    delivery_location = fields.Char(string='Delivery Location')
    delivery_coordinates = fields.Char(string='Delivery Coordinates')
    notes = fields.Text(string='Notes')
    # Pump-specific markers
    is_pump = fields.Boolean(string='Is Pump Ticket?')
    pump_id = fields.Many2one('rmc.subcontractor.pump', string='Pump')

    @api.model_create_multi
    def create(self, vals_list):
        records = super(DropshippingWorkorderTicket, self).create(vals_list)
        # After creating tickets, sync the workorder state
        # DISABLED: Auto-sync disabled to maintain manual state control
        # workorders = records.mapped('workorder_id')
        # workorders._sync_state_from_tickets()
        return records

    def write(self, vals):
        res = super(DropshippingWorkorderTicket, self).write(vals)
        # DISABLED: Auto-sync disabled to maintain manual state control
        # if 'state' in vals:
        #     self.mapped('workorder_id')._sync_state_from_tickets()
        return res

class DropshippingWarehouseShift(models.Model):
    _name = 'dropshipping.warehouse.shift'
    _description = 'Dropshipping Warehouse Shift'

    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder')
    product_id = fields.Many2one('product.product', string='Product')
    quantity_shifted = fields.Float(string='Quantity Shifted')
    from_location_id = fields.Many2one('stock.location', string='From Location')
    to_location_id = fields.Many2one('stock.location', string='To Location')
    shift_date = fields.Datetime(string='Shift Date', default=fields.Datetime.now)

# Removed duplicate light models for weighbridge/quality; keep only references used elsewhere.
class RmcWeighbridge(models.Model):
    _name = 'rmc.weighbridge'
    _description = 'RMC Weighbridge (stub)'

    name = fields.Char(string='Name', required=True)
    transaction_date = fields.Datetime(string='Transaction Date', default=fields.Datetime.now)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    batch_id = fields.Many2one('rmc.batch', string='Batch')
    subcontractor_id = fields.Many2one('res.partner', string='Subcontractor')
    vehicle_number = fields.Char(string='Vehicle Number')
    driver_name = fields.Char(string='Driver Name')
    driver_mobile = fields.Char(string='Driver Mobile')
    transporter = fields.Char(string='Transporter')
    plant_empty_weight = fields.Float(string='Plant Empty Weight')
    plant_loaded_weight = fields.Float(string='Plant Loaded Weight')
    plant_net_weight = fields.Float(string='Plant Net Weight', compute='_compute_net_weight')
    customer_empty_weight = fields.Float(string='Customer Empty Weight')
    customer_loaded_weight = fields.Float(string='Customer Loaded Weight')
    customer_net_weight = fields.Float(string='Customer Net Weight', compute='_compute_net_weight')
    weight_variance = fields.Float(string='Weight Variance', compute='_compute_variance')
    variance_percentage = fields.Float(string='Variance %', compute='_compute_variance')
    tolerance_percentage = fields.Float(string='Tolerance %', default=5.0)
    variance_action = fields.Selection([('accept', 'Accept'), ('reject', 'Reject')], string='Variance Action')
    kanta_parchi = fields.Binary(string='Kanta Parchi')
    delivery_challan = fields.Binary(string='Delivery Challan')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('completed', 'Completed')], string='State', default='draft')
    notes = fields.Text(string='Notes')

    @api.depends('plant_loaded_weight', 'plant_empty_weight')
    def _compute_net_weight(self):
        for record in self:
            record.plant_net_weight = record.plant_loaded_weight - record.plant_empty_weight
            record.customer_net_weight = record.customer_loaded_weight - record.customer_empty_weight

    @api.depends('plant_net_weight', 'customer_net_weight')
    def _compute_variance(self):
        for record in self:
            record.weight_variance = record.plant_net_weight - record.customer_net_weight
            if record.plant_net_weight and record.plant_net_weight != 0:
                record.variance_percentage = (record.weight_variance / record.plant_net_weight) * 100
            else:
                record.variance_percentage = 0.0


class RmcQualityCheck(models.Model):
    _name = 'rmc.quality.check'
    _description = 'RMC Quality Check (stub)'

    name = fields.Char(string='Name', required=True)
    check_date = fields.Datetime(string='Check Date', default=fields.Datetime.now)
    batch_id = fields.Many2one('rmc.batch', string='Batch')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    check_type = fields.Selection([('plant', 'Plant'), ('site', 'Site')], string='Check Type')
    check_location = fields.Char(string='Check Location')
    checker_name = fields.Char(string='Checker Name')
    slump_flow_actual = fields.Float(string='Slump Flow Actual')
    slump_flow_target = fields.Float(string='Slump Flow Target')
    temperature = fields.Float(string='Temperature')
    visual_inspection = fields.Text(string='Visual Inspection')
    sample_collected = fields.Boolean(string='Sample Collected')
    sample_id = fields.Char(string='Sample ID')
    compression_strength_7day = fields.Float(string='Compression Strength 7 Day')
    compression_strength_28day = fields.Float(string='Compression Strength 28 Day')
    overall_result = fields.Selection([('pass', 'Pass'), ('fail', 'Fail')], string='Overall Result')
    quality_certificate = fields.Binary(string='Quality Certificate')
    test_photos = fields.Binary(string='Test Photos')
    notes = fields.Text(string='Notes')
    corrective_actions = fields.Text(string='Corrective Actions')

    

# Inherit sale.order to add fields
class SaleOrder(models.Model):
    _inherit = 'sale.order'

    customer_provides_cement = fields.Boolean(string='Customer Provides Cement')
    delivery_coordinates = fields.Char(string='Delivery Coordinates')
    required_slump = fields.Float(string='Required Slump')
    pour_structure = fields.Char(string='Pour Structure')
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Helpdesk Ticket')
    batch_count = fields.Integer(string='Batch Count', compute='_compute_counts')
    quality_check_count = fields.Integer(string='Quality Check Count', compute='_compute_counts')
    batch_ids = fields.One2many('rmc.batch', 'sale_order_id', string='Batches')
    quality_check_ids = fields.One2many('rmc.quality.check', 'sale_order_id', string='Quality Checks')
    weighbridge_ids = fields.One2many('rmc.weighbridge', 'sale_order_id', string='Weighbridges')

    @api.depends('batch_ids', 'quality_check_ids')
    def _compute_counts(self):
        for record in self:
            record.batch_count = len(record.batch_ids)
            record.quality_check_count = len(record.quality_check_ids)
