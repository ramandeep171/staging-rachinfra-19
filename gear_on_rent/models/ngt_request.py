import calendar

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class GearNgTLedger(models.Model):
    """Monthly ledger that stores NGT relief that has been approved."""

    _name = "gear.ngt.ledger"
    _description = "NGT Monthly Ledger"
    _order = "month desc, so_id"

    so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract",
        required=True,
        index=True,
        ondelete="cascade",
    )
    request_id = fields.Many2one(
        comodel_name="gear.ngt.request",
        string="NGT Request",
        required=True,
        ondelete="cascade",
    )
    month = fields.Date(string="Month", required=True, index=True)
    hours_relief = fields.Float(string="Approved Hours", digits=(16, 2))
    note = fields.Char(string="Notes")


class GearNgTRequest(models.Model):
    """Handles Non-Generation Time (NGT) requests and MGQ relief."""

    _name = "gear.ngt.request"
    _description = "Gear On Rent NGT Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Reference",
        default=lambda self: _("New"),
        copy=False,
        tracking=True,
    )
    so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract / SO",
        required=True,
        tracking=True,
        domain=[("state", "in", ["sale", "done"])],
    )
    date_start = fields.Datetime(string="Start", required=True, tracking=True)
    date_end = fields.Datetime(string="End", required=True, tracking=True)
    reason = fields.Text(string="Reason", tracking=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    approved_by = fields.Many2one(
        comodel_name="res.users",
        string="Approved By",
        tracking=True,
        readonly=True,
    )
    approved_on = fields.Datetime(string="Approved On", tracking=True, readonly=True)
    hours_total = fields.Float(
        string="Total Hours",
        compute="_compute_hours_total",
        store=True,
        digits=(16, 2),
    )
    month = fields.Date(
        string="Relief Month",
        compute="_compute_month",
        store=True,
        readonly=True,
    )
    mgq_monthly = fields.Float(
        string="MGQ (Monthly)",
        related="so_id.mgq_monthly",
        store=True,
        readonly=True,
        digits=(16, 2),
    )
    ngt_hourly_prorata_factor = fields.Float(
        string="NGT Hourly Prorata Factor",
        related="so_id.ngt_hourly_prorata_factor",
        store=True,
        readonly=True,
        digits=(16, 4),
    )
    ngt_hourly_rate = fields.Float(
        string="Per Hour Rate (m³/hr)",
        compute="_compute_ngt_hourly_rate",
        store=True,
        digits=(16, 2),
        readonly=True,
        help="Derived as (MGQ per month / days in month) / 24 hours.",
    )
    ngt_hourly_factor_effective = fields.Float(
        string="NGT Hourly Factor (m³/hr)",
        compute="_compute_ngt_hourly_factor_effective",
        store=True,
        digits=(16, 2),
        readonly=True,
        help="Uses contract factor if set, otherwise falls back to derived per-hour rate.",
    )
    ngt_qty = fields.Float(
        string="NGT Quantity (m³)",
        compute="_compute_ngt_qty",
        digits=(16, 2),
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        related="so_id.currency_id",
        store=True,
        readonly=True,
    )
    employee_expense = fields.Monetary(
        string="Employee Expense",
        currency_field="currency_id",
        tracking=True,
        readonly=True,
    )
    land_rent = fields.Monetary(
        string="Land Rent",
        currency_field="currency_id",
        tracking=True,
        readonly=True,
    )
    meter_reading_start = fields.Float(
        string="Start Meter Reading",
        digits=(16, 2),
        tracking=True,
    )
    meter_reading_end = fields.Float(
        string="End Meter Reading",
        digits=(16, 2),
        tracking=True,
    )
    electricity_unit_rate = fields.Monetary(
        string="Electricity Unit Rate",
        currency_field="currency_id",
        digits=(16, 2),
        tracking=True,
        readonly=True,
        help="Rate per unit/kVAh used to compute electricity expense from meter readings.",
    )
    electricity_units = fields.Float(
        string="Metered Units",
        compute="_compute_expense_breakdown",
        store=True,
        digits=(16, 2),
        readonly=True,
    )
    electricity_expense = fields.Monetary(
        string="Electricity Expense",
        currency_field="currency_id",
        compute="_compute_expense_breakdown",
        store=True,
        digits=(16, 2),
        readonly=True,
    )
    total_expense = fields.Monetary(
        string="Total Expense",
        currency_field="currency_id",
        compute="_compute_expense_breakdown",
        store=True,
        digits=(16, 2),
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="so_id.company_id",
        store=True,
        readonly=True,
    )

    @api.depends("date_start", "date_end")
    def _compute_hours_total(self):
        for request in self:
            hours = 0.0
            if request.date_start and request.date_end:
                if request.date_end < request.date_start:
                    raise UserError(_("End date must be after start date."))
                delta = request.date_end - request.date_start
                hours = float_round(delta.total_seconds() / 3600.0, precision_digits=2)
            request.hours_total = hours

    @api.depends("date_start")
    def _compute_month(self):
        for request in self:
            date_ref = request.date_start or fields.Datetime.now()
            request.month = fields.Date.to_date(date_ref).replace(day=1)

    @api.depends(
        "hours_total",
        "ngt_hourly_factor_effective",
        "ngt_hourly_prorata_factor",
        "ngt_hourly_rate",
        "mgq_monthly",
        "date_start",
    )
    def _compute_ngt_qty(self):
        for request in self:
            factor = request.ngt_hourly_factor_effective or 0.0
            request.ngt_qty = float_round((request.hours_total or 0.0) * factor, precision_digits=2)

    @api.depends("mgq_monthly", "date_start")
    def _compute_ngt_hourly_rate(self):
        for request in self:
            mgq = request.mgq_monthly or 0.0
            date_ref = fields.Datetime.to_datetime(request.date_start) if request.date_start else fields.Datetime.now()
            days = calendar.monthrange(date_ref.year, date_ref.month)[1]
            per_hour = 0.0
            if mgq > 0 and days > 0:
                per_hour = float_round((mgq / days) / 24.0, precision_digits=2)
            request.ngt_hourly_rate = per_hour

    @api.depends("ngt_hourly_prorata_factor", "ngt_hourly_rate")
    def _compute_ngt_hourly_factor_effective(self):
        for request in self:
            factor = request.ngt_hourly_prorata_factor or request.ngt_hourly_rate or 0.0
            factor = float_round(factor, precision_digits=2)
            request.ngt_hourly_factor_effective = factor

    @api.depends(
        "meter_reading_start",
        "meter_reading_end",
        "electricity_unit_rate",
        "employee_expense",
        "land_rent",
    )
    def _compute_expense_breakdown(self):
        for request in self:
            units = 0.0
            start_reading = request.meter_reading_start or 0.0
            end_reading = request.meter_reading_end or 0.0
            if start_reading and end_reading:
                if end_reading < start_reading:
                    raise UserError(_("End meter reading must be greater than or equal to start reading."))
                units = float_round(
                    end_reading - start_reading, precision_digits=2
                )
            electricity_cost = float_round(units * (request.electricity_unit_rate or 0.0), precision_digits=2)
            request.electricity_units = units
            request.electricity_expense = electricity_cost
            request.total_expense = float_round(
                (request.employee_expense or 0.0) + (request.land_rent or 0.0) + electricity_cost,
                precision_digits=2,
            )
            # Sync expense fields from the monthly master snapshot if available
            request._gear_pull_master_expenses()

    def _gear_pull_master_expenses(self):
        """Pull expense inputs from the monthly work order master (if any) and lock edits."""
        if not self.so_id or not self.month:
            return
        monthly = (
            self.env["gear.rmc.monthly.order"]
            .search(
                [
                    ("so_id", "=", self.so_id.id),
                    ("date_start", "<=", self.date_end.date() if self.date_end else self.month),
                    ("date_end", ">=", self.date_start.date() if self.date_start else self.month),
                ],
                limit=1,
            )
        )
        if not monthly:
            return
        vals = {}
        if monthly.ngt_employee_expense:
            vals["employee_expense"] = monthly.ngt_employee_expense
        if monthly.ngt_land_rent:
            vals["land_rent"] = monthly.ngt_land_rent
        if monthly.ngt_electricity_unit_rate:
            vals["electricity_unit_rate"] = monthly.ngt_electricity_unit_rate
        if vals:
            self.update(vals)

    def action_submit(self):
        for request in self:
            if request.state != "draft":
                raise UserError(_("Only draft requests can be submitted."))
            request.state = "submitted"
        return True

    def action_reset_to_draft(self):
        for request in self:
            if request.state not in ("rejected", "submitted"):
                raise UserError(_("Only submitted or rejected requests can be reset."))
            request.state = "draft"
        return True

    def action_reject(self):
        self._ensure_can_approve()
        for request in self:
            if request.state != "submitted":
                raise UserError(_("Only submitted requests can be rejected."))
            request.state = "rejected"
        return True

    def action_approve(self):
        self._ensure_can_approve()
        for request in self:
            if request.state != "submitted":
                raise UserError(_("Only submitted requests can be approved."))
            if not request.hours_total:
                raise UserError(_("Cannot approve an NGT request without duration."))
            request.so_id.gear_generate_monthly_orders(
                date_start=fields.Date.to_date(request.date_start),
                date_end=fields.Date.to_date(request.date_end),
            )
            request.so_id.gear_register_ngt(request)
            month = request.month
            request._create_ledger_entry(month)
            request.write(
                {
                    "state": "approved",
                    "approved_by": self.env.user.id,
                    "approved_on": fields.Datetime.now(),
                }
            )
        return True

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("gear_on_rent.action_report_ngt_request").report_action(self)

    def _create_ledger_entry(self, month):
        self.ensure_one()
        ledger_env = self.env["gear.ngt.ledger"]
        existing = ledger_env.search(
            [
                ("request_id", "=", self.id),
            ],
            limit=1,
        )
        if existing:
            existing.write(
                {
                    "so_id": self.so_id.id,
                    "month": month,
                    "hours_relief": self.hours_total,
                }
            )
        else:
            ledger_env.create(
                {
                    "so_id": self.so_id.id,
                    "request_id": self.id,
                    "month": month,
                    "hours_relief": self.hours_total,
                }
            )

    def _ensure_can_approve(self):
        if not self.env.user.has_group("gear_on_rent.group_gear_on_rent_manager"):
            raise UserError(_("Only Gear On Rent managers can approve requests."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _("New"):
                record.name = self.env["ir.sequence"].next_by_code("gear.ngt.request") or _("New")
        return records
