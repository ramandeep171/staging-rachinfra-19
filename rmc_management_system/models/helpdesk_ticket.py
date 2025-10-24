from odoo import models, fields, api, _

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'
    # Link to Odoo Field Service task (official FSM uses project.task with is_fsm=True)
    fsm_task_id = fields.Many2one('project.task', string='Field Service Task', readonly=True, copy=False, ondelete='set null')
    # Track if this ticket was created from the Field Service button
    is_field_service_created = fields.Boolean(string='Created from Field Service', default=False)

    # RMC Specific Fields
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    assigned_subcontractor_id = fields.Many2one('rmc.subcontractor', string='Assigned Subcontractor', ondelete='set null')
    distance_to_site = fields.Float(string='Distance to Site (Km)')
    # Quantity for this ticket (M3)
    rmc_quantity = fields.Float(string='Ticket Quantity (M3)')
    # Delivered/Remaining quantities (computed from production batches)
    rmc_qty_delivered = fields.Float(string='Delivered (M3)', compute='_compute_rmc_qty_stats', store=False, readonly=True)
    rmc_qty_remaining = fields.Float(string='Remaining (M3)', compute='_compute_rmc_qty_stats', store=False, readonly=True)
    # Optional: allow selecting a different subcontractor specifically for transport
    transport_subcontractor_id = fields.Many2one(
        'rmc.subcontractor',
        string='otherTransport Subcontractor',
        domain="[('has_transport','=',True), ('transport_ids','!=', False)]",
        help='Choose a transport-providing subcontractor. If empty, Transport shows options from Assigned Subcontractor.'
    )
    # Helper field to drive domain: if transport_subcontractor_id is set use it, otherwise fall back to assigned_subcontractor_id
    domain_transport_subcontractor_id = fields.Many2one(
        'rmc.subcontractor', string='Domain Transport Subcontractor', compute='_compute_domain_transport_subcon', store=False)
    transporter_id = fields.Many2one(
        'rmc.subcontractor.transport',
        string='Transport',
        domain="[('subcontractor_id','=', domain_transport_subcontractor_id)]",
    )
    
    # RMC Status
    rmc_status = fields.Selection([
        ('new', 'New'),
        ('assigned', 'Assigned to Subcontractor'),
        ('pending_acceptance', 'Pending Acceptance'),
        ('accepted', 'Accepted'),
        ('in_production', 'In Production'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('plant_breakdown', 'Plant Breakdown'),
        ('completed', 'Completed'),
    ], string='RMC Status', default='new')
    
    # RMC Product flag
    is_rmc_product = fields.Boolean(string='Is RMC Product', compute='_compute_is_rmc_product', store=True)
    
    # Relations
    batch_ids = fields.One2many('rmc.batch', 'helpdesk_ticket_id', string='Batches')
    field_service_task_ids = fields.One2many('rmc.field.service.task', 'ticket_id', string='Field Service Tasks')
    field_service_task_count = fields.Integer(string='Field Service Task Count', compute='_compute_field_service_task_count')

    # Related workorder tickets created from diversion or generation
    workorder_ticket_ids = fields.One2many(
        'dropshipping.workorder.ticket', 'helpdesk_ticket_id', string='Workorder Tickets')
    workorder_ticket_count = fields.Integer(
        string='Workorder Tickets', compute='_compute_workorder_ticket_count')

    # For ordering: flag tickets whose stage is 'In Progress'
    is_in_progress_stage = fields.Boolean(
        string='Is In Progress', compute='_compute_is_in_progress_stage', store=True)

    # UI helper: show Divert button when any linked docket is in 'ready'
    show_divert_button = fields.Boolean(string='Show Divert', compute='_compute_show_divert_button', store=False)

    # Diversion linkage
    diverted_from_ticket_id = fields.Many2one(
        'helpdesk.ticket', string='Diverted From', help='Original ticket this was diverted from')
    diverted_from_ticket_name = fields.Char(
        string='Diverted From Ticket Name',
        help='Name of the original ticket this record was diverted from (snapshot at diversion time).',
        copy=False,
        readonly=True,
    )
    last_diverted_ticket_name = fields.Char(
        string='Last Diverted Ticket Name',
        help='On the original ticket, stores the name of the most recently created diverted ticket.',
        copy=False,
        readonly=True,
    )
    diverted_child_ticket_ids = fields.One2many(
        'helpdesk.ticket', 'diverted_from_ticket_id', string='Diverted Tickets')

    # Cancellation audit
    cancel_reason_category = fields.Selection([
        ('customer_request', 'Customer Request'),
        ('plant_breakdown', 'Plant Breakdown'),
        ('logistics_issue', 'Logistics Issue'),
        ('quality_issue', 'Quality Issue'),
        ('other', 'Other'),
    ], string='Cancel Reason Category', readonly=True)
    cancel_reason = fields.Text(string='Cancel Reason', readonly=True)

    # RMC Details references
    delivery_track_ids = fields.One2many(
        'rmc.delivery_track', 'helpdesk_ticket_id', string='Delivery Tracks')
    docket_ids = fields.One2many('rmc.docket', 'helpdesk_ticket_id', string='Dockets')
    truck_loading_ids = fields.Many2many(
        'rmc.truck_loading', compute='_compute_truck_loading_ids', string='Truck Loadings', store=False)
    plant_check_ids = fields.Many2many(
        'rmc.plant_check', compute='_compute_plant_check_ids', string='Plant Checks', store=False)
    delivery_variance_ids = fields.Many2many(
        'rmc.delivery_variance', compute='_compute_delivery_variance_ids', string='Delivery Variances', store=False)

    # Docket Batches linked via the ticket's dockets (for visibility under RMC Details)
    docket_batch_ids = fields.Many2many(
        'rmc.docket.batch', compute='_compute_docket_batch_ids', string='Docket Batches', store=False)

    # Direct Workorder reference for UX: resolved via (1) linked workorder tickets, else (2) linked dockets
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder', compute='_compute_workorder_id', store=False)

    @api.depends('sale_order_id.is_rmc_product')
    def _compute_is_rmc_product(self):
        for ticket in self:
            ticket.is_rmc_product = ticket.sale_order_id.is_rmc_product if ticket.sale_order_id else False

    def unlink(self):
        """Override unlink to archive instead of delete when there are foreign key constraints"""
        # Check for related records that would prevent deletion
        for record in self:
            # Check for related batches
            if record.batch_ids:
                # Archive related batches first
                record.batch_ids.write({'active': False})
            
            # Check for related field service tasks
            if record.field_service_task_ids:
                # Archive related field service tasks
                record.field_service_task_ids.write({'active': False})
            
            # Check for related workorders
            workorders = self.env['dropshipping.workorder'].search([('helpdesk_ticket_id', '=', record.id)])
            if workorders:
                # Archive workorders that are in draft or cancelled state
                workorders.filtered(lambda w: w.state in ['draft', 'cancelled']).write({'active': False})
        
        # Try to delete normally first
        try:
            return super().unlink()
        except Exception as e:
            error_msg = str(e).lower()
            if ('foreign key constraint' in error_msg or 
                'requires the record' in error_msg or 
                'still referenced' in error_msg or
                'violates foreign key constraint' in error_msg):
                # If deletion fails due to foreign key constraints, archive the ticket instead
                self.write({'active': False})
                return True
            else:
                # Re-raise other exceptions
                raise

    def action_create_field_service_task(self):
        """Create an Odoo Field Service (project.task with is_fsm=True) for this ticket and link it."""
        self.ensure_one()
        if not self.fsm_task_id:
            # Find a default FSM project (project.project with is_fsm=True), or create one if needed
            fsm_project = self.env['project.project'].search([('is_fsm', '=', True)], limit=1)
            if not fsm_project:
                fsm_project = self.env['project.project'].create({'name': 'RMC Field Service', 'is_fsm': True})
            vals = {
                'name': f"Helpdesk: {self.name}",
                'project_id': fsm_project.id,
                'partner_id': self.partner_id.id if self.partner_id else False,
                'is_fsm': True,
                'planned_date_begin': fields.Datetime.now(),
                'description': self.description or '',
            }
            fsm_task = self.env['project.task'].create(vals)
            self.fsm_task_id = fsm_task.id
        return True

    def action_open_fsm_task(self):
        """Open the linked official Field Service task (project.task) if present."""
        self.ensure_one()
        if not self.fsm_task_id:
            return True
        return {
            'type': 'ir.actions.act_window',
            'name': _('Field Service Task'),
            'res_model': 'project.task',
            'view_mode': 'form',
            'res_id': self.fsm_task_id.id,
            'target': 'current',
        }

    def _compute_field_service_task_count(self):
        for ticket in self:
            ticket.field_service_task_count = len(ticket.field_service_task_ids or [])

    def action_view_field_service_tasks(self):
        """View field service tasks for this ticket"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Field Service Tasks'),
            'res_model': 'rmc.field.service.task',
            'view_mode': 'list,form',
            'domain': [('ticket_id', '=', self.id)],
            'context': {'default_ticket_id': self.id},
        }

    def _compute_rmc_qty_stats(self):
        """Compute delivered and remaining quantities based on linked batches.

        Delivered priority:
        1) Sum of docket.quantity_produced across all dockets linked to this ticket (user-visible Produced wins).
        2) Else, sum of Truck Loading total quantities for loadings linked to this ticket's dockets (or via delivery tracks).
        3) Else, sum of rmc.batch linked directly to this ticket (quantity_produced fallback quantity_ordered).
        4) Else, sum of rmc.docket.batch for linked dockets; fallback to docket quantity fields.
        Remaining = max(0, rmc_quantity - delivered)
        """
        Batch = self.env['rmc.batch'].sudo()
        TL = self.env['rmc.truck_loading'].sudo()
        DocketBatch = self.env['rmc.docket.batch'].sudo()
        for rec in self:
            delivered = 0.0
            # 1) Prefer docket.quantity_produced (sum across all dockets)
            try:
                if rec.docket_ids:
                    total_produced = sum(float(d.quantity_produced or 0.0) for d in rec.docket_ids)
                    if total_produced > 0.0:
                        delivered = total_produced
            except Exception:
                pass

            # 2) Truck loadings from dockets (fallback if produced not available)
            try:
                if delivered <= 0.0:
                    docket_ids = rec.docket_ids.ids or []
                    if docket_ids:
                        tls = TL.search([('docket_id', 'in', docket_ids)])
                        if tls:
                            delivered = sum(float((tl.total_quantity or 0.0)) for tl in tls)
                    # If no dockets or none delivered via TLs, try via computed truck_loading_ids (from delivery tracks)
                    if delivered <= 0.0 and rec.truck_loading_ids:
                        delivered = sum(float((tl.total_quantity or 0.0)) for tl in rec.truck_loading_ids)
            except Exception:
                pass

            # 3) Direct rmc.batch linked to ticket
            if delivered <= 0.0 and rec.id:
                try:
                    batches = Batch.search([('helpdesk_ticket_id', '=', rec.id)])
                    for b in batches:
                        delivered += (b.quantity_produced or 0.0) or (b.quantity_ordered or 0.0)
                except Exception:
                    pass

            # 4) Docket batches or docket fields
            if delivered <= 0.0 and rec.docket_ids:
                try:
                    for d in rec.docket_ids:
                        dbatches = DocketBatch.search([('docket_id', '=', d.id)])
                        if dbatches:
                            delivered += sum(float(b.quantity_ordered or 0.0) for b in dbatches)
                        else:
                            delivered += float((d.quantity_produced or 0.0) or (d.quantity_ordered or 0.0))
                except Exception:
                    pass

            rec.rmc_qty_delivered = delivered
            qty = float(rec.rmc_quantity or 0.0)
            rec.rmc_qty_remaining = max(0.0, qty - delivered)

    def _compute_workorder_ticket_count(self):
        for ticket in self:
            ticket.workorder_ticket_count = len(ticket.workorder_ticket_ids or [])

    @api.depends('stage_id')
    def _compute_is_in_progress_stage(self):
        for rec in self:
            name = (rec.stage_id.name or '').lower() if rec.stage_id else ''
            rec.is_in_progress_stage = 'progress' in name

    def action_view_workorder_tickets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Workorder Tickets'),
            'res_model': 'dropshipping.workorder.ticket',
            'view_mode': 'list,form',
            'domain': [('helpdesk_ticket_id', '=', self.id)],
            'context': {'default_helpdesk_ticket_id': self.id},
        }

    @api.depends('docket_ids.state')
    def _compute_show_divert_button(self):
        for rec in self:
            rec.show_divert_button = any(d.state == 'in_production' for d in rec.docket_ids)

    def action_cancel_ticket(self):
        """Mark ticket as cancelled and sync related workorder tickets."""
        for rec in self:
            try:
                # If helpdesk stages include 'Cancelled', try to move to that stage by name
                cancelled_stage = self.env['helpdesk.stage'].search([('name', 'ilike', 'cancel')], limit=1)
                if cancelled_stage:
                    rec.stage_id = cancelled_stage.id
                # Update RMC status to Completed/Delivered-cancelled like state if used
                if hasattr(rec, 'rmc_status'):
                    rec.rmc_status = 'completed'
                # Sync related workorder tickets
                if rec.workorder_ticket_ids:
                    rec.workorder_ticket_ids.write({'state': 'cancelled'})
            except Exception:
                # Non-blocking
                pass
        return True

    # --- Computes for RMC Details ---
    def _compute_truck_loading_ids(self):
        for rec in self:
            # Collect Truck Loadings from Delivery Tracks
            loads_from_tracks = rec.delivery_track_ids.mapped('truck_loading_id').ids
            # Also include Truck Loadings linked to the ticket's Dockets directly
            loads_from_dockets = rec.docket_ids.mapped('truck_loading_ids').ids
            all_loads = list({*loads_from_tracks, *loads_from_dockets})
            rec.truck_loading_ids = [(6, 0, all_loads)]

    def _compute_plant_check_ids(self):
        for rec in self:
            plant_checks = rec.truck_loading_ids.mapped('plant_check_id').ids
            rec.plant_check_ids = [(6, 0, plant_checks)]

    def _compute_delivery_variance_ids(self):
        for rec in self:
            dv_ids = []
            if rec.truck_loading_ids:
                dv_ids = self.env['rmc.delivery_variance'].search([
                    ('truck_loading_id', 'in', rec.truck_loading_ids.ids)
                ]).ids
            rec.delivery_variance_ids = [(6, 0, dv_ids)]

    def _compute_workorder_id(self):
        for rec in self:
            wo = False
            # Prefer workorder via workorder tickets mapping
            if rec.workorder_ticket_ids:
                wo = rec.workorder_ticket_ids[:1].workorder_id
            # Fallback to any docket linked to this ticket
            if not wo and rec.docket_ids:
                wo = rec.docket_ids[:1].workorder_id
            rec.workorder_id = wo.id if wo else False

    def _compute_docket_batch_ids(self):
        for rec in self:
            db_ids = rec.docket_ids.mapped('docket_batch_ids').ids
            rec.docket_batch_ids = [(6, 0, db_ids)]

    def action_assign_subcontractor(self):
        """Open wizard to assign subcontractor"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assign Subcontractor'),
            'res_model': 'rmc.subcontractor.assignment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_open_divert_ticket_wizard(self):
        """Open the Divert Ticket wizard to choose a target workorder and new site."""
        self.ensure_one()
        # Pick a sensible default Truck Loading to minimize user effort and avoid validation errors
        default_tl_id = False
        try:
            tls = self.truck_loading_ids
            if not tls and self.docket_ids:
                # Fall back to TLs found via the ticket's dockets
                tls = self.env['rmc.truck_loading'].sudo().search([
                    ('docket_id', 'in', self.docket_ids.ids)
                ], order='id desc')
            if tls:
                tl_in_prog = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['in_progress'])[:1]
                tl_sched = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['scheduled'])[:1]
                default_tl = tl_in_prog or tl_sched or tls[:1]
                default_tl_id = default_tl.id if default_tl else False
        except Exception:
            default_tl_id = False

        ctx = {'default_ticket_id': self.id}
        if default_tl_id:
            ctx['default_truck_loading_id'] = default_tl_id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rmc.divert.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_open_cancel_ticket_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancel Ticket'),
            'res_model': 'helpdesk.ticket.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

    def action_open_breakdown_wizard(self):
        """Open the Plant Breakdown (Half Load) wizard from the ticket.
        Prefill the Truck Loading if one is available for this ticket.
        """
        self.ensure_one()
        # Choose a sensible default truck loading (prefer in_progress, then scheduled, else any)
        default_tl_id = False
        try:
            tls = self.truck_loading_ids
            # Try to prioritize by status if field is present
            if tls:
                tl_in_prog = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['in_progress'])[:1]
                tl_sched = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['scheduled'])[:1]
                default_tl = tl_in_prog or tl_sched or tls[:1]
                default_tl_id = default_tl.id if default_tl else False
        except Exception:
            default_tl_id = False

        action = self.env.ref('rmc_management_system.action_rmc_breakdown_wizard').read()[0]
        ctx = dict(self.env.context or {})
        if default_tl_id:
            ctx.update({'default_truck_loading_id': default_tl_id})
        action['context'] = ctx
        return action

    @api.onchange('transport_subcontractor_id')
    def _onchange_transport_subcontractor_id(self):
        """When the transport subcontractor changes, clear the selected transport to enforce the new domain."""
        for rec in self:
            rec.transporter_id = False

    @api.onchange('assigned_subcontractor_id')
    def _onchange_assigned_subcontractor_id_clear_transport(self):
        """Changing assigned subcontractor can change domain; clear transport to avoid invalid value."""
        for rec in self:
            rec.transporter_id = False

    @api.depends('transport_subcontractor_id', 'assigned_subcontractor_id')
    def _compute_domain_transport_subcon(self):
        for rec in self:
            rec.domain_transport_subcontractor_id = rec.transport_subcontractor_id or rec.assigned_subcontractor_id

    # --- Workflow hooks ---
    def write(self, vals):
        # Track stage change to trigger Docket creation and ticket state updates
        stage_changed = 'stage_id' in vals
        res = super(HelpdeskTicket, self).write(vals)
        if stage_changed:
            for rec in self:
                try:
                    stage = rec.stage_id
                    stage_name = (stage.name or '').lower()
                    if 'progress' in stage_name:  # matches 'In Progress'
                        # 1) Create Docket if not already linked
                        if not rec.docket_ids:
                            # Derive workorder via workorder ticket mapping
                            wo_ticket = rec.workorder_ticket_ids[:1]
                            wo = wo_ticket.workorder_id if wo_ticket else False
                            so = wo.sale_order_id if wo else False
                            # Quantities mapping
                            qty_ticket = rec.rmc_quantity or (wo_ticket.quantity if wo_ticket else 0.0)
                            qty_so = 0.0
                            if so and so.order_line:
                                # Take first line's ordered qty as per user's mapping rule
                                first_line = so.order_line[0]
                                qty_so = first_line.product_uom_qty
                            # Docket number: do NOT assign when created from ticket
                            seq = ''
                            docket_vals = {
                                'docket_number': seq,
                                'docket_date': fields.Datetime.now(),
                                'sale_order_id': so.id if so else False,
                                'helpdesk_ticket_id': rec.id,
                                'workorder_id': wo.id if wo else False,
                                'quantity_ordered': qty_so or 0.0,
                                'quantity_produced': qty_ticket or 0.0,
                            }
                            # Propagate subcontractor (rmc.subcontractor) from Workorder if available
                            try:
                                if wo and getattr(wo, 'rmc_subcontractor_id', False):
                                    docket_vals['subcontractor_id'] = wo.rmc_subcontractor_id.id
                            except Exception:
                                pass
                            # Capacity: set from selected workorder subcontractor plant
                            if wo and wo.subcontractor_plant_id and wo.subcontractor_plant_id.capacity:
                                docket_vals['current_capacity'] = wo.subcontractor_plant_id.capacity
                                docket_vals.setdefault('subcontractor_plant_id', wo.subcontractor_plant_id.id)
                            elif wo and wo.subcontractor_plant_id:
                                docket_vals.setdefault('subcontractor_plant_id', wo.subcontractor_plant_id.id)
                            # Propagate recipe from workorder to docket
                            if wo and getattr(wo, 'recipe_id', False):
                                docket_vals['recipe_id'] = wo.recipe_id.id
                            # Propagate subcontractor transport if set on ticket
                            if rec.transporter_id:
                                docket_vals['subcontractor_transport_id'] = rec.transporter_id.id
                            new_docket = rec.env['rmc.docket'].create(docket_vals)
                            # Auto-create batches if capacity present
                            if new_docket.current_capacity:
                                try:
                                    new_docket._generate_batches()
                                except Exception:
                                    pass
                            # Backfill Ticket Quantity so the ticket shows a value
                            try:
                                # Prefer the ticket quantity we derived; else fallback to docket's ordered qty
                                if not rec.rmc_quantity:
                                    if qty_ticket and qty_ticket > 0:
                                        rec.rmc_quantity = qty_ticket
                                    elif new_docket and getattr(new_docket, 'quantity_ordered', 0.0) > 0:
                                        rec.rmc_quantity = new_docket.quantity_ordered
                            except Exception:
                                pass
                        # 2) Update related workorder tickets to in_progress
                        if rec.workorder_ticket_ids:
                            rec.workorder_ticket_ids.write({'state': 'in_progress'})
                    elif any(w in stage_name for w in ['solved', 'done', 'closed', 'complete']):
                        # Mark related workorder tickets as completed when helpdesk ticket is solved/done
                        if rec.workorder_ticket_ids:
                            rec.workorder_ticket_ids.write({'state': 'completed'})
                    elif 'cancel' in stage_name:
                        # Safety: set related workorder tickets to cancelled if ticket is cancelled
                        if rec.workorder_ticket_ids:
                            rec.workorder_ticket_ids.write({'state': 'cancelled'})
                except Exception:
                    # Non-blocking: avoid raising during write
                    pass
        return res
