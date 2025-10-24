from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RmcDivertWizard(models.TransientModel):
    _name = 'rmc.divert.wizard'
    _description = 'RMC Divert Ticket Wizard'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True, readonly=True)
    truck_loading_id = fields.Many2one('rmc.truck_loading', string='Truck Loading', required=True)
    # show workorders that are running or assigned so helpdesk can pick one
    target_workorder_id = fields.Many2one(
        'dropshipping.workorder',
        string='Target Workorder',
        help='Select any workorder to divert this ticket to',
    )
    new_site_id = fields.Many2one('res.partner', string='New Site')
    # Parity with Plant Breakdown wizard
    docket_id = fields.Many2one('rmc.docket', string='Docket', related='truck_loading_id.docket_id', store=False)
    original_subcontractor_id = fields.Many2one('rmc.subcontractor', string='Original Subcontractor',
                                               related='truck_loading_id.subcontractor_id', store=False)
    new_subcontractor_id = fields.Many2one('rmc.subcontractor', string='New Subcontractor')
    loaded_at_original = fields.Float(string='Loaded at Original (M3)')
    remaining_to_complete = fields.Float(string='Remaining to Complete (M3)')
    create_draft = fields.Boolean(string='Create Bills as Draft', default=True,
        help='Shown for parity with Plant Breakdown. Vendor bills are handled in PB flow if configured.')
    # Plant Breakdown mode: use remaining quantity; do not move existing loaded batches
    plant_breakdown_mode = fields.Boolean(string='Plant Breakdown (Half Load) Mode', default=False,
        help='When enabled, divert the remaining quantity to the target workorder without moving loaded batches.')

    # Quantity controls
    divert_qty = fields.Float(string='Divert Quantity (M3)', required=True, default=0.0)
    # Computed helper stats for validation and UX
    ticket_ordered_qty = fields.Float(string='Ticket Ordered (M3)', compute='_compute_limits', store=False)
    ticket_delivered_qty = fields.Float(string='Ticket Delivered (M3)', compute='_compute_limits', store=False)
    ticket_remaining_qty = fields.Float(string='Ticket Remaining (M3)', compute='_compute_limits', store=False)
    docket_ordered_qty = fields.Float(string='Docket Ordered (M3)', compute='_compute_limits', store=False)
    docket_delivered_qty = fields.Float(string='Docket Delivered (M3)', compute='_compute_limits', store=False)
    docket_remaining_qty = fields.Float(string='Docket Remaining (M3)', compute='_compute_limits', store=False)
    max_divert_qty = fields.Float(string='Max Divert Qty (M3)', compute='_compute_limits', store=False)

    # Human-readable summary for quick glance
    rmc_summary = fields.Char(string='RMC Summary', compute='_compute_rmc_summary', store=False)

    # Helper for safe domain binding in XML
    ticket_docket_ids = fields.Many2many('rmc.docket', string='Ticket Dockets', compute='_compute_ticket_dockets', store=False)

    def _compute_ticket_dockets(self):
        for wiz in self:
            wiz.ticket_docket_ids = [(6, 0, wiz.ticket_id.docket_ids.ids if wiz.ticket_id else [])]

    @api.depends(
        'ticket_ordered_qty', 'ticket_delivered_qty', 'ticket_remaining_qty',
        'docket_ordered_qty', 'docket_delivered_qty', 'docket_remaining_qty'
    )
    def _compute_rmc_summary(self):
        for wiz in self:
            wiz.rmc_summary = (
                'Ticket: Ordered %.3f, Delivered %.3f, Remaining %.3f | '
                'Docket: Ordered %.3f, Delivered %.3f, Remaining %.3f'
            ) % (
                float(wiz.ticket_ordered_qty or 0.0),
                float(wiz.ticket_delivered_qty or 0.0),
                float(wiz.ticket_remaining_qty or 0.0),
                float(wiz.docket_ordered_qty or 0.0),
                float(wiz.docket_delivered_qty or 0.0),
                float(wiz.docket_remaining_qty or 0.0),
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        # If ticket provided but no truck loading, pick a sensible default to avoid validation errors
        ticket_id = values.get('ticket_id') or self.env.context.get('default_ticket_id')
        # Ensure ticket_id is set early to avoid recursive default_get when reading Many2one in computes
        if ticket_id and not values.get('ticket_id'):
            values['ticket_id'] = ticket_id
        tl_id = values.get('truck_loading_id') or self.env.context.get('default_truck_loading_id')
        ticket = None
        if ticket_id and not tl_id:
            try:
                ticket = self.env['helpdesk.ticket'].browse(ticket_id)
                tls = ticket.truck_loading_ids
                if not tls and ticket.docket_ids:
                    # Fall back to TLs via ticket's dockets
                    tls = self.env['rmc.truck_loading'].sudo().search([
                        ('docket_id', 'in', ticket.docket_ids.ids)
                    ], order='id desc')
                if tls:
                    tl_in_prog = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['in_progress'])[:1]
                    tl_sched = tls.filtered(lambda t: getattr(t, 'loading_status', '') in ['scheduled'])[:1]
                    default_tl = tl_in_prog or tl_sched or tls[:1]
                    if default_tl:
                        values['truck_loading_id'] = default_tl.id
                        tl_id = default_tl.id
            except Exception:
                pass
        # Default target workorder: prefer ticket.workorder_id, else docket.workorder
        if ticket is None and ticket_id:
            ticket = self.env['helpdesk.ticket'].browse(ticket_id)
        if not values.get('target_workorder_id'):
            target_wo = False
            try:
                if ticket and getattr(ticket, 'workorder_id', False):
                    target_wo = ticket.workorder_id
                if not target_wo and tl_id:
                    tl = self.env['rmc.truck_loading'].browse(tl_id)
                    target_wo = getattr(tl.docket_id, 'workorder_id', False)
                if target_wo:
                    values['target_workorder_id'] = target_wo.id
            except Exception:
                pass
        # Pre-populate parity and quantity fields so user doesn't hit validation on empty qty
        tl_id = values.get('truck_loading_id') or self.env.context.get('default_truck_loading_id')
        if tl_id:
            tl = self.env['rmc.truck_loading'].browse(tl_id)
            try:
                values['loaded_at_original'] = float(tl.total_quantity or 0.0)
            except Exception:
                pass
            # Compute remaining and caps directly to avoid triggering computes on a new transient record
            try:
                if ticket is None and ticket_id:
                    ticket = self.env['helpdesk.ticket'].browse(ticket_id)
                docket = tl.docket_id if tl else False
                # Helper: sum delivered quantities
                def _sum_batches(domain):
                    batches = self.env['rmc.batch'].sudo().search(domain)
                    total = 0.0
                    for b in batches:
                        total += (b.quantity_produced or 0.0) or (b.quantity_ordered or 0.0)
                    return total
                TL = self.env['rmc.truck_loading'].sudo()
                DocketBatch = self.env['rmc.docket.batch'].sudo()
                ordered_t = float(getattr(ticket, 'rmc_quantity', 0.0) or 0.0) if ticket else 0.0
                delivered_t = 0.0
                if ticket:
                    docket_ids = ticket.docket_ids.ids or []
                    if docket_ids:
                        tls = TL.search([('docket_id', 'in', docket_ids)])
                        if tls:
                            delivered_t = sum(float((x.total_quantity or 0.0)) for x in tls)
                    if delivered_t <= 0.0 and ticket.truck_loading_ids:
                        delivered_t = sum(float((x.total_quantity or 0.0)) for x in ticket.truck_loading_ids)
                    if delivered_t <= 0.0:
                        delivered_t = _sum_batches([('helpdesk_ticket_id', '=', ticket.id)])
                    if delivered_t <= 0.0 and docket_ids:
                        # fallback via docket batches and fields
                        dbatches = DocketBatch.search([('docket_id', 'in', docket_ids)])
                        if dbatches:
                            delivered_t = sum(float((b.quantity_ordered or 0.0)) for b in dbatches)
                        else:
                            # sum docket quantities
                            d_recs = self.env['rmc.docket'].sudo().browse(docket_ids)
                            delivered_t = sum(float(((d.quantity_produced or 0.0) or (d.quantity_ordered or 0.0))) for d in d_recs)
                remaining_t = max(0.0, ordered_t - delivered_t)

                ordered_d = float(getattr(docket, 'quantity_ordered', 0.0) or 0.0) if docket else 0.0
                delivered_d = 0.0
                if docket:
                    tls_d = TL.search([('docket_id', '=', docket.id)])
                    if tls_d:
                        delivered_d = sum(float((x.total_quantity or 0.0)) for x in tls_d)
                    if delivered_d <= 0.0:
                        delivered_d = _sum_batches([('docket_id', '=', docket.id)])
                    if delivered_d <= 0.0:
                        # fallback via rmc.docket.batch lines, else docket fields
                        dbatches = DocketBatch.search([('docket_id', '=', docket.id)])
                        if dbatches:
                            delivered_d = sum(float((b.quantity_ordered or 0.0)) for b in dbatches)
                        else:
                            delivered_d = float(((docket.quantity_produced or 0.0) or (docket.quantity_ordered or 0.0)))
                remaining_d = max(0.0, ordered_d - delivered_d)

                values['remaining_to_complete'] = remaining_t
                cap = min(remaining_t, remaining_d) if (remaining_t and remaining_d) else 0.0
                loaded = float(getattr(tl, 'total_quantity', 0.0) or 0.0)
                if values.get('plant_breakdown_mode'):
                    values['divert_qty'] = cap
                else:
                    # Prefer loaded capped by remaining; if loaded is 0, fall back to cap to avoid 0 default
                    values['divert_qty'] = (min(loaded, cap) if loaded > 0.0 and cap > 0.0 else (cap if cap > 0.0 else loaded))
            except Exception:
                # Fallback: at least set divert_qty from loaded
                loaded = float(getattr(tl, 'total_quantity', 0.0) or 0.0)
                values['divert_qty'] = loaded
        return values

    @api.onchange('truck_loading_id', 'plant_breakdown_mode')
    def _onchange_truck_loading_id_set_qty(self):
        """When a truck loading is chosen, propose its total loaded quantity as the divert quantity
        but cap it by the computed max allowed.
        """
        if self.truck_loading_id:
            # ensure limits are recomputed for a correct cap
            self._compute_limits()
            cap = float(self.max_divert_qty or 0.0)
            # Fill PB parity fields
            try:
                self.loaded_at_original = float(self.truck_loading_id.total_quantity or 0.0)
                # Default remaining_to_complete to ticket remaining for clarity
                self.remaining_to_complete = float(self.ticket_remaining_qty or 0.0)
            except Exception:
                pass
            if self.plant_breakdown_mode:
                # Use remaining as divert quantity in PB mode
                self.divert_qty = cap
            else:
                loaded = float(self.truck_loading_id.total_quantity or 0.0)
                # Prefer loaded capped by remaining; if loaded is 0, fall back to cap to avoid 0 default
                self.divert_qty = (min(loaded, cap) if loaded > 0.0 and cap > 0.0 else (cap if cap > 0.0 else loaded))

    @api.onchange('ticket_id')
    def _onchange_ticket_id_update_remaining(self):
        """Keep Remaining to Complete in sync for UX; actual limits still enforced server-side."""
        self._compute_limits()
        try:
            self.remaining_to_complete = float(self.ticket_remaining_qty or 0.0)
        except Exception:
            pass

    @api.depends('ticket_id', 'ticket_id.rmc_quantity', 'truck_loading_id')
    def _compute_limits(self):
        def _sum_batches(domain):
            batches = self.env['rmc.batch'].sudo().search(domain)
            total = 0.0
            for b in batches:
                total += (b.quantity_produced or 0.0) or (b.quantity_ordered or 0.0)
            return total
        TL = self.env['rmc.truck_loading'].sudo()
        for wiz in self:
            # Ticket side
            ordered_t = float(wiz.ticket_id.rmc_quantity or 0.0)
            delivered_t = 0.0
            if wiz.ticket_id:
                try:
                    docket_ids = wiz.ticket_id.docket_ids.ids or []
                    if docket_ids:
                        tls = TL.search([('docket_id', 'in', docket_ids)])
                        if tls:
                            delivered_t = sum(float((tl.total_quantity or 0.0)) for tl in tls)
                    # If no dockets or none delivered via TLs, try via computed truck_loadings
                    if delivered_t <= 0.0 and wiz.ticket_id.truck_loading_ids:
                        delivered_t = sum(float((tl.total_quantity or 0.0)) for tl in wiz.ticket_id.truck_loading_ids)
                    # If still zero, fallback to batches linked directly to ticket
                    if delivered_t <= 0.0:
                        delivered_t = _sum_batches([('helpdesk_ticket_id', '=', wiz.ticket_id.id)])
                except Exception:
                    # Fallback to batches if any error
                    delivered_t = _sum_batches([('helpdesk_ticket_id', '=', wiz.ticket_id.id)])
            remaining_t = max(0.0, ordered_t - delivered_t)

            # Docket side (based on selected truck loading)
            docket = wiz.truck_loading_id.docket_id if wiz.truck_loading_id else False
            ordered_d = float(docket.quantity_ordered or 0.0) if docket else 0.0
            delivered_d = 0.0
            if docket:
                try:
                    tls_d = TL.search([('docket_id', '=', docket.id)])
                    if tls_d:
                        delivered_d = sum(float((tl.total_quantity or 0.0)) for tl in tls_d)
                    if delivered_d <= 0.0:
                        delivered_d = _sum_batches([('docket_id', '=', docket.id)])
                except Exception:
                    delivered_d = _sum_batches([('docket_id', '=', docket.id)])
            remaining_d = max(0.0, ordered_d - delivered_d)

            wiz.ticket_ordered_qty = ordered_t
            wiz.ticket_delivered_qty = delivered_t
            wiz.ticket_remaining_qty = remaining_t
            wiz.docket_ordered_qty = ordered_d
            wiz.docket_delivered_qty = delivered_d
            wiz.docket_remaining_qty = remaining_d
            wiz.max_divert_qty = min(remaining_t, remaining_d) if (remaining_t and remaining_d) else 0.0

    @api.onchange('truck_loading_id')
    def _onchange_truck_loading_id(self):
        """Propose divert quantity from the selected truck loading, capped by max_divert_qty."""
        if self.truck_loading_id:
            loaded = float(self.truck_loading_id.total_quantity or 0.0)
            # Ensure limits are up to date
            self._compute_limits()
            cap = float(self.max_divert_qty or 0.0)
            if self.plant_breakdown_mode:
                self.divert_qty = cap
            else:
                # Prefer loaded capped by remaining; if loaded is 0, fall back to cap to avoid 0 default
                self.divert_qty = (min(loaded, cap) if loaded > 0.0 and cap > 0.0 else (cap if cap > 0.0 else loaded))

    def action_divert(self):
        self.ensure_one()
        if not self.truck_loading_id:
            raise ValidationError(_('Please select a Truck Loading.'))
        # Determine effective target workorder if not explicitly provided
        target_workorder = self.target_workorder_id
        if not target_workorder:
            original_ticket = self.ticket_id.sudo()
            target_workorder = getattr(original_ticket, 'workorder_id', False)
            if not target_workorder and self.truck_loading_id and self.truck_loading_id.docket_id:
                target_workorder = getattr(self.truck_loading_id.docket_id, 'workorder_id', False)
        if not target_workorder:
            raise ValidationError(_('No target workorder found. Please select a Target Workorder or ensure the ticket/docket is linked to a workorder.'))
        # Quantity validations
        # Recompute limits to ensure up-to-date
        self._compute_limits()
        # If nothing remains to divert, raise an informative message before checking qty positivity
        if self.max_divert_qty <= 0.0:
            raise ValidationError(_('No remaining quantity is available to divert for this Ticket/Docket.'))
        if self.divert_qty <= 0.0:
            raise ValidationError(_('Please enter a positive Divert Quantity.'))
        if self.divert_qty - self.max_divert_qty > 1e-6:
            raise ValidationError(_(
                'Divert Quantity %.3f exceeds the allowed maximum %.3f (min of Ticket Remaining and Docket Remaining).'
            ) % (self.divert_qty, self.max_divert_qty))

        # Determine team and diverted stage for non-PB diversions (new ticket scenario)
        original_ticket = self.ticket_id.sudo()
        team = original_ticket.team_id or self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping', raise_if_not_found=False)
        new_helpdesk_ticket = False
        if not self.plant_breakdown_mode:
            diverted_stage = self.env.ref('rmc_management_system.helpdesk_stage_diverted_rmc', raise_if_not_found=False)
            if not diverted_stage or (team and team.id not in diverted_stage.team_ids.ids):
                domain = [('name', '=', 'Diverted')]
                if team:
                    domain.append(('team_ids', 'in', team.id))
                diverted_stage = self.env['helpdesk.stage'].sudo().search(domain, limit=1)
            if not diverted_stage and team:
                diverted_stage = self.env['helpdesk.stage'].sudo().create({
                    'name': 'Diverted',
                    'sequence': 35,
                    'team_ids': [(6, 0, [team.id])],
                })

            # Create a NEW helpdesk ticket for the diversion with a unique sequence-based name
            seq_name = self.env['ir.sequence'].next_by_code('rmc.divert.helpdesk.ticket') or _('Diverted Ticket')
            new_hd_vals = {
                'name': '%s - %s → %s' % (
                    seq_name,
                    original_ticket.name or original_ticket.id,
                    target_workorder.display_name,
                ),
                'description': _('Diverted from ticket %s to workorder %s. Truck Loading: %s') % (
                    original_ticket.display_name,
                    target_workorder.display_name,
                    self.truck_loading_id.display_name if self.truck_loading_id else '-',
                ),
                'partner_id': (self.new_site_id.id if self.new_site_id else original_ticket.partner_id.id),
                'team_id': team.id if team else False,
                'stage_id': diverted_stage.id if diverted_stage else False,
                'sale_order_id': getattr(target_workorder, 'sale_order_id', False) and target_workorder.sale_order_id.id or False,
                'priority': original_ticket.priority or '2',
                # Set the new ticket's quantity to the diverted portion
                'rmc_quantity': self.divert_qty,
            }
            # Include a snapshot of the original ticket's name
            new_hd_vals['diverted_from_ticket_name'] = original_ticket.display_name or original_ticket.name
            new_helpdesk_ticket = self.env['helpdesk.ticket'].sudo().create(new_hd_vals)
            # Set diversion linkage
            new_helpdesk_ticket.sudo().diverted_from_ticket_id = original_ticket.id
            # Store the last diverted child ticket name on the original ticket (snapshot)
            try:
                original_ticket.sudo().write({'last_diverted_ticket_name': new_helpdesk_ticket.display_name})
            except Exception:
                pass

        # create diversion workorder ticket on the target workorder and link to NEW helpdesk ticket
        new_ticket = self.env['dropshipping.workorder.ticket'].sudo().create({
            'workorder_id': target_workorder.id,
            'name': (_('PB Diversion from %s') if self.plant_breakdown_mode else _('Diverted from %s')) % (original_ticket.name or original_ticket.id),
            'quantity': self.divert_qty,
            'helpdesk_ticket_id': (original_ticket.id if self.plant_breakdown_mode else (new_helpdesk_ticket.id if new_helpdesk_ticket else False)),
            'state': 'assigned',
            'notes': _('Auto-created by %s diversion for helpdesk ticket %s') % (
                'PB' if self.plant_breakdown_mode else 'standard',
                original_ticket.name or original_ticket.id,
            ),
        })

        # PB mode: create a new docket on the same ticket, link to target workorder, and reassign this Truck Loading to it
        new_docket = False
        if self.plant_breakdown_mode and self.truck_loading_id and self.truck_loading_id.docket_id:
            src_docket = self.truck_loading_id.docket_id.sudo()
            # choose subcontractor: prefer new if provided, else original
            subc = self.new_subcontractor_id or src_docket.subcontractor_id
            # pick sale order from target workorder when available, else from source docket
            so = getattr(target_workorder, 'sale_order_id', False) or src_docket.sale_order_id
            # In PB mode, per business rule:
            # - Set the new docket's Quantity Ordered to the Workorder's ordered quantity
            # - Set the new docket's Quantity Produced to the Remaining (prefer Ticket Remaining)
            ordered_for_wo = float(getattr(target_workorder, 'quantity_ordered', 0.0) or 0.0)
            produced_remaining = float(getattr(self, 'ticket_remaining_qty', 0.0) or 0.0)
            new_docket_vals = {
                'sale_order_id': so.id if so else False,
                'helpdesk_ticket_id': original_ticket.id,
                'subcontractor_id': subc.id if subc else False,
                'recipe_id': src_docket.recipe_id.id if src_docket.recipe_id else False,
                'workorder_id': target_workorder.id,
                'subcontractor_plant_id': target_workorder.subcontractor_plant_id.id if target_workorder.subcontractor_plant_id else False,
                'quantity_ordered': ordered_for_wo,
                'quantity_produced': max(0.0, produced_remaining),
                'current_capacity': src_docket.current_capacity,
                'state': 'in_production',
                'notes': _('Auto-created by PB diversion from docket %s') % (src_docket.display_name),
            }
            try:
                new_docket = self.env['rmc.docket'].sudo().create(new_docket_vals)
                # Reassign the selected Truck Loading to new docket
                self.truck_loading_id.sudo().write({'docket_id': new_docket.id})
            except Exception:
                new_docket = False

        # find or create delivery_track by selected truck_loading
        track = self.env['rmc.delivery_track'].sudo().search([
            ('truck_loading_id', '=', self.truck_loading_id.id)
        ], limit=1)
        if not track:
            track = self.env['rmc.delivery_track'].sudo().create({
                'helpdesk_ticket_id': (original_ticket.id if self.plant_breakdown_mode else (new_helpdesk_ticket.id if new_helpdesk_ticket else False)),
                'truck_loading_id': self.truck_loading_id.id,
                'workorder_id': target_workorder.id,
                'new_site_id': self.new_site_id.id if self.new_site_id else False,
                'workorder_ticket_id': new_ticket.id,
            })
        else:
            # ensure truck loading is linked
            if not track.truck_loading_id:
                track.sudo().truck_loading_id = self.truck_loading_id.id
            track.sudo().action_divert_to_workorder(target_workorder)
            track.sudo().workorder_ticket_id = new_ticket.id
            if self.new_site_id:
                track.sudo().new_site_id = self.new_site_id.id
        
        # Update original helpdesk ticket flags only (don't change its stage now)
        original_ticket.write({'assigned_subcontractor_id': False})

        # Auto-update Delivery Variance against this Truck Loading: set diverted True and destination partner
        try:
            dv = self.env['rmc.delivery_variance'].sudo().search([
                ('truck_loading_id', '=', self.truck_loading_id.id)
            ], limit=1)
            if dv:
                dv.write({
                    'diverted': True,
                    'divert_to_partner_id': ((self.new_site_id.id if self.new_site_id else original_ticket.partner_id.id) if self.plant_breakdown_mode else (new_helpdesk_ticket.partner_id.id if new_helpdesk_ticket else False)),
                    'diverted_qty': self.divert_qty,
                })
                # Also create a new Delivery Variance record for the diverted customer with same references
                if not self.plant_breakdown_mode and new_helpdesk_ticket:
                    self.env['rmc.delivery_variance'].sudo().create({
                        'truck_loading_id': self.truck_loading_id.id,
                        'diverted': True,
                        'divert_to_partner_id': new_helpdesk_ticket.partner_id.id or False,
                        'diverted_qty': self.divert_qty,
                        'notes': _('Auto-created by diversion from ticket %s to %s') % (
                            original_ticket.display_name,
                            new_helpdesk_ticket.display_name,
                        ),
                    })
        except Exception:
            pass

        # Log diversion on both tickets for traceability
        try:
            if self.plant_breakdown_mode:
                msg_orig = _(
                    'PB Diversion of %.3f M3 to Workorder: %s (ID %s). Truck Loading: %s. Workorder Ticket ID: %s.%s'
                ) % (
                    self.divert_qty,
                    target_workorder.display_name,
                    target_workorder.id,
                    self.truck_loading_id.display_name if self.truck_loading_id else '-',
                    new_ticket.id,
                    ((' New Docket: %s (ID %s).' % (new_docket.display_name, new_docket.id)) if new_docket else ''),
                )
                original_ticket.message_post(body=msg_orig)
            else:
                msg_orig = _(
                    'Diverted %.3f M3 to Workorder: %s (ID %s). Truck Loading: %s. New Helpdesk Ticket: %s (ID %s). Created Workorder Ticket ID: %s.'
                ) % (
                    self.divert_qty,
                    target_workorder.display_name,
                    target_workorder.id,
                    self.truck_loading_id.display_name if self.truck_loading_id else '-',
                    new_helpdesk_ticket.display_name,
                    new_helpdesk_ticket.id,
                    new_ticket.id,
                )
                original_ticket.message_post(body=msg_orig)

                msg_new = _(
                    'Created by diversion of %.3f M3 from Helpdesk Ticket: %s (ID %s). Target Workorder: %s (ID %s). Truck Loading: %s. Linked Workorder Ticket ID: %s.'
                ) % (
                    self.divert_qty,
                    original_ticket.display_name,
                    original_ticket.id,
                    target_workorder.display_name,
                    target_workorder.id,
                    self.truck_loading_id.display_name if self.truck_loading_id else '-',
                    new_ticket.id,
                )
                new_helpdesk_ticket.message_post(body=msg_new)
        except Exception:
            # Non-blocking if chatter not available or other issues
            pass
        # In standard divert, move loaded batches to the new ticket; in PB mode, keep them with the original
        if not self.plant_breakdown_mode:
            try:
                if self.truck_loading_id and self.truck_loading_id.batch_ids:
                    self.truck_loading_id.batch_ids.sudo().write({'helpdesk_ticket_id': new_helpdesk_ticket.id})
            except Exception:
                pass
        # Move the original helpdesk ticket to a 'Failed' stage only in standard diversion, not in PB mode
        if not self.plant_breakdown_mode:
            try:
                fail_stage = self.env['helpdesk.stage'].sudo().search([
                    ('name', '=', 'Failed'),
                    ('team_ids', 'in', team.id) if team else (1, '=', 1),
                ], limit=1)
                if not fail_stage:
                    vals = {'name': 'Failed', 'sequence': 90}
                    if team:
                        vals['team_ids'] = [(6, 0, [team.id])]
                    fail_stage = self.env['helpdesk.stage'].sudo().create(vals)
                original_ticket.sudo().write({'stage_id': fail_stage.id})
            except Exception:
                pass
        return {'type': 'ir.actions.client', 'tag': 'reload'}
