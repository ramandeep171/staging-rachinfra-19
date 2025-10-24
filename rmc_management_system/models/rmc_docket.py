from odoo import models, fields, api, _
from math import ceil
import random
import re
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta


class RmcDocket(models.Model):
    _name = 'rmc.docket'
    _description = 'RMC Docket Production'
    _order = 'docket_date desc, docket_number desc'

    name = fields.Char(string='Docket Reference', required=True, copy=False, readonly=True, default='New')
    # Not required: when created from Helpdesk Ticket, we intentionally leave this blank
    docket_number = fields.Char(string='Docket Number', required=False)
    docket_date = fields.Datetime(string='Docket Date', required=True, default=fields.Datetime.now)
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket')
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor')    
    recipe_id = fields.Many2one('mrp.bom', string="Recipe", domain=lambda self: self._get_recipe_domain())
    concrete_grade = fields.Char(string='Concrete Grade', compute='_compute_concrete_grade', store=True)
    
    # Product information
    product_id = fields.Many2one('product.product', string='Product', compute='_compute_product', store=True)
    is_rmc_product = fields.Boolean(string='Is RMC Product', compute='_compute_is_rmc_product', store=True)
    # Link to Workorder and show its tickets
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder', domain="[('sale_order_id','=',sale_order_id)]",
                                   help='Workorder for this docket (filtered by Sale Order)')
    workorder_ticket_ids = fields.One2many(related='workorder_id.ticket_ids', string='Workorder Tickets', readonly=True)
    
    quantity_ordered = fields.Float(string='Quantity Ordered (M3)', required=True)
    quantity_produced = fields.Float(string='Quantity Produced (M3)')
    cumulative_quantity = fields.Float(string='Cumulative Quantity (M3)')
    # Ticket Quantity snapshot for reference
    quantity_ticket = fields.Float(string='Ticket Quantity (M3)', compute='_compute_quantity_ticket', store=True)
    
    # Production Details
    pour_structure = fields.Selection([
        ('rcc', 'RCC'),
        ('pcc', 'PCC'),
        ('foundation', 'Foundation'),
        ('slab', 'Slab'),
        ('beam', 'Beam'),
        ('column', 'Column'),
    ], string='Pour Structure', default='rcc')
    
    batching_time = fields.Datetime(string='Batching Time')
    water_ratio_actual = fields.Float(string='Actual Water Ratio')
    slump_flow_actual = fields.Float(string='Actual Slump/Flow (mm)')
    # Additional runtime fields
    current_capacity = fields.Float(string='Current Capacity (M3/batch)')
    tm_number = fields.Char(string='TM Number')
    driver_name = fields.Char(string='Driver Name')
    subcontractor_transport_id = fields.Many2one('rmc.subcontractor.transport', string='Transport')
    subcontractor_plant_id = fields.Many2one(
        'rmc.subcontractor.plant',
        string='Plant',
        help='Origin plant for this docket; drives operator portal visibility.'
    )
    # Relations
    truck_loading_ids = fields.One2many('rmc.truck_loading', 'docket_id', string='Truck Loadings')
    plant_check_ids = fields.One2many('rmc.plant_check', 'docket_id', string='Plant Checks')
    # docket_batch_ids = fields.One2many('rmc.batch', 'docket_id', string='Batches')
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    # Smart button counts
    truck_loading_count = fields.Integer(string='Truck Loadings', compute='_compute_counts', store=False)
    plant_check_count = fields.Integer(string='Plant Checks', compute='_compute_counts', store=False)
    docket_batch_count = fields.Integer(string='Batches', compute='_compute_counts', store=False)
    vendor_bill_count = fields.Integer(string='Vendor Bills', compute='_compute_counts', store=False)
    invoice_count = fields.Integer(string='Customer Invoices', compute='_compute_counts', store=False)
    has_truck_loading = fields.Boolean(string='Has Truck Loading', compute='_compute_has_truck_loading', store=True)
    
    # Current active truck loading and plant check
    # current_truck_loading_id = fields.Many2one('rmc.truck_loading', string='Current Truck Loading', 
    #                                            compute='_compute_current_truck_loading', store=True)
    current_plant_check_id = fields.Many2one('rmc.plant_check', string='Current Plant Check',
                                             compute='_compute_current_plant_check', store=True)
    
    # Docket Lines
    docket_line_ids = fields.One2many('rmc.docket.line', 'docket_id', string='Docket Lines')
    docket_batch_ids = fields.One2many('rmc.docket.batch', 'docket_id', string='Batches')
    batch_variance_tolerance = fields.Float(string='Batch Variance Tolerance (%)', default=2.0)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_production', 'In Production'),
        ('ready', 'Ready'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')

    notes = fields.Text(string='Notes')
    active = fields.Boolean(string='Active', default=True)
    operator_user_id = fields.Many2one('res.users', string='Operator User', compute='_compute_operator_user', store=True, readonly=False)
    operator_portal_status = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], string='Operator Status', default='pending', tracking=True)
    operator_completion_time = fields.Datetime(string='Operator Completion Time')
    operator_notes = fields.Text(string='Operator Notes')
    operator_day_report_id = fields.Many2one('rmc.operator.day.report', string='Day Report')

    # --- State automation ---
    @api.onchange('docket_number')
    def _onchange_docket_number_set_in_production(self):
        """When a docket number is provided on a draft docket, move it to In Production.
        We do not auto-revert if the number is cleared.
        """
        for rec in self:
            try:
                if rec.docket_number and rec.state == 'draft':
                    rec.state = 'in_production'
            except Exception:
                # Non-blocking in UI
                pass

    def _compute_counts(self):
        for rec in self:
            rec.truck_loading_count = len(rec.truck_loading_ids)
            rec.plant_check_count = len(rec.plant_check_ids)
            rec.docket_batch_count = len(rec.docket_batch_ids)
            rec.invoice_count = 1 if rec.invoice_id else 0
            # Vendor bills linked via workorder name as invoice_origin
            if rec.workorder_id:
                rec.vendor_bill_count = self.env['account.move'].search_count([
                    ('move_type', '=', 'in_invoice'),
                    ('invoice_origin', 'ilike', rec.workorder_id.name or ''),
                ])
            else:
                rec.vendor_bill_count = 0

    @api.depends('truck_loading_ids')
    def _compute_(self):
        for rec in self:
            rec.has_truck_loading = bool(rec.truck_loading_ids)

    # Smart button actions
    def action_open_truck_loadings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Truck Loadings',
            'res_model': 'rmc.truck_loading',
            'view_mode': 'list,form',
            'domain': [('docket_id', '=', self.id)],
        }

    @api.depends(
        'subcontractor_transport_id.plant_id.operator_user_id',
        'subcontractor_plant_id.operator_user_id',
    )
    def _compute_operator_user(self):
        for docket in self:
            operator_user = docket.subcontractor_transport_id.plant_id.operator_user_id or docket.subcontractor_plant_id.operator_user_id
            docket.operator_user_id = operator_user.id if operator_user else False

    def action_operator_set_status(self, status, notes=None):
        allowed = {'pending', 'in_progress', 'completed'}
        if status not in allowed:
            raise ValidationError(_('Invalid operator status.'))
        values = {'operator_portal_status': status}
        if status == 'completed':
            values['operator_completion_time'] = fields.Datetime.now()
        if notes is not None:
            values['operator_notes'] = notes
        self.write(values)


    @api.depends('helpdesk_ticket_id', 'helpdesk_ticket_id.rmc_quantity')
    def _compute_quantity_ticket(self):
        for rec in self:
            rec.quantity_ticket = float(rec.helpdesk_ticket_id.rmc_quantity or 0.0)

    @api.depends('recipe_id', 'product_id', 'sale_order_id', 'sale_order_id.order_line.product_id', 'sale_order_id.order_line.name')
    def _compute_concrete_grade(self):
        """Derive a human-friendly concrete grade.

        Precedence:
        1) Explicit concrete_grade on recipe/product template if present.
        2) Parse an "Mxx" token from recipe name, product name, or SO line name.
        3) Fallback to recipe display name or empty string.
        """
        pattern = re.compile(r"M\s*\d+", re.IGNORECASE)
        for rec in self:
            grade = False
            # 1) From recipe
            if rec.recipe_id:
                grade = getattr(rec.recipe_id, 'concrete_grade', False)
                if not grade:
                    m = pattern.search(rec.recipe_id.display_name or '')
                    if m:
                        grade = m.group(0).replace(' ', '').upper()
            # 2) From product template or SO lines
            if not grade:
                tmpl = rec.product_id.product_tmpl_id if rec.product_id else False
                grade = getattr(tmpl, 'concrete_grade', False) if tmpl else False
            if not grade and rec.product_id:
                m = pattern.search((rec.product_id.display_name or '') + ' ' + (rec.product_id.name or ''))
                if m:
                    grade = m.group(0).replace(' ', '').upper()
            if not grade and rec.sale_order_id and rec.sale_order_id.order_line:
                # look across lines for an Mxx marker in product or line name
                for line in rec.sale_order_id.order_line:
                    src = ((line.product_id and line.product_id.display_name) or '') + ' ' + (line.name or '')
                    m = pattern.search(src)
                    if m:
                        grade = m.group(0).replace(' ', '').upper()
                        break
            # 3) Fallback to recipe display name, else empty
            if not grade and rec.recipe_id:
                grade = rec.recipe_id.display_name
            rec.concrete_grade = grade or ''

    

    # --- Transport → Truck Loading automation ---
    def _ensure_truck_loading_for_transport(self):
        """Ensure there is at least one Truck Loading for the selected subcontractor transport.
        If none exists for (docket, transport), create a scheduled loading and link the fleet vehicle.
        """
        TL = self.env['rmc.truck_loading']
        for rec in self:
            transport = rec.subcontractor_transport_id
            if not transport:
                continue
            # Skip if a loading for this (docket, transport) already exists
            existing = TL.search([
                ('docket_id', '=', rec.id),
                ('subcontractor_transport_id', '=', transport.id),
            ], limit=1)
            if existing:
                continue
            # Ensure we have a fleet vehicle for this transport
            vehicle = transport.fleet_vehicle_id
            if not vehicle and hasattr(transport, '_create_fleet_vehicle'):
                try:
                    transport._create_fleet_vehicle()
                    vehicle = transport.fleet_vehicle_id
                except Exception:
                    vehicle = False
            if not vehicle:
                # Cannot create loading without a vehicle (required field)
                continue
            vals = {
                'docket_id': rec.id,
                'subcontractor_transport_id': transport.id,
                'vehicle_id': vehicle.id,
                'loading_status': 'scheduled',
            }
            try:
                TL.create(vals)
            except Exception:
                # Non-blocking
                pass

    def action_open_plant_checks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Plant Checks',
            'res_model': 'rmc.plant_check',
            'view_mode': 'list,form',
            'domain': [('docket_id', '=', self.id)],
        }

    def action_open_docket_batches(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Docket Batches',
            'res_model': 'rmc.docket.batch',
            'view_mode': 'list,form',
            'domain': [('docket_id', '=', self.id)],
        }

    def action_open_customer_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Customer Invoice',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_vendor_bills(self):
        self.ensure_one()
        domain = [('move_type', '=', 'in_invoice')]
        if self.workorder_id and self.workorder_id.name:
            domain.append(('invoice_origin', 'ilike', self.workorder_id.name))
        else:
            domain.append(('id', '=', 0))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bills',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'search_default_posted': 1},
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('rmc.docket') or 'New'
            # If a docket number is provided at creation and state not explicitly set, start In Production
            if vals.get('docket_number') and not vals.get('state'):
                vals['state'] = 'in_production'
            if not vals.get('subcontractor_plant_id'):
                plant_id = False
                if vals.get('subcontractor_transport_id'):
                    transport = self.env['rmc.subcontractor.transport'].browse(vals['subcontractor_transport_id'])
                    plant_id = transport.plant_id.id
                if not plant_id and vals.get('workorder_id'):
                    workorder = self.env['dropshipping.workorder'].browse(vals['workorder_id'])
                    plant_id = workorder.subcontractor_plant_id.id
                if plant_id:
                    vals['subcontractor_plant_id'] = plant_id
        records = super(RmcDocket, self).create(vals_list)
        # Create a Truck Loading automatically if transport is already set
        try:
            records._ensure_truck_loading_for_transport()
        except Exception:
            pass
        # Ensure recipe-based lines are populated if recipe is set programmatically
        for rec in records:
            if rec.recipe_id and not rec.docket_line_ids:
                rec._apply_recipe_lines()
        # Auto-batch if capacity present
        for rec in records:
            try:
                if rec.current_capacity:
                    rec._generate_batches()
            except Exception:
                # Non-blocking; log in server log if needed
                pass
        # Trigger cube tests per docket depending on sale order setting
        for docket in records:
            so = docket.sale_order_id
            if not so or not so.is_rmc_order or not so.cube_test_condition:
                continue
            cond = so.cube_test_condition
            if cond == 'every_truck':
                docket._trigger_cube_tests_for_docket(cond)
            elif cond == 'every_six':
                # Count dockets for this Workorder (fallback to SO) and trigger on each 6th
                if docket.workorder_id:
                    count = self.search_count([('workorder_id', '=', docket.workorder_id.id)])
                else:
                    count = self.search_count([('sale_order_id', '=', so.id)])
                if count % 6 == 0:
                    docket._trigger_cube_tests_for_docket(cond)
        return records

    def write(self, vals):
        """Guard to move to In Production when docket_number gets its first value while in draft.
        Avoid overriding explicit state changes.
        """
        res = super(RmcDocket, self).write(vals)
        if not self.env.context.get('skip_auto_plant'):
            should_sync = 'subcontractor_transport_id' in vals or ('workorder_id' in vals and 'subcontractor_plant_id' not in vals)
            if should_sync:
                for rec in self:
                    plant = rec.subcontractor_transport_id.plant_id or rec.workorder_id.subcontractor_plant_id
                    if plant and rec.subcontractor_plant_id != plant:
                        rec.with_context(skip_auto_plant=True).write({'subcontractor_plant_id': plant.id})
        if 'docket_number' in vals and vals.get('docket_number'):
            for rec in self:
                try:
                    # Only auto-advance from draft if state wasn't explicitly changed in this write
                    if rec.state == 'draft' and 'state' not in vals:
                        rec.state = 'in_production'
                except Exception:
                    # Non-blocking
                    pass
        # If transport has been set/changed, ensure a truck loading exists for it
        if 'subcontractor_transport_id' in vals and vals.get('subcontractor_transport_id'):
            try:
                self._ensure_truck_loading_for_transport()
            except Exception:
                pass
        # If state moved to in_production, auto-start truck loading (if exists) or create+start
        if 'state' in vals and vals.get('state') == 'in_production':
            for rec in self:
                try:
                    # Ensure a truck loading exists
                    rec._ensure_truck_loading_for_transport()
                    # Start the first applicable loading
                    tl = self.env['rmc.truck_loading'].search([
                        ('docket_id', '=', rec.id),
                        ('loading_status', 'in', ['scheduled', 'in_progress'])
                    ], limit=1)
                    if tl and tl.loading_status == 'scheduled':
                        tl.action_start_loading()
                except Exception:
                    pass
        # If state moved to ready, complete the truck loading
        if 'state' in vals and vals.get('state') == 'ready':
            for rec in self:
                try:
                    tl = self.env['rmc.truck_loading'].search([
                        ('docket_id', '=', rec.id),
                        ('loading_status', 'in', ['scheduled', 'in_progress'])
                    ], limit=1)
                    if tl:
                        if tl.loading_status == 'scheduled':
                            tl.action_start_loading()
                        tl.action_complete_loading()
                except Exception:
                    pass

        # Backfill Ticket Quantity if empty based on docket quantities
        try:
            if any(k in vals for k in ['quantity_ordered', 'quantity_produced']):
                for rec in self:
                    ticket = rec.helpdesk_ticket_id
                    if ticket and not ticket.rmc_quantity:
                        qty = rec.quantity_ordered or rec.quantity_produced or 0.0
                        if qty:
                            ticket.rmc_quantity = qty
        except Exception:
            pass
        return res

    # Button to set manufacturing ready and complete truck loading
    def action_manufacturing_ready(self):
        for rec in self:
            # Set docket state to ready
            if rec.state != 'ready':
                rec.state = 'ready'
            # Complete any in-progress truck loading
            tl = self.env['rmc.truck_loading'].search([
                ('docket_id', '=', rec.id),
                ('loading_status', 'in', ['scheduled', 'in_progress'])
            ], limit=1)
            if tl:
                try:
                    # If still scheduled, start then complete to stamp times
                    if tl.loading_status == 'scheduled':
                        tl.action_start_loading()
                    tl.action_complete_loading()
                except Exception:
                    pass
        return True

    def _trigger_cube_tests_for_docket(self, condition):
        self.ensure_one()
        if not self.sale_order_id:
            return False
        qc_model = self.env['quality.cube.test']
        today = fields.Date.context_today(self)
        # Always create separate 7-day and 28-day tests per trigger event
        qc_model.create({
            'sale_order_id': self.sale_order_id.id,
            'test_condition': condition,
            'cubes_per_test': 3,
            'casting_date': today,
            'day_type': '7',
            'docket_id': self.id,
            'workorder_id': self.workorder_id.id,
            'user_id': self.sale_order_id.cube_test_user_id.id,
            'notes': self.sale_order_id.cube_test_notes,
        })
        qc_model.create({
            'sale_order_id': self.sale_order_id.id,
            'test_condition': condition,
            'cubes_per_test': 3,
            'casting_date': today,
            'day_type': '28',
            'docket_id': self.id,
            'workorder_id': self.workorder_id.id,
            'user_id': self.sale_order_id.cube_test_user_id.id,
            'notes': self.sale_order_id.cube_test_notes,
        })
        return True

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id_set_workorder(self):
        """When sale order changes, clear or auto-select workorder limited to that SO."""
        if self.sale_order_id:
            # Auto select if exactly one workorder exists for this SO
            wos = self.env['dropshipping.workorder'].search([('sale_order_id', '=', self.sale_order_id.id)], limit=2)
            if len(wos) == 1:
                self.workorder_id = wos[0].id
            elif self.workorder_id and self.workorder_id.sale_order_id != self.sale_order_id:
                self.workorder_id = False
        else:
            self.workorder_id = False

    def _get_recipe_domain(self):
        """Dynamic domain for recipe_id based on subcontractor and plant"""
        domain = []
        if self.subcontractor_id:
            domain.append(('subcontractor_id', '=', self.subcontractor_id.partner_id.id))
        if self.subcontractor_id and self.subcontractor_id.plant_code:
            domain.append(('plant_code', '=', self.subcontractor_id.plant_code))
        return domain

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_id(self):
        """Update recipe domain when subcontractor changes"""
        if self.subcontractor_id:
            return {'domain': {'recipe_id': self._get_recipe_domain()}}
        else:
            return {'domain': {'recipe_id': []}}

    @api.onchange('recipe_id')
    def _onchange_recipe_id(self):
        self._apply_recipe_lines()

    def _apply_recipe_lines(self):
        """Replace docket lines with the recipe's BOM lines. Safe to call on create/write/onchange."""
        for rec in self:
            if not rec.recipe_id:
                continue
            lines = [(5, 0, 0)]
            for bom_line in rec.recipe_id.bom_line_ids:
                lines.append((0, 0, {
                    'material_name': bom_line.product_id.name,
                    'material_code': getattr(bom_line, 'product_code', False) or bom_line.product_id.default_code,
                    'design_qty': bom_line.product_qty,
                }))
            rec.docket_line_ids = lines

    

    def write(self, vals):
        res = super(RmcDocket, self).write(vals)
        if 'recipe_id' in vals:
            # Re-apply lines when recipe changed programmatically
            self._apply_recipe_lines()
        return res

    def _generate_batches(self):
        """Generate rmc.docket.batch records based on quantity_ordered and current_capacity.

        Algorithm:
        - total_qty = quantity_ordered
        - batch_capacity = current_capacity
        - n = ceil(total_qty / batch_capacity)
        - delete existing batches for this docket
        - for i in 1..n-1: create batch with volume = batch_capacity +/- variance
        - last batch volume = remaining to ensure totals exact
        - for each recipe line, compute per-batch material = per_cum_qty * batch_volume
        - apply variance percent from field batch_variance_tolerance (default 2%)
        """
        for rec in self:
            total_qty = float(rec.quantity_ordered or 0.0)
            batch_capacity = float(rec.current_capacity or 0.0)
            tol_pct = float(rec.batch_variance_tolerance or 2.0) / 100.0

            if total_qty <= 0:
                continue
            if batch_capacity <= 0:
                raise UserError(_('Batch capacity must be set and greater than zero to generate batches.'))

            num_batches = int(ceil(total_qty / batch_capacity))

            # gather recipe lines: prefer docket_line_ids (per-cum), else use recipe_id.bom_line_ids
            recipe_lines = []
            if rec.docket_line_ids:
                for line in rec.docket_line_ids:
                    recipe_lines.append({
                        'name': line.material_name or (line.material_code or ''),
                        'product_id': False,
                        'per_cum_qty': float(line.design_qty or 0.0),
                    })
            elif rec.recipe_id:
                for bl in rec.recipe_id.bom_line_ids:
                    recipe_lines.append({
                        'name': bl.product_id.name,
                        'product_id': bl.product_id.id,
                        'per_cum_qty': float(bl.product_qty or 0.0),
                    })
            else:
                raise UserError(_('No recipe found on the docket. Please set a recipe or docket lines before generating batches.'))

            # compute total material expected per product (for exact balancing)
            total_materials = {}
            for rl in recipe_lines:
                total_materials[rl.get('name')] = total_materials.get(rl.get('name'), 0.0) + rl.get('per_cum_qty', 0.0) * total_qty

            # remove existing batches for this docket
            existing = self.env['rmc.docket.batch'].search([('docket_id', '=', rec.id)])
            if existing:
                existing.unlink()

            created_batches = []
            volumes = []

            # For first n-1 batches apply variance
            for i in range(1, num_batches + 1):
                if i < num_batches:
                    # variance factor in [1 - tol, 1 + tol]
                    var_factor = 1.0 + random.uniform(-tol_pct, tol_pct) if tol_pct > 0 else 1.0
                    vol = batch_capacity * var_factor
                    # don't exceed remaining total drastically; cap to reasonable
                    if vol <= 0:
                        vol = batch_capacity
                    volumes.append(vol)
                else:
                    # placeholder for last batch, compute later
                    volumes.append(0.0)

            # compute last batch as remainder to make exact total
            sum_prev = sum(volumes[:-1]) if len(volumes) > 1 else 0.0
            last_vol = max(0.0, total_qty - sum_prev)
            # if last_vol is zero (due to rounding), set to batch_capacity
            if last_vol <= 0:
                last_vol = batch_capacity
            volumes[-1] = last_vol

            # If due to randomness sum exceeds total_qty, scale down proportionally
            total_vol_sum = sum(volumes)
            if total_vol_sum != total_qty and total_vol_sum > 0:
                scale = total_qty / total_vol_sum
                volumes = [v * scale for v in volumes]

            # For material quantities per batch, compute using per_cum_qty * vol; keep running sums to ensure exact last-batch balancing
            material_running = {k: 0.0 for k in total_materials.keys()}

            for idx, vol in enumerate(volumes, start=1):
                batch_vals = {
                    'docket_id': rec.id,
                    'batch_code': 'Batch-%03d' % idx,
                    'batch_id': str(idx),
                }

                # compute per-material qty for this batch
                mat_values_for_fields = {
                    'ten_mm': 0.0,
                    'twenty_mm': 0.0,
                    'facs': 0.0,
                    'water_batch': 0.0,
                    'flyash': 0.0,
                    'adm_plast': 0.0,
                    'WATERR': 0.0,
                }

                # accumulate material quantities
                for rl in recipe_lines:
                    name = rl.get('name')
                    per_cum = rl.get('per_cum_qty', 0.0)
                    qty = per_cum * vol

                    # For last batch, adjust to exact remaining for this material
                    if idx == num_batches:
                        remaining = total_materials.get(name, 0.0) - material_running.get(name, 0.0)
                        qty = remaining

                    material_running[name] = material_running.get(name, 0.0) + qty

                    lname = (name or '').lower()
                    # naive mapping by name keywords
                    if '10' in lname or '10mm' in lname or 'ca10' in lname or 'ca10mm' in lname:
                        mat_values_for_fields['ten_mm'] += qty
                    elif '20' in lname or '20mm' in lname or 'ca20' in lname or 'ca20mm' in lname:
                        mat_values_for_fields['twenty_mm'] += qty
                    elif 'fly' in lname or 'flyash' in lname:
                        mat_values_for_fields['flyash'] += qty
                    elif 'water' in lname or 'waterr' in lname:
                        mat_values_for_fields['WATERR'] += qty
                    elif 'adm' in lname or 'admix' in lname or 'admixture' in lname:
                        mat_values_for_fields['adm_plast'] += qty
                    elif 'fac' in lname or 'facs' in lname:
                        mat_values_for_fields['facs'] += qty
                    else:
                        # default map to facs if unknown
                        mat_values_for_fields['facs'] += qty

                # set batch material fields
                batch_vals.update(mat_values_for_fields)
                batch_vals['quantity_ordered'] = vol
                batch = self.env['rmc.docket.batch'].create(batch_vals)
                created_batches.append(batch)

            # link created batches to docket via relation (already set by docket_id)
            return created_batches

    def action_generate_batches(self):
        """Button wrapper to generate batches from the UI."""
        return self._generate_batches()

    @api.depends('name')
    def _compute_totals(self):
        for record in self:
            # Get batches related to this docket
            try:
                batches = self.env['rmc.batch'].search([('docket_id', '=', record.id)])
            except ValueError:
                # If docket_id field doesn't exist, return empty
                batches = self.env['rmc.batch']
            
            record.total_ten_mm = sum(batch.ten_mm for batch in batches)
            record.total_twenty_mm = sum(batch.twenty_mm for batch in batches)
            record.total_facs = sum(batch.facs for batch in batches)
            record.total_water_batch = sum(batch.water_batch for batch in batches)
            record.total_flyash = sum(batch.flyash for batch in batches)
            record.total_adm_plast = sum(batch.adm_plast for batch in batches)
            record.total_waterr = sum(batch.WATERR for batch in batches)

    @api.depends('sale_order_id')
    def _compute_product(self):
        for record in self:
            if record.sale_order_id and record.sale_order_id.order_line:
                # Get the first product from sale order lines (assuming single product per docket)
                record.product_id = record.sale_order_id.order_line[0].product_id
            else:
                record.product_id = False

    @api.depends('sale_order_id.order_line.product_id')
    def _compute_is_rmc_product(self):
        for record in self:
            if record.sale_order_id and record.sale_order_id.order_line:
                record.is_rmc_product = any(line.product_id.product_tmpl_id.is_rmc_product for line in record.sale_order_id.order_line if line.product_id)
            else:
                record.is_rmc_product = False

    # @api.depends('truck_loading_ids.loading_status')
    # def _compute_current_truck_loading(self):
    #     for record in self:
    #         # Get the most recent truck loading that is not completed or cancelled
    #         try:
    #             active_loading = self.env['rmc.truck_loading'].search([
    #                 ('docket_id', '=', record.id),
    #                 ('loading_status', 'in', ['scheduled', 'in_progress'])
    #             ], limit=1, order='loading_date desc')
    #         except ValueError:
    #             active_loading = False
    #         
    #         record.current_truck_loading_id = active_loading

    @api.depends('plant_check_ids.check_status')
    def _compute_current_plant_check(self):
        for record in self:
            # Get the most recent plant check that is in progress
            try:
                active_check = self.env['rmc.plant_check'].search([
                    ('docket_id', '=', record.id),
                    ('check_status', '=', 'in_progress')
                ], limit=1, order='check_date desc')
            except ValueError:
                active_check = False
            
            record.current_plant_check_id = active_check

    def action_create_truck_loading(self):
        """Create a new truck loading for this docket"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Truck Loading',
            'res_model': 'rmc.truck_loading',
            'view_mode': 'form',
            'context': {
                'default_docket_id': self.id,
                'default_vehicle_id': self.env.context.get('default_vehicle_id'),
            },
            'target': 'new',
        }

    def action_generate_invoice(self):
        """Generate invoice for completed plant check"""
        self.ensure_one()

        # Check if there's a completed plant check
        completed_checks = self.plant_check_ids.filtered(lambda pc: pc.check_status == 'completed')
        if not completed_checks:
            raise ValidationError(_("No completed plant checks found for this docket."))

        # Create invoice based on the latest completed plant check
        latest_check = completed_checks[0]  # Already ordered by check_date desc

        invoice_vals = {
            'partner_id': self.sale_order_id.partner_id.id if self.sale_order_id else self.env.user.company_id.partner_id.id,
            'move_type': 'out_invoice',
            'invoice_date': fields.Date.today(),
            'docket_id': self.id,
            'plant_check_id': latest_check.id,
        }
        invoice = self.env['account.move'].create(invoice_vals)

        # Store the invoice reference
        self.invoice_id = invoice.id

        # Add invoice line: product from Sale Order; quantity from Ticket
        # 1) Pick SO line/product to invoice
        sol_line = False
        if self.sale_order_id and self.sale_order_id.order_line:
            # Prefer a line whose product is marked RMC or in RMC/Concrete category
            rmc_lines = self.sale_order_id.order_line.filtered(lambda l: l.product_id and (
                getattr(l.product_id.categ_id, 'is_rmc_category', False)
                or ('RMC' in (l.product_id.categ_id.name or '').upper())
                or ('CONCRETE' in (l.product_id.categ_id.name or '').upper())
                or getattr(l.product_id.product_tmpl_id, 'is_rmc_product', False)
            ))
            sol_line = rmc_lines[:1] or self.sale_order_id.order_line[:1]
            sol_line = sol_line and sol_line[0] or False

        product_id = sol_line.product_id.id if sol_line else (self.product_id.id if self.product_id else False)
        price_unit = sol_line.price_unit if sol_line else (self.sale_order_id.order_line[0].price_unit if (self.sale_order_id and self.sale_order_id.order_line) else 0)

        # 2) Derive quantity from Ticket; fallback to docket or plant check
        ticket_qty = 0.0
        # Prefer tickets linked to this helpdesk ticket (if any)
        try:
            tickets = self.helpdesk_ticket_id.workorder_ticket_ids if self.helpdesk_ticket_id else False
        except Exception:
            tickets = False
        if not tickets and self.workorder_id:
            # fallback to workorder tickets
            tickets = self.workorder_id.ticket_ids
        if tickets:
            # Prefer completed/in_progress ticket, else any
            preferred = tickets.filtered(lambda t: t.state in ('completed', 'in_progress')) or tickets
            # Choose most recent by id (avoid datetime ops for robustness)
            ticket = sorted(preferred, key=lambda t: t.id, reverse=True)[0]
            ticket_qty = ticket.quantity or 0.0

        quantity = ticket_qty or (self.quantity_ordered or 0.0) or (latest_check.net_weight / 1000.0)

        if sol_line and sol_line.name:
            line_name = sol_line.name
        elif product_id:
            product = self.env['product.product'].browse(product_id)
            line_name = product.display_name or product.name or _('RMC Supply')
        else:
            line_name = _('RMC Supply')
        if self.docket_number:
            line_name = _('%s (Docket %s)') % (line_name, self.docket_number)

        invoice_line_vals = {
            'move_id': invoice.id,
            'product_id': product_id,
            'quantity': quantity,
            'price_unit': price_unit,
            'name': line_name,
        }
        # If product is missing for any reason, keep behavior robust: don't set product_id, rely on name/price
        if not product_id:
            invoice_line_vals.pop('product_id', None)
        self.env['account.move.line'].create(invoice_line_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }


class RmcDocketLine(models.Model):
    _name = 'rmc.docket.line'
    _description = 'RMC Docket Line'

    docket_id = fields.Many2one('rmc.docket', string='Docket', required=True, ondelete='cascade')
    material_name = fields.Char(string='Material Name')
    material_code = fields.Char(string='Material Code')
    design_qty = fields.Float(string='Design Qty (Kg)', required=True)
    Correction = fields.Float(string='%Mois/%Abs/Corr(Kg)')
    Corrected = fields.Float(string='Corrected(Kg)', default=2.0)
    actual_qty = fields.Float(string='Actual Qty (Kg)')
    
    Required = fields.Float(string='Required(Kg)', compute='_compute_variance', store=True)
    Batched = fields.Float(string='Batched(Kg)', compute='_compute_variance', store=True)
    variance = fields.Float(string='Variance(Kg)', compute='_compute_variance', store=True)
    variance_percentage = fields.Float(string='Variance %', compute='_compute_variance', store=True)
    
    @api.depends(
        'design_qty', 'actual_qty', 'material_name', 'material_code',
        'docket_id.docket_batch_ids.ten_mm', 'docket_id.docket_batch_ids.twenty_mm',
        'docket_id.docket_batch_ids.facs', 'docket_id.docket_batch_ids.water_batch',
        'docket_id.docket_batch_ids.flyash', 'docket_id.docket_batch_ids.adm_plast',
        'docket_id.docket_batch_ids.WATERR'
    )
    def _compute_variance(self):
        for record in self:
            record.Required = record.design_qty

            # Collect batches for this docket (empty recordset if no docket)
            if record.docket_id:
                batches = self.env['rmc.docket.batch'].search([('docket_id', '=', record.docket_id.id)])
            else:
                batches = self.env['rmc.docket.batch'].browse()

            # Sum all batch material fields into a map
            total_materials = {
                'ten_mm': sum(b.ten_mm for b in batches),
                'twenty_mm': sum(b.twenty_mm for b in batches),
                'facs': sum(b.facs for b in batches),
                'water_batch': sum(b.water_batch for b in batches),
                'flyash': sum(b.flyash for b in batches),
                'adm_plast': sum(b.adm_plast for b in batches),
                'WATERR': sum(b.WATERR for b in batches),
            }

            # Prefer matching by material_code (e.g. 'ca10mm', 'ca20mm'), fallback to material_name
            key = (record.material_code or record.material_name or '')
            norm = re.sub(r'[^a-z0-9]', '', (key or '').lower())
            batched_val = 0.0

            # Match CA10 / CA10MM
            if ('ca10mm' in norm) or (norm.endswith('10mm') and '20' not in norm) or ('ca10' in norm and '20' not in norm):
                batched_val = total_materials['ten_mm']
            # Match CA20 / CA20MM
            elif ('ca20mm' in norm) or (norm.endswith('20mm')) or ('ca20' in norm):
                batched_val = total_materials['twenty_mm']
            # Flyash
            elif 'flyash' in norm or 'fly' in norm:
                batched_val = total_materials['flyash']
            # Water
            elif 'water' in norm or 'waterr' in norm or 'h2o' in norm:
                batched_val = total_materials['WATERR']
            # Admixture / admixture codes
            elif 'adm' in norm or 'admix' in norm or 'admixture' in norm:
                batched_val = total_materials['adm_plast']
            # Filler / cement / facs
            elif 'fac' in norm or 'facs' in norm or 'cement' in norm or 'cem' in norm:
                batched_val = total_materials['facs']
            else:
                # last resort: try to infer from material_name similarly
                lname = re.sub(r'[^a-z0-9]', '', (record.material_name or '').lower())
                if ('10' in lname and '20' not in lname) or '10mm' in lname or 'ca10' in lname:
                    batched_val = total_materials['ten_mm']
                elif '20' in lname or '20mm' in lname or 'ca20' in lname:
                    batched_val = total_materials['twenty_mm']
                else:
                    batched_val = total_materials['facs']

            record.Batched = batched_val
            if record.design_qty > 0:
                record.variance = record.actual_qty - record.design_qty
                record.variance_percentage = (record.variance / record.design_qty) * 100


class RmcDocketBatch(models.Model):
    _name = 'rmc.docket.batch'
    _description = 'RMC Docket Batch'

    docket_id = fields.Many2one('rmc.docket', string='Docket', required=True, ondelete='cascade')
    batch_code = fields.Char(string='Batch Code')
    batch_id = fields.Char(string='Batch ID')
    ten_mm = fields.Float(string='CA10MM')
    twenty_mm = fields.Float(string='CA20MM')
    facs = fields.Float(string='FACS')
    water_batch = fields.Float(string='CEMOPC')
    flyash = fields.Float(string='FLYASHIR')
    adm_plast = fields.Float(string='ADMPLAST')
    WATERR = fields.Float(string='WATERR')

    # quantity for this batch (M3) - created by docket._generate_batches
    quantity_ordered = fields.Float(string='Batch Quantity (M3)')
