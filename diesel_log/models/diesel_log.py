# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.fleet.models.fleet_vehicle_model import FUEL_TYPES


ALLOWED_DIESEL_FUEL_TYPES = {
    'diesel',
    'plug_in_hybrid_diesel',
}


class DieselLog(models.Model):
    old_log_ids = fields.One2many(
        comodel_name='diesel.log',
        inverse_name='vehicle_id',
        string='Old Logs',
        compute='_compute_old_log_ids',
        store=False,
        readonly=True,
        help='Previous diesel logs for this vehicle.'
    )

    @api.depends('vehicle_id', 'attendance_check_in', 'attendance_check_out')
    def _compute_old_log_ids(self):
        for rec in self:
            if not rec.vehicle_id:
                rec.old_log_ids = False
                continue

            domain = [
                ('vehicle_id', '=', rec.vehicle_id.id),
                ('id', '!=', rec.id),
            ]
            if rec.attendance_check_in:
                domain.append(('date', '>=', rec.attendance_check_in))
            if rec.attendance_check_out:
                domain.append(('date', '<=', rec.attendance_check_out))

            old_logs = self.env['diesel.log'].search(domain, order='date desc')
            rec.old_log_ids = old_logs

            if rec.log_type == 'equipment':
                # Sum quantity from all matched logs; used to drive issue diesel for equipment attendances
                rec.quantity = sum(old_logs.mapped('quantity')) if old_logs else 0.0
    odometer_difference = fields.Float(
        string='Odometer Usage',
        compute='_compute_odometer_difference',
        store=True,
        help='Difference between current and last odometer readings.'
    )
    odometer_difference_display = fields.Char(
        string='Odometer Usage',
        compute='_compute_odometer_difference_display',
        help="Human readable odometer difference or 'Waiting...' while pending",
        store=False
    )

    @api.depends('current_odometer', 'last_odometer')
    def _compute_odometer_difference(self):
        for rec in self:
            rec.odometer_difference = (rec.current_odometer or 0.0) - (rec.last_odometer or 0.0)
    
    @api.depends('odometer_difference', 'current_odometer', 'last_odometer', 'state')
    def _compute_odometer_difference_display(self):
        for rec in self:
            if not rec.current_odometer and not rec.last_odometer:
                rec.odometer_difference_display = _('Waiting...')
            elif rec.current_odometer in (0, False) and rec.state == 'draft':
                rec.odometer_difference_display = _('Waiting...')
            else:
                # Format with no decimals if integer difference, else 2 decimals
                diff = rec.odometer_difference
                if diff is None:
                    rec.odometer_difference_display = _('Waiting...')
                else:
                    formatted = ('%d' % diff) if float(diff).is_integer() else ('%.2f' % diff)
                    rec.odometer_difference_display = _('%s %s') % (formatted, rec._get_odometer_unit_label())

    def _get_odometer_unit_label(self):
        self.ensure_one()
        if self.log_type == 'equipment':
            return _('hr')
        field_info = self.fields_get(['odometer_unit']).get('odometer_unit', {})
        selection = dict(field_info.get('selection') or [])
        if self.odometer_unit and self.odometer_unit in selection:
            return selection[self.odometer_unit]
        return _('unit')
    fuel_efficiency = fields.Float(
        string='Current Avg Efficiency',
        help='Average efficiency = distance or hours used divided by fuel consumption.',
        compute='_compute_fuel_efficiency',
        store=True,
        tracking=True,
    )
    current_efficiency = fields.Float(
        string='Current Efficiency',
        help='Current Efficiency = Odometer Difference multiplied by the vehicle average efficiency (per selected unit).',
        compute='_compute_current_efficiency',
        store=True,
        readonly=True,
    )
    fuel_short = fields.Float(
    string='Fuel Short/Excess',
    help='Fuel Short/Excess = Current Efficiency - Fuel Consumption (positive = excess, negative = short)',
        compute='_compute_fuel_short',
        store=True,
        readonly=True,
    )
    fuel_short_excess_display = fields.Html(
        string='Fuel Short/Excess',
        compute='_compute_fuel_short',
        sanitize=False,
        help='Colored indicator: red when shortage (negative), green when excess (positive), black when zero.'
    )
    fuel_short_remark = fields.Char(
    string='Remark',
    help='Enter remark for shortage (shown only when Fuel Short/Excess is negative).'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        help='Operator / employee for Equipment log.',
        tracking=True,
    )
    attendance_check_in = fields.Datetime(
        string='Check In',
        help='Attendance check in time (auto-fetched for employee on equipment logs).',
        readonly=True,
    )
    attendance_check_out = fields.Datetime(
        string='Check Out',
        help='Attendance check out time (auto-fetched for employee on equipment logs).',
        readonly=True,
    )
    log_type = fields.Selection([
        ('diesel', 'Diesel Log'),
        ('equipment', 'Equipment Log'),
    ], string='Log Type', default='diesel', required=True, index=True, tracking=True,
       help='Classify record as Diesel or Equipment log to allow separate menus via domain.')
    date = fields.Datetime(
        string='Date',
        required=False,  # conditionally required only for diesel logs
        default=fields.Datetime.now,
        tracking=True,
        help='Date/time (required for Diesel logs, optional for Equipment).'
    )
    _name = 'diesel.log'
    _description = 'Diesel Log'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Enable chatter so message_post works
    
    # Core fields
    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'),
        copy=False,
        tracking=True
    )
    
    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        required=False,  # conditionally required only for diesel logs
        domain="[('company_id', 'in', [company_id, False]), '|', ('fuel_type', '=', False), ('fuel_type', 'in', ['diesel', 'plug_in_hybrid_diesel'])]",
        tracking=True,
        help='Vehicle (required for Diesel logs, optional for Equipment).'
    )
    vehicle_fuel_type = fields.Selection(
        related='vehicle_id.fuel_type',
        selection=FUEL_TYPES,
        string='Vehicle Fuel Type',
        store=True,
        readonly=True,
    )
    driver_id = fields.Many2one(
        'res.partner',
        string='Driver',
        related='vehicle_id.driver_id',
        store=True,
        readonly=True,
        help='Driver of the selected vehicle (from Vehicle record).'
    )
    photo = fields.Binary(
        string='Photo',
        attachment=True,
        help='Optional photo / proof for this diesel log.'
    )
    shift = fields.Selection([
        ('a', 'Shift A'),
        ('b', 'Shift B'),
        ('c', 'Shift C'),
    ], string='Shift', default='a', tracking=True, help='Operational shift for this diesel log.')
    vehicle_avg_fuel_eff_per_hr = fields.Float(
        related='vehicle_id.avg_fuel_efficiency_per_hr',
        string='Avg Fuel Eff (Per hr)',
        readonly=False,
        store=True,
        help='Editable proxy of vehicle Average Fuel Efficiency (Per hr). Changing here updates vehicle.'
    )
    in_1_gaje = fields.Float(
        string='In 1 Gaje',
        compute='_compute_in_1_gaje',
        store=True,
        readonly=True,
        help='Numeric value of 1 Gaje taken from vehicle in_1_gaje_vehicle (cast to float).'
    )
    odometer_unit = fields.Selection(
        related='vehicle_id.odometer_unit',
        selection=[('kilometers', 'km'), ('miles', 'mi')],
        string='Odometer Unit',
        store=True,
        readonly=True,
    )
    
    @api.depends('vehicle_id', 'vehicle_id.in_1_gaje_vehicle')
    def _compute_in_1_gaje(self):
        for rec in self:
            val = 0.0
            if rec.vehicle_id and hasattr(rec.vehicle_id, 'in_1_gaje_vehicle'):
                raw = rec.vehicle_id.in_1_gaje_vehicle
                # Cast numeric strings or ints to float; ignore non-numeric gracefully
                try:
                    if raw not in (False, None, ''):
                        val = float(raw)
                except (ValueError, TypeError):
                    val = 0.0
            rec.in_1_gaje = val

    def _refresh_diesel_balances(self):
        """Force recomputation of balance-related computed fields in new records."""
        if not self:
            return
        self._compute_in_1_gaje()
        self._compute_opening_diesel()
        self._compute_issue_and_closing_diesel()
        self._compute_fuel_consumption()
        self._compute_fuel_efficiency()
        self._compute_current_efficiency()
        self._compute_fuel_short()
        self._compute_actual_fuel_cost_per_cum()
        self._compute_short_excess_cost()

    @api.onchange('vehicle_id', 'quantity', 'current_gaje', 'last_gaje')
    def _onchange_refresh_diesel_balances(self):
        self._refresh_diesel_balances()

    @api.onchange('employee_id', 'log_type')
    def _onchange_employee_attendance_times(self):
        """Fetch latest open/closed attendance for selected employee when equipment log."""
        for rec in self:
            if rec.log_type != 'equipment' or not rec.employee_id:
                continue
            Attendance = self.env['hr.attendance']
            # get latest attendance for that day (or overall) - simple approach
            att = Attendance.search([
                ('employee_id', '=', rec.employee_id.id)
            ], order='check_in desc', limit=1)
            rec.attendance_check_in = att.check_in if att else False
            rec.attendance_check_out = att.check_out if att else False

    @api.constrains('log_type', 'date', 'vehicle_id', 'quantity')
    def _check_required_for_diesel(self):
        for rec in self:
            if rec.log_type == 'diesel':
                missing = []
                if not rec.date:
                    missing.append(_('Date'))
                if not rec.vehicle_id:
                    missing.append(_('Vehicle'))
                if rec.quantity in (False, None) or rec.quantity == 0.0:
                    missing.append(_('Quantity'))
                if missing:
                    raise ValidationError(_('%s required for Diesel Log.') % ', '.join(missing))
    
    product_id = fields.Many2one(
        'product.product',
        string='Diesel Product',
        readonly=True,
        tracking=True
    )
    
    quantity = fields.Float(
        string='Quantity (Liters)',
        required=False,  # conditionally required only for diesel logs
        digits='Product Unit of Measure',
        tracking=True,
        help='Quantity of diesel issued in liters (required for Diesel logs).'
    )
    
    last_odometer = fields.Float(
        string='Last Odometer Reading',
        readonly=True,
        store=True,
        help='Previous odometer reading from fleet'
    )
    last_odometer_datetime = fields.Datetime(
    string='Previous Log Date/Time',
        readonly=True,
        help='Timestamp of the odometer entry from which the Last Odometer Reading was taken.'
    )
    
    current_odometer = fields.Float(
        string='Current Odometer Reading',
        required=False,  # Not mandatory for equipment logs
        tracking=True,
        help='Current odometer reading (required for Diesel logs, optional for Equipment logs).',
    )
    current_odometer_datetime = fields.Datetime(
    string='Current Log Date/Time',
        readonly=True,
        help='Timestamp when the Current Odometer Reading was last entered/changed.'
    )
    production_name = fields.Char(
    string='Production (This Period)',
          # default value; user may change manually
        help='Enter related production / operation name.'
    )
    diesel_rate = fields.Float(
        string='Diesel Rate',
        default=90.0,
        help='Diesel rate per liter (default 90).'
    )
    actual_fuel_cost_per_cum = fields.Float(
        string='Actual Fuel Cost per CuM',
        compute='_compute_actual_fuel_cost_per_cum',
        store=True,
        readonly=True,
        help='Production (This Period) divided by Fuel Consumption.'
    )
    short_excess_cost = fields.Float(
    string='Cost Short/Excess',
        compute='_compute_short_excess_cost',
        store=True,
        readonly=True,
        help='Short/Excess Cost = Target Cost per CuM - Actual Fuel Cost per CuM (positive = saving/excess, negative = shortfall).'
    )
    # New Gaje fields
    last_gaje = fields.Float(
        string='Last Gaje',
        readonly=True,
        help='Previous gaje reading'
    )
    current_gaje = fields.Float(
        string='Current Gaje',
        help='Current gaje reading'
    )

    # Fuel balance fields
    opening_diesel = fields.Float(
        string='Opening Diesel',
        compute='_compute_opening_diesel',
        store=True,
        readonly=True,
        help='Opening diesel = Last Gaje * In 1 Gaje (or Gaje Liter fallback).'
    )
    opening_diesel_display = fields.Char(
        string='Opening Diesel Formula',
        compute='_compute_opening_diesel',
        store=False,
        help='Human readable formula: Opening = Last Gaje * In 1 Gaje'
    )
    issue_diesel = fields.Float(
        string='Issue Diesel',
        compute='_compute_issue_and_closing_diesel',
        store=True,
        help='Diesel issued for this log (mirrors Quantity).'
    )
    closing_diesel = fields.Float(
        string='Closing Diesel',
        compute='_compute_issue_and_closing_diesel',
        store=True,
    help='Closing diesel = Current Gaje * In 1 Gaje (or Gaje Liter fallback).'
    )
    fuel_consumption = fields.Float(
        string='Fuel Consumption',
        compute='_compute_fuel_consumption',
        store=True,
        readonly=True,
        help='Fuel Consumption = Opening Diesel + Issue Diesel - Closing Diesel'
    )

    
    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Picking',
        readonly=True,
        copy=False
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        help='Company (editable in draft).'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Workflow tracking fields
    requested_by_id = fields.Many2one('res.users', string='Requested By', readonly=True, tracking=True)
    requested_date = fields.Datetime(string='Requested Date', readonly=True, tracking=True)
    approved_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, tracking=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True, tracking=True)
    cancelled_by_id = fields.Many2one('res.users', string='Cancelled By', readonly=True, tracking=True)
    cancelled_date = fields.Datetime(string='Cancelled Date', readonly=True, tracking=True)

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('name', _('New')) == _('New'):
                seq_code = 'diesel.log'
                if vals.get('log_type') == 'equipment':
                    seq_code = 'equipment.log'
                vals['name'] = self.env['ir.sequence'].next_by_code(seq_code) or _('New')

            if vals.get('log_type', 'diesel') == 'diesel':
                diesel_product_id = vals.get('product_id') or self._get_default_product_id()
                if not diesel_product_id:
                    raise UserError(_('Please configure the Diesel Product in Settings before creating diesel logs.'))
                vals['product_id'] = diesel_product_id

            vehicle_id = vals.get('vehicle_id')
            if vehicle_id and not vals.get('last_odometer'):
                last_odometer = self.env['fleet.vehicle.odometer'].search([
                    ('vehicle_id', '=', vehicle_id)
                ], order='value desc', limit=1)
                vals['last_odometer'] = last_odometer.value if last_odometer else 0.0
                if last_odometer:
                    vals['last_odometer_datetime'] = last_odometer.date or last_odometer.create_date

            if vehicle_id and not vals.get('last_gaje'):
                prev_log = self.env['diesel.log'].search([
                    ('vehicle_id', '=', vehicle_id)
                ], order='date desc,id desc', limit=1)
                vals['last_gaje'] = prev_log.current_gaje if prev_log else 0.0

            prepared.append(vals)

        records = super(DieselLog, self).create(prepared)

        for record in records:
            if record.log_type == 'diesel' and not record.product_id:
                diesel_product_id = record._get_default_product_id()
                if not diesel_product_id:
                    raise UserError(_('Please configure the Diesel Product in Settings before creating diesel logs.'))
                record.product_id = diesel_product_id

            if record.current_odometer and not record.current_odometer_datetime:
                record.current_odometer_datetime = record.date or fields.Datetime.now()

            if record.vehicle_id and record.current_odometer:
                driver = getattr(record.vehicle_id, 'driver_id', False)
                odometer_vals = {
                    'vehicle_id': record.vehicle_id.id,
                    'value': record.current_odometer,
                    'date': record.date or fields.Datetime.now(),
                    'driver_id': driver.id if driver else False,
                }
                if 'diesel_log_id' in record.env['fleet.vehicle.odometer']._fields:
                    odometer_vals['diesel_log_id'] = record.id
                record.env['fleet.vehicle.odometer'].create(odometer_vals)

            if record.log_type == 'diesel':
                picking = record._create_stock_picking()
                if picking:
                    record.picking_id = picking.id

            record._sync_shortage_activity()

        records._auto_enforce_shortage_workflow()
        return records

    def write(self, vals):
        res = super(DieselLog, self).write(vals)
        if 'current_odometer' in vals:
            now = fields.Datetime.now()
            for rec in self:
                if rec.current_odometer:  # only stamp when value present
                    rec.current_odometer_datetime = now
        self._sync_shortage_activity()
        self._auto_enforce_shortage_workflow()
        return res
    
    
    @api.model
    def _get_default_product_id(self):
        """Get the configured diesel product ID"""
        config = self.env['res.config.settings']
        return config._get_diesel_product_id()
    
    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Auto-fill last odometer reading from fleet.vehicle.odometer history"""
        if self.vehicle_id:
            last_odometer = self.env['fleet.vehicle.odometer'].search([
                ('vehicle_id', '=', self.vehicle_id.id)
            ], order='value desc', limit=1)
            self.last_odometer = last_odometer.value if last_odometer else 0.0
            self.last_odometer_datetime = last_odometer.date or last_odometer.create_date if last_odometer else False
            # Populate last_gaje from previous diesel log for this vehicle
            prev_log = self.env['diesel.log'].search([
                ('vehicle_id', '=', self.vehicle_id.id),
                ('id', '!=', self.id or 0)
            ], order='date desc,id desc', limit=1)
            self.last_gaje = prev_log.current_gaje if prev_log else 0.0
           
    @api.onchange('last_gaje', 'vehicle_id')
    def _onchange_last_gaje(self):
        # Kept for potential UI refresh; computed field handles value
        pass

    @api.constrains('quantity')
    def _check_quantity_positive(self):
        for record in self:
            if record.log_type == 'diesel' and record.quantity <= 0:
                raise ValidationError(_('Quantity must be greater than 0 for Diesel logs.'))
    
    @api.constrains('current_odometer', 'last_odometer')
    def _check_odometer_reading(self):
        for record in self:
            if record.log_type == 'diesel' and record.current_odometer < record.last_odometer:
                raise ValidationError(_('Current odometer reading cannot be less than the last odometer reading (Diesel logs only).'))

    @api.constrains('log_type', 'current_odometer')
    def _check_current_odometer_required_for_diesel(self):
        for rec in self:
            if rec.log_type == 'diesel' and (rec.current_odometer in (False, 0)):
                raise ValidationError(_('Current Odometer Reading is required for Diesel logs.'))

    @api.constrains('vehicle_id', 'log_type')
    def _check_vehicle_fuel_type(self):
        fuel_labels = dict(FUEL_TYPES)
        for rec in self:
            if rec.log_type != 'diesel' or not rec.vehicle_id:
                continue
            fuel_type = rec.vehicle_fuel_type
            if fuel_type and fuel_type not in ALLOWED_DIESEL_FUEL_TYPES:
                label = fuel_labels.get(fuel_type, fuel_type)
                raise ValidationError(_("Vehicle fuel type '%s' is not compatible with diesel logs.") % label)
    
    @api.constrains('current_gaje', 'last_gaje')
    def _check_gaje_reading(self):
            # Constraint disabled: current gaje may now be less than last gaje.
            return True

    @api.depends('quantity', 'opening_diesel', 'current_gaje', 'in_1_gaje', 'vehicle_id', 'vehicle_id.gaje_liter')
    def _compute_issue_and_closing_diesel(self):
        for rec in self:
            rec.issue_diesel = rec.quantity or 0.0
            # Closing Diesel now: Current Gaje * In 1 Gaje (fallback to vehicle.gaje_liter)
            factor = rec.in_1_gaje or 0.0
            if not factor and hasattr(rec.vehicle_id, 'gaje_liter'):
                factor = rec.vehicle_id.gaje_liter or 0.0
            rec.closing_diesel = (rec.current_gaje or 0.0) * factor

    @api.depends('last_gaje', 'in_1_gaje', 'vehicle_id', 'vehicle_id.gaje_liter', 'vehicle_id.in_1_gaje_vehicle')
    def _compute_opening_diesel(self):
        for rec in self:
            # Determine factor preference: in_1_gaje (computed from Studio field) else vehicle.gaje_liter
            factor = rec.in_1_gaje or 0.0
            if not factor and hasattr(rec.vehicle_id, 'gaje_liter'):
                factor = rec.vehicle_id.gaje_liter or 0.0
            rec.opening_diesel = (rec.last_gaje or 0.0) * factor
            if rec.last_gaje and factor:
                rec.opening_diesel_display = f"{rec.last_gaje} * {factor} = {rec.opening_diesel}"
            else:
                rec.opening_diesel_display = 'Waiting for values'

    @api.depends('opening_diesel', 'issue_diesel', 'closing_diesel')
    def _compute_fuel_consumption(self):
        for rec in self:
            rec.fuel_consumption = (rec.opening_diesel or 0.0) + (rec.issue_diesel or 0.0) - (rec.closing_diesel or 0.0)

    @api.depends('odometer_difference', 'fuel_consumption')
    def _compute_fuel_efficiency(self):
        for rec in self:
            # Expected formula: Avg = Odometer Difference / Fuel Consumption
            odom = rec.odometer_difference or 0.0
            cons = rec.fuel_consumption or 0.0
            if cons and odom:
                rec.fuel_efficiency = odom / cons
            else:
                rec.fuel_efficiency = 0.0
    
    @api.depends('odometer_difference', 'vehicle_avg_fuel_eff_per_hr', 'vehicle_id.avg_fuel_efficiency_per_hr')
    def _compute_current_efficiency(self):
        for rec in self:
            # Current Efficiency = Odometer Difference * Avg Fuel Eff (Per hr)
            rec.current_efficiency = (rec.odometer_difference or 0.0) * (rec.vehicle_avg_fuel_eff_per_hr or 0.0)

    @api.depends('fuel_consumption', 'current_efficiency')
    def _compute_fuel_short(self):
        for rec in self:
            # Fuel Short = Fuel Consumption - Current Efficiency
            rec.fuel_short = (rec.current_efficiency or 0.0) - (rec.fuel_consumption or 0.0)
            val = rec.fuel_short or 0.0
            color = '#000000'
            remark = False
            if val < 0:
                color = '#cc0000'  # red
                # keep existing user remark (no overwrite)
            elif val > 0:
                color = '#007800'  # green
            rec.fuel_short_excess_display = f"<span style='font-weight:600;color:{color};'>{val:.2f}</span>"

    def _auto_enforce_shortage_workflow(self):
        """Ensure workflow follows shortage rules:
        - Negative shortage stays in requested (needs review).
        - Non-negative shortage auto-approves when already requested.
        """
        if self.env.context.get('skip_auto_shortage'):
            return
        for rec in self:
            if rec.state in ('done', 'cancel'):
                continue
            shortage = rec.fuel_short or 0.0
            if shortage < 0:
                if rec.state == 'approved':
                    rec.with_context(skip_auto_shortage=True).write({
                        'state': 'requested',
                        'approved_by_id': False,
                        'approved_date': False,
                    })
                elif rec.state == 'draft':
                    rec.with_context(skip_auto_shortage=True).action_request()
            else:
                if rec.state == 'requested':
                    rec.with_context(skip_auto_shortage=True).action_approve()
                elif rec.state == 'draft':
                    rec.with_context(skip_auto_shortage=True).action_request()
                    rec.with_context(skip_auto_shortage=True).action_approve()

    @api.depends('production_name', 'fuel_consumption')
    def _compute_actual_fuel_cost_per_cum(self):
        for rec in self:
            prod_val = 0.0
            if rec.production_name:
                try:
                    prod_val = float(rec.production_name)
                except (ValueError, TypeError):
                    prod_val = 0.0
            cons = (rec.fuel_consumption or 0.0) * (rec.diesel_rate or 0.0)
            rec.actual_fuel_cost_per_cum = prod_val / cons if cons else 0.0

    # (Old shift log integration removed; now using internal equipment log model.)

    @api.depends('actual_fuel_cost_per_cum', 'vehicle_id.target_cost_per_cum')
    def _compute_short_excess_cost(self):
        for rec in self:
            target = getattr(rec.vehicle_id, 'target_cost_per_cum', 0.0) or 0.0
            rec.short_excess_cost = target - (rec.actual_fuel_cost_per_cum or 0.0)

   
    def action_confirm(self):
        """Finalize (Done) after approval: process stock picking if not already done."""
        for record in self:
            if record.state != 'approved':
                raise UserError(_('Only approved records can be finalized.'))
            # Basic validations (stricter rules apply only to diesel logs)
            if record.log_type == 'diesel':
                if not record.quantity or record.quantity <= 0:
                    raise UserError(_('Please enter a valid quantity.'))
                if not record.current_odometer:
                    raise UserError(_('Please enter the current odometer reading.'))
                if record.current_odometer < record.last_odometer:
                    raise UserError(_('Current odometer reading cannot be less than the last reading.'))
            # (Optional) if you want to (re)create picking only at final stage uncomment below block
            # if not record.picking_id:
            #     picking = record._create_stock_picking()
            #     if picking:
            #         picking.action_confirm()
            #         picking.action_assign()
            #         for move in picking.move_lines:
            #             move.quantity_done = move.product_uom_qty
            #         picking._action_done()
            #         record.picking_id = picking.id
            # Update vehicle odometer
            record.vehicle_id.odometer = record.current_odometer
            record.state = 'done'
            if hasattr(record, 'message_post'):
                record.message_post(body=_('Diesel log finalized (Done).'), message_type='notification')

    def action_request(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft records can be requested.'))
            record.requested_by_id = self.env.user
            record.requested_date = fields.Datetime.now()
            record.with_context(skip_auto_shortage=True).state = 'requested'
            if hasattr(record, 'message_post'):
                record.message_post(body=_('Request submitted for approval.'), message_type='notification')
            record._auto_enforce_shortage_workflow()

    def action_approve(self):
        for record in self:
            if record.state != 'requested':
                raise UserError(_('Only requested records can be approved.'))
            record.approved_by_id = self.env.user
            record.approved_date = fields.Datetime.now()
            record.with_context(skip_auto_shortage=True).state = 'approved'
            if hasattr(record, 'message_post'):
                record.message_post(body=_('Request approved. Ready to finalize.'), message_type='notification')

    def action_cancel(self):
        for record in self:
            if record.state in ('done', 'cancel'):
                raise UserError(_('Cannot cancel a done or already cancelled record.'))
            record.cancelled_by_id = self.env.user
            record.cancelled_date = fields.Datetime.now()
            record.state = 'cancel'
            if hasattr(record, 'message_post'):
                record.message_post(body=_('Diesel log cancelled.'), message_type='notification')
    
    def _create_stock_picking(self):
        """Create stock picking for diesel issuance"""
        # Get configured operation type
        operation_type = self._get_fuel_operation_type()
        if not operation_type:
            raise UserError(_('Fuel operation type is not configured. Please configure it in Settings.'))
        
        if not self.product_id:
            raise UserError(_('Diesel product is not configured. Please configure it in Settings.'))
        
        # Create picking
        picking_vals = {
            'picking_type_id': operation_type.id,
            'location_id': operation_type.default_location_src_id.id,
            'location_dest_id': operation_type.default_location_dest_id.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'move_type': 'direct',
        }
        
        picking = self.env['stock.picking'].create(picking_vals)
        
        # Create stock move
        move_vals = {
            'description_picking': _('Diesel Issue: %s') % self.vehicle_id.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'product_uom': self.product_id.uom_id.id,
            'location_id': operation_type.default_location_src_id.id,
            'location_dest_id': operation_type.default_location_dest_id.id,
            'picking_id': picking.id,
            'company_id': self.company_id.id,
        }
        
        self.env['stock.move'].create(move_vals)
        
        return picking
    
    def _get_fuel_operation_type(self):
        """Get the configured fuel operation type"""
        config = self.env['res.config.settings']
        return config._get_fuel_operation_type_id()

    def _sync_shortage_activity(self):
        """Keep mail activities aligned with shortage status for done logs."""
        Config = self.env['res.config.settings']
        activity_type = Config._get_shortage_activity_type()
        if not activity_type:
            return
        responsible = Config._get_shortage_activity_user()
        deadline = fields.Date.context_today(self)
        summary = _('Review fuel shortage')
        for record in self:
            activities = record.activity_ids.filtered(
                lambda act: act.activity_type_id == activity_type and act.state != 'done'
            )
            shortage_active = record.state == 'done' and (record.fuel_short or 0.0) < 0
            if shortage_active:
                shortage_value = abs(record.fuel_short or 0.0)
                vehicle_name = record.vehicle_id.display_name if record.vehicle_id else _('N/A')
                log_date = fields.Datetime.context_timestamp(record, record.date) if record.date else False
                note = _(
                    'Fuel shortage of %(shortage)s detected for %(vehicle)s on %(date)s.\n'
                    'Please review the log and add a remark if necessary.',
                ) % {
                    'shortage': f'{shortage_value:.2f}',
                    'vehicle': vehicle_name,
                    'date': log_date.strftime('%Y-%m-%d %H:%M:%S') if log_date else _('unspecified date'),
                }
                updates = {
                    'date_deadline': deadline,
                    'summary': summary,
                    'note': note,
                }
                if responsible:
                    updates['user_id'] = responsible.id
                if activities:
                    activities.write(updates)
                else:
                    record.activity_schedule(
                        date_deadline=deadline,
                        summary=summary,
                        note=note,
                        activity_type_id=activity_type.id,
                        user_id=responsible.id if responsible else False,
                    )
            else:
                if activities:
                    activities.action_feedback(
                        feedback=_('Fuel shortage resolved or log state updated.')
                    )

    def action_view_picking(self):
        """Smart button action to view related picking"""
        self.ensure_one()
        if self.picking_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Stock Picking'),
                'res_model': 'stock.picking',
                'res_id': self.picking_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False
    
    def action_reset_to_draft(self):
        """Reset to draft state (for managers only)"""
        for record in self:
            if record.state == 'done':
                raise UserError(_('Cannot reset a done record.'))
            record.with_context(skip_auto_shortage=True).state = 'draft'
            if hasattr(record, 'message_post'):
                record.message_post(body=_('Diesel log reset to draft.'), message_type='notification')
    
    def unlink(self):
        """Prevent deletion of confirmed records"""
        for record in self:
            if record.state == 'done':
                raise UserError(_('Cannot delete confirmed diesel log entries.'))
        return super(DieselLog, self).unlink()

    # Equipment log actions
    def action_create_equipment_log(self):
        self.ensure_one()
        existing = self.env['diesel.equipment.log'].search([('diesel_log_id', '=', self.id)], limit=1)
        if existing:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Equipment Log',
                'res_model': 'diesel.equipment.log',
                'view_mode': 'form',
                'res_id': existing.id,
                'target': 'current',
            }
        new_log = self.env['diesel.equipment.log'].create({
            'diesel_log_id': self.id,
            'vehicle_id': self.vehicle_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Equipment Log',
            'res_model': 'diesel.equipment.log',
            'view_mode': 'form',
            'res_id': new_log.id,
            'target': 'current',
        }

    def action_open_equipment_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Equipment Logs',
            'res_model': 'diesel.equipment.log',
            'view_mode': 'list,form,pivot,graph',
            'domain': [('diesel_log_id', '=', self.id)],
            'target': 'current',
            'context': {
                'default_diesel_log_id': self.id,
                'search_default_diesel_log_id': self.id,
            }
        }
