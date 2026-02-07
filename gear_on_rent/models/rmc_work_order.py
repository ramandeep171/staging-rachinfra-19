from calendar import monthrange
import calendar
from datetime import datetime, time, timedelta
from math import ceil

try:  # pragma: no cover - shim for dev/test containers
    import pytz
except ModuleNotFoundError:  # pragma: no cover
    from odoo_shims import pytz

import logging

from odoo import _, api, fields, models
from odoo.tools import float_round, format_date
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class GearRmcMonthlyOrder(models.Model):
    """Monthly umbrella that orchestrates daily manufacturing orders."""

    _name = "gear.rmc.monthly.order"
    _description = "RMC Monthly Work Order"
    _order = "date_start desc, name"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("gear.rmc.monthly.order") or _("New"),
        tracking=True,
    )
    so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract / SO",
        required=True,
        domain=[("state", "in", ["sale", "done"])],
        tracking=True,
    )
    workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Primary Work Center",
        help="Work center that should host the automatically generated work orders.",
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="RMC Product",
        required=True,
        help="Service/consumable product that represents the concrete mix for this contract.",
    )
    x_inventory_mode = fields.Selection(
        selection=[
            ("without_inventory", "Without Inventory"),
            ("with_inventory", "With Inventory"),
        ],
        string="Inventory Mode",
        default="without_inventory",
        tracking=True,
        help="Snapshot of the sales order inventory mode at the time this monthly order was created.",
    )
    x_real_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Real Warehouse",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="Warehouse to route production when Inventory Mode is set to With Inventory.",
    )
    date_start = fields.Date(string="Start Date", required=True, tracking=True)
    date_end = fields.Date(string="End Date", required=True, tracking=True)
    x_window_start = fields.Datetime(
        string="Window Start",
        tracking=True,
        help="Exact datetime at which this monthly work order window begins.",
    )
    x_window_end = fields.Datetime(
        string="Window End",
        tracking=True,
        help="Exact datetime at which this monthly work order window ends.",
    )
    x_is_cooling_period = fields.Boolean(
        string="Cooling Period",
        tracking=True,
        help="Flag indicating the window falls inside the contract cooling period.",
    )
    x_auto_email_daily = fields.Boolean(
        string="Email Daily Reports",
        default=True,
        help="When checked, emailing a daily MO report will notify the customer automatically.",
    )
    x_monthly_mgq_snapshot = fields.Float(
        string="Monthly MGQ Snapshot",
        digits=(16, 2),
        help="Snapshot of the contract MGQ allocated to this window.",
        tracking=True,
    )
    wastage_allowed_percent = fields.Float(
        string="Allowed Wastage (%)",
        digits=(16, 4),
        tracking=True,
        help="Scrap tolerance percent captured from the sales order at creation time.",
    )
    prime_rate = fields.Float(
        string="Prime Rate Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Prime production rate captured from the sales order variables.",
    )
    optimize_rate = fields.Float(
        string="Optimize Rate Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Optimize standby rate captured from the sales order variables.",
    )
    ngt_rate = fields.Float(
        string="NGT Rate Snapshot",
        digits=(16, 2),
        tracking=True,
        help="NGT rate captured from the sales order variables.",
    )
    excess_rate = fields.Float(
        string="Excess Rate Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Excess production rate captured from the sales order variables.",
    )
    mgq_monthly = fields.Float(
        string="MGQ (Monthly) Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Variable-based monthly MGQ captured for this window.",
    )
    cooling_months = fields.Integer(
        string="Cooling Months Snapshot",
        tracking=True,
        help="Cooling period length captured when the monthly work order was created.",
    )
    loto_waveoff_hours = fields.Float(
        string="LOTO Wave-Off Allowance Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Wave-off allowance captured from the sales order variables.",
    )
    waveoff_hours_remaining = fields.Float(
        string="Wave-Off Allowance Remaining",
        digits=(16, 2),
        compute="_compute_waveoff_remaining",
        store=True,
        help="Allowance minus applied wave-off hours.",
    )
    apply_waveoff_remaining = fields.Boolean(
        string="Apply Wave-Off Remaining to NGT Hours",
        default=True,
        help="When enabled, remaining wave-off allowance reduces NGT hours used for downtime relief.",
    )
    downtime_total_hours = fields.Float(
        string="Downtime Hours Total",
        digits=(16, 2),
        compute="_compute_downtime_relief_qty",
        store=True,
        help="NGT hours plus chargeable LOTO hours used for downtime relief.",
    )
    bank_pull_limit = fields.Float(
        string="Bank Pull Limit Snapshot",
        digits=(16, 2),
        tracking=True,
        help="Maximum allowed bank pull captured from the sales order variables.",
    )
    ngt_hourly_prorata_factor = fields.Float(
        string="NGT Hourly Prorata Factor Snapshot",
        digits=(16, 4),
        tracking=True,
        help="Hourly to m³ conversion factor captured for NGT relief calculations.",
    )
    ngt_employee_expense = fields.Monetary(
        string="NGT Employee Expense",
        currency_field="currency_id",
        default=0.0,
        copy=False,
        help="Manually entered monthly employee cost for the NGT annexure.",
    )
    ngt_land_rent = fields.Monetary(
        string="NGT Land Rent",
        currency_field="currency_id",
        default=0.0,
        copy=False,
        help="Manually entered monthly land rent for the NGT annexure.",
    )
    ngt_electricity_unit_rate = fields.Monetary(
        string="NGT Electricity Unit Rate",
        currency_field="currency_id",
        default=0.0,
        copy=False,
        help="Manually entered electricity unit rate for the NGT annexure.",
    )
    ngt_electricity_expense = fields.Monetary(
        string="NGT Electricity Expense",
        currency_field="currency_id",
        compute="_compute_ngt_expense_totals",
        store=True,
        help="Electricity expense derived from meter units and unit rate.",
    )
    ngt_total_expense = fields.Monetary(
        string="NGT Total Expense",
        currency_field="currency_id",
        compute="_compute_ngt_expense_totals",
        store=True,
        help="Total expense = employee + land rent + electricity expense.",
    )
    ngt_effective_rate = fields.Float(
        string="NGT Rate (Derived)",
        digits=(16, 2),
        compute="_compute_ngt_effective_rate",
        store=True,
        help="Derived NGT rate = NGT Total Expense ÷ Monthly MGQ. Used on invoice when available.",
    )
    ngt_meter_units = fields.Float(
        string="NGT Metered Units",
        digits=(16, 2),
        compute="_compute_ngt_expense_totals",
        store=True,
        help="Metered units pulled from the latest approved NGT request for this month.",
    )
    standard_loading_minutes = fields.Float(
        string="Standard Loading (min) Snapshot",
        digits=(16, 2),
        tracking=True,
    )
    diesel_burn_rate_per_hour = fields.Float(
        string="Diesel Burn Rate (L/hr) Snapshot",
        digits=(16, 2),
        tracking=True,
    )
    diesel_rate_per_litre = fields.Monetary(
        string="Diesel Rate per Litre",
        currency_field="currency_id",
        tracking=True,
    )
    last_generated_date = fields.Date(
        string="Last Generated Day",
        help="Most recent calendar day for which daily manufacturing orders were generated.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("done", "Done"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    production_ids = fields.One2many(
        comodel_name="mrp.production",
        inverse_name="x_monthly_order_id",
        string="Daily Manufacturing Orders",
    )
    docket_ids = fields.One2many(
        comodel_name="gear.rmc.docket",
        inverse_name="monthly_order_id",
        string="Dockets",
        readonly=True,
    )
    invoice_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="gear_monthly_order_id",
        string="Invoices",
        readonly=True,
    )
    invoice_count = fields.Integer(compute="_compute_invoice_stats")
    has_active_invoice = fields.Boolean(compute="_compute_invoice_stats")
    last_billed_end = fields.Date(compute="_compute_invoice_stats")
    has_remaining_invoice_window = fields.Boolean(compute="_compute_invoice_stats")
    monthly_target_qty = fields.Float(
        string="Monthly MGQ",
        digits=(16, 2),
        compute="_compute_monthly_target_qty",
        store=True,
    )
    adjusted_target_qty = fields.Float(
        string="Adjusted MGQ",
        digits=(16, 2),
        compute="_compute_adjusted_target",
        store=True,
    )
    prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        digits=(16, 2),
        compute="_compute_prime_output",
        store=True,
    )
    manual_on_qty = fields.Float(
        string="Manual Qty (On Production)",
        digits=(16, 3),
        compute="_compute_manual_rollup",
        store=True,
    )
    manual_after_qty = fields.Float(
        string="Manual Qty (After Production)",
        digits=(16, 3),
        compute="_compute_manual_rollup",
        store=True,
    )
    prime_with_manual_qty = fields.Float(
        string="Prime + Manual (m³)",
        digits=(16, 3),
        compute="_compute_manual_rollup",
        store=True,
    )
    mwo_prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        digits=(16, 2),
        compute="_compute_wastage_rollup",
        store=True,
        help="Sum of prime outputs across all linked manufacturing orders.",
    )
    mwo_allowed_wastage_qty = fields.Float(
        string="Allowed Wastage (m³)",
        digits=(16, 2),
        compute="_compute_wastage_rollup",
        store=True,
        help="Total scrap tolerance for the monthly window.",
    )
    mwo_actual_scrap_qty = fields.Float(
        string="Actual Scrap (m³)",
        digits=(16, 2),
        compute="_compute_wastage_rollup",
        store=True,
        help="Aggregated scrap captured on all manufacturing orders.",
    )
    mwo_over_wastage_qty = fields.Float(
        string="Over Wastage (m³)",
        digits=(16, 2),
        compute="_compute_wastage_rollup",
        store=True,
        help="Scrap quantity beyond the allowed tolerance.",
    )
    mwo_deduction_qty = fields.Float(
        string="Deduction Quantity (m³)",
        digits=(16, 2),
        compute="_compute_wastage_rollup",
        store=True,
        help="Quantity to be used for wastage-based deductions at the MWO level.",
    )
    wastage_penalty_rate = fields.Monetary(
        string="Wastage Penalty Rate",
        currency_field="currency_id",
        tracking=True,
        help="Rate used to value over-wastage quantities during debit note creation.",
    )
    optimized_standby_qty = fields.Float(
        string="Optimized Standby (m³)",
        digits=(16, 2),
        compute="_compute_optimized_standby",
        store=True,
    )
    ngt_hours = fields.Float(
        string="NGT Hours",
        digits=(16, 2),
        compute="_compute_relief_breakdown",
        store=False,
    )
    loto_hours = fields.Float(
        string="LOTO Hours",
        digits=(16, 2),
        compute="_compute_relief_breakdown",
        store=True,
    )
    waveoff_hours_applied = fields.Float(
        string="Wave-Off Applied",
        digits=(16, 2),
        compute="_compute_relief_breakdown",
        store=True,
    )
    waveoff_hours_chargeable = fields.Float(
        string="Wave-Off Chargeable",
        digits=(16, 2),
        compute="_compute_relief_breakdown",
        store=True,
    )
    excess_diesel_litre_total = fields.Float(
        string="Excess Diesel (L)",
        digits=(16, 3),
        compute="_compute_diesel_overrun_totals",
        store=True,
    )
    excess_diesel_amount_total = fields.Monetary(
        string="Excess Diesel Amount",
        currency_field="currency_id",
        compute="_compute_diesel_overrun_totals",
        store=True,
    )
    downtime_relief_qty = fields.Float(
        string="No-Generation Time (m³)",
        digits=(16, 2),
        compute="_compute_downtime_relief_qty",
        store=False,
    )
    runtime_minutes = fields.Float(
        string="Runtime (min)",
        digits=(16, 2),
        compute="_compute_runtime_idle",
        store=True,
    )
    idle_minutes = fields.Float(
        string="Idle (min)",
        digits=(16, 2),
        compute="_compute_runtime_idle",
        store=True,
    )
    docket_count = fields.Integer(
        string="Dockets",
        compute="_compute_docket_count",
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="so_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )

    _check_monthly_dates = models.Constraint(
        "CHECK(date_end >= date_start)",
        "End date must not be earlier than start date.",
    )

    @api.constrains("x_inventory_mode", "x_real_warehouse_id")
    def _check_inventory_mode_real_warehouse(self):
        for order in self:
            silent_wh = self._gear_get_silent_warehouse(order.company_id)
            if order.x_inventory_mode == "with_inventory" and not order.x_real_warehouse_id:
                raise ValidationError(_("Please select a real warehouse when using Inventory Mode: With Inventory."))
            # if silent_wh and order.x_real_warehouse_id and order.x_real_warehouse_id == silent_wh:
            #     raise ValidationError(_("The silent warehouse cannot be selected as the real warehouse."))

    @api.depends("x_window_start", "x_window_end", "date_start", "date_end", "so_id", "so_id.x_monthly_mgq")
    def _compute_monthly_target_qty(self):
        for order in self:
            prorated = order._gear_get_prorated_mgq()
            if prorated is not None:
                order.monthly_target_qty = prorated
            else:
                order.monthly_target_qty = order.so_id.x_monthly_mgq or 0.0

    @api.model
    def _gear_get_silent_warehouse(self, company=None):
        company = company or self.env.company
        param_model = self.env["ir.config_parameter"].sudo()
        company_key = f"gear_on_rent.silent_warehouse_id.{company.id}"
        param_value = param_model.get_param(company_key)
        if not param_value:
            param_value = param_model.get_param("gear_on_rent.silent_warehouse_id")
        silent_wh = False
        if param_value:
            try:
                silent_wh = self.env["stock.warehouse"].browse(int(param_value))
            except (TypeError, ValueError):
                silent_wh = False
        if silent_wh:
            silent_wh = silent_wh.filtered(lambda wh: wh and wh.company_id == company)
        return silent_wh

    def _gear_resolve_inventory_targets(self):
        self.ensure_one()
        mode = self.x_inventory_mode or self.so_id.x_inventory_mode or "without_inventory"
        real_wh = self.x_real_warehouse_id or self.so_id.x_real_warehouse_id
        silent_wh = self._gear_get_silent_warehouse(self.company_id)

        if mode == "with_inventory":
            warehouse = real_wh
            if not warehouse:
                raise UserError(_("Please configure a real warehouse on the sales order before scheduling production."))
            # if silent_wh and warehouse == silent_wh:
            #     raise UserError(_("The silent warehouse cannot be used when Inventory Mode is set to With Inventory."))
        else:
            warehouse = silent_wh
            if not warehouse:
                raise UserError(_("Silent warehouse is not configured. Please set it in Gear On Rent settings."))

        picking_type = warehouse.manu_type_id
        if not picking_type:
            raise UserError(_("Warehouse %s has no manufacturing picking type configured.") % (warehouse.display_name,))

        location_src = picking_type.default_location_src_id or warehouse.lot_stock_id
        location_dest = picking_type.default_location_dest_id or warehouse.lot_stock_id
        if not location_src or not location_dest:
            raise UserError(
                _(
                    "Warehouse %s lacks default source/destination locations for manufacturing. Please complete the configuration."
                )
                % (warehouse.display_name,)
            )

        return {
            "inventory_mode": mode,
            "warehouse": warehouse,
            "picking_type": picking_type,
            "location_src": location_src,
            "location_dest": location_dest,
        }

    @api.depends("monthly_target_qty", "downtime_relief_qty")
    def _compute_adjusted_target(self):
        for order in self:
            target_snapshot = order.monthly_target_qty or order.x_monthly_mgq_snapshot or 0.0
            relief = order.downtime_relief_qty or 0.0
            order.adjusted_target_qty = max(target_snapshot - relief, 0.0)

    @api.depends("production_ids.x_prime_output_qty")
    def _compute_prime_output(self):
        for order in self:
            order.prime_output_qty = sum(order.production_ids.mapped("x_prime_output_qty"))

    @api.depends("prime_output_qty", "docket_ids")
    def _compute_manual_rollup(self):
        ManualOp = self.env["gear.rmc.manual.operation"].sudo()
        for order in self:
            if not order.id:
                order.manual_on_qty = 0.0
                order.manual_after_qty = 0.0
                order.prime_with_manual_qty = order.prime_output_qty or 0.0
                continue
            ops = ManualOp.search([("docket_id.monthly_order_id", "=", order.id)])
            on_qty = sum(ops.filtered(lambda op: op.recipe_display_mode == "on_production").mapped("manual_qty_total"))
            after_qty = sum(
                ops.filtered(lambda op: op.recipe_display_mode == "after_production").mapped("manual_qty_total")
            )
            order.manual_on_qty = on_qty
            order.manual_after_qty = after_qty
            order.prime_with_manual_qty = (order.prime_output_qty or 0.0) + on_qty + after_qty

    @api.depends(
        "production_ids.prime_output_qty",
        "production_ids.wastage_allowed_qty",
        "production_ids.actual_scrap_qty",
        "production_ids.over_wastage_qty",
        "production_ids.deduction_qty",
    )
    def _compute_wastage_rollup(self):
        for order in self:
            prime_total = sum(order.production_ids.mapped("prime_output_qty"))
            allowed_total = sum(order.production_ids.mapped("wastage_allowed_qty"))
            actual_total = sum(order.production_ids.mapped("actual_scrap_qty"))
            over_total = max(actual_total - allowed_total, 0.0)
            order.mwo_prime_output_qty = prime_total
            order.mwo_allowed_wastage_qty = allowed_total
            order.mwo_actual_scrap_qty = actual_total
            order.mwo_over_wastage_qty = over_total
            order.mwo_deduction_qty = over_total

    @api.depends("monthly_target_qty", "downtime_relief_qty", "prime_output_qty", "x_is_cooling_period")
    def _compute_optimized_standby(self):
        for order in self:
            if order.x_is_cooling_period:
                order.optimized_standby_qty = 0.0
            else:
                target_snapshot = order.monthly_target_qty or order.x_monthly_mgq_snapshot or 0.0
                relief = order.downtime_relief_qty or 0.0
                prime = order.prime_output_qty or 0.0
                order.optimized_standby_qty = max(target_snapshot - relief - prime, 0.0)

    @api.depends(
        "production_ids.x_ngt_hours",
        "production_ids.x_loto_hours",
        "production_ids.x_waveoff_hours_applied",
        "production_ids.x_waveoff_hours_chargeable",
        "date_start",
        "date_end",
        "so_id",
    )
    def _compute_relief_breakdown(self):
        NgTLedger = self.env["gear.ngt.ledger"]
        LotoLedger = self.env["gear.loto.ledger"]
        for order in self:
            ngt_total = 0.0
            loto_total = 0.0
            ledger_domain = []
            if order.so_id:
                ledger_domain = [("so_id", "=", order.so_id.id)]
            month_key = None
            if order.date_start:
                # ledger month is stored as first day of the month
                month_key = order.date_start.replace(day=1)

            if ledger_domain:
                ngt_domain = list(ledger_domain)
                loto_domain = list(ledger_domain)
                if month_key:
                    ngt_domain.append(("month", "=", month_key))
                    loto_domain.append(("month", "=", month_key))
                ngt_domain.append(("request_id.state", "=", "approved"))

                ngt_ledgers = NgTLedger.search(ngt_domain)
                ngt_total = sum(ngt_ledgers.mapped("hours_relief")) if ngt_ledgers else 0.0

                # Fallback: if ledger is missing but requests exist, sum approved NGT requests for the month.
                if not ngt_total:
                    req_domain = [
                        ("so_id", "=", order.so_id.id),
                        ("state", "=", "approved"),
                    ]
                    if month_key:
                        req_domain.append(("month", "=", month_key))
                    ngt_requests = order.env["gear.ngt.request"].search(req_domain)
                    ngt_total = sum(ngt_requests.mapped("hours_total")) if ngt_requests else 0.0

                loto_ledgers = LotoLedger.search(loto_domain)
                loto_total = sum(loto_ledgers.mapped("hours_total")) if loto_ledgers else 0.0

            order.ngt_hours = ngt_total
            order.loto_hours = loto_total
            allowance = order.so_id.x_loto_waveoff_hours or 0.0
            order.waveoff_hours_applied = min(loto_total, allowance)
            order.waveoff_hours_chargeable = max(loto_total - allowance, 0.0)
            order.waveoff_hours_remaining = max(allowance - order.waveoff_hours_applied, 0.0)
            # If there are no approved NGT hours for this month, clear stale per-MO NGT allocations.
            if not ngt_total and order.production_ids:
                stale_productions = order.production_ids.filtered(lambda p: p.x_ngt_hours)
                if stale_productions:
                    for production in stale_productions.sudo():
                        qty_relief = production._gear_hours_to_qty(production.x_ngt_hours or 0.0)
                        if qty_relief:
                            production.x_relief_qty = max((production.x_relief_qty or 0.0) - qty_relief, 0.0)
                        production.x_ngt_hours = 0.0
    @api.depends("so_id.x_loto_waveoff_hours", "waveoff_hours_applied")
    def _compute_waveoff_remaining(self):
        for order in self:
            allowance = order.so_id.x_loto_waveoff_hours or 0.0
            applied = order.waveoff_hours_applied or 0.0
            order.waveoff_hours_remaining = max(allowance - applied, 0.0)

    @api.depends(
        "production_ids.x_ngt_hours",
        "production_ids.x_waveoff_hours_chargeable",
        "production_ids.x_daily_target_qty",
        "monthly_target_qty",
        "prime_output_qty",
        "x_is_cooling_period",
        "waveoff_hours_chargeable",
        "ngt_hours",
        "waveoff_hours_remaining",
        "apply_waveoff_remaining",
    )
    def _compute_downtime_relief_qty(self):
        for order in self:
            if order.x_is_cooling_period:
                target = order.monthly_target_qty or 0.0
                prime = order.prime_output_qty or 0.0
                order.downtime_relief_qty = round(max(target - prime, 0.0), 2)
                order.downtime_total_hours = 0.0
            else:
                # Prefer ledger-backed hours on the monthly order; fall back to per-MO hours.
                ngt_hours = order.ngt_hours
                waveoff_chargeable = order.waveoff_hours_chargeable
                allowance_remaining = order.waveoff_hours_remaining or 0.0

                # Requested formula: (NGT Hours - Remaining Wave-Off) + chargeable LOTO hours.
                if order.apply_waveoff_remaining:
                    effective_ngt = (ngt_hours or 0.0) - (allowance_remaining or 0.0)
                else:
                    effective_ngt = ngt_hours or 0.0
                hours = max((effective_ngt or 0.0) + (waveoff_chargeable or 0.0), 0.0)

                factor = order._gear_get_ngt_factor()
                order.downtime_relief_qty = round(hours * factor, 2)
                order.downtime_total_hours = round(hours, 2)

    def action_print_month_end_report(self):
        self.ensure_one()
        report = self.env.ref("gear_on_rent.action_report_month_end", raise_if_not_found=False)
        if not report:
            raise UserError(_("Month-End report configuration is missing."))

        Invoice = self.env["account.move"]
        invoice = Invoice.search(
            [
                ("gear_monthly_order_id", "=", self.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("state", "=", "posted"),
            ],
            order="invoice_date desc, id desc",
            limit=1,
        )
        if not invoice:
            invoice = Invoice.search(
                [
                    ("gear_monthly_order_id", "=", self.id),
                    ("move_type", "in", ("out_invoice", "out_refund")),
                ],
                order="invoice_date desc, id desc",
                limit=1,
            )
        if not invoice:
            raise UserError(_("No invoice found to generate the Month-End report for this work order."))

        return report.report_action(invoice)

    @api.depends(
        "so_id",
        "date_start",
        "ngt_employee_expense",
        "ngt_land_rent",
        "ngt_electricity_unit_rate",
    )
    def _compute_ngt_expense_totals(self):
        for order in self:
            meter_units = 0.0
            employee_val = order.ngt_employee_expense or 0.0
            land_val = order.ngt_land_rent or 0.0
            unit_rate = order.ngt_electricity_unit_rate or 0.0
            start_meter = None
            end_meter = None
            electricity_expense = 0.0
            total_expense = 0.0
            if order.so_id and order.date_start:
                month_key = order.date_start.replace(day=1)
                meter_logs = order.env["gear.ngt.meter.log"].search(
                    [("so_id", "=", order.so_id.id), ("month", "=", month_key)],
                    order="month desc, id desc",
                )
                if meter_logs:
                    start_candidates = [log.start_meter for log in meter_logs if log.start_meter]
                    end_candidates = [log.end_meter for log in meter_logs if log.end_meter]
                    if start_candidates:
                        start_meter = min(start_candidates)
                    if end_candidates:
                        end_meter = max(end_candidates)
                    if start_meter is not None and end_meter is not None:
                        meter_units = max(end_meter - start_meter, 0.0)
                    else:
                        meter_units = sum(meter_logs.mapped("meter_units"))
                    if not unit_rate:
                        unit_rate = meter_logs[-1].electricity_unit_rate or 0.0
                else:
                    ngt_requests = order.env["gear.ngt.request"].search(
                        [
                            ("so_id", "=", order.so_id.id),
                            ("month", "=", month_key),
                            ("state", "!=", "rejected"),
                        ],
                        order="date_start asc",
                    )
                    if ngt_requests:
                        starts = [req.meter_reading_start for req in ngt_requests if req.meter_reading_start]
                        ends = [req.meter_reading_end for req in ngt_requests if req.meter_reading_end]
                        if starts and ends:
                            start_meter = min(starts)
                            end_meter = max(ends)
                            meter_units = max(end_meter - start_meter, 0.0)
                        else:
                            meter_units = sum(ngt_requests.mapped("electricity_units"))
                        if not employee_val:
                            employee_val = ngt_requests[-1].employee_expense or 0.0
                        if not land_val:
                            land_val = ngt_requests[-1].land_rent or 0.0
                        if not unit_rate:
                            unit_rate = ngt_requests[-1].electricity_unit_rate or 0.0

            # Electricity expense = (metered units × 10) × unit rate (as requested)
            electricity_expense = (meter_units * 10.0) * unit_rate
            total_expense = employee_val + land_val + electricity_expense

            order.ngt_meter_units = meter_units
            order.ngt_electricity_expense = electricity_expense
            order.ngt_total_expense = total_expense

    @api.depends(
        "ngt_total_expense",
        "monthly_target_qty",
        "adjusted_target_qty",
        "mgq_monthly",
        "x_monthly_mgq_snapshot",
    )
    def _compute_ngt_effective_rate(self):
        for order in self:
            base_mgq = (
                order.monthly_target_qty
                or order.adjusted_target_qty
                or order.mgq_monthly
                or order.x_monthly_mgq_snapshot
                or 0.0
            )
            rate = 0.0
            if base_mgq:
                rate = (order.ngt_total_expense or 0.0) / base_mgq
            order.ngt_effective_rate = rate

    def write(self, vals):
        res = super().write(vals)
        tracked = {"ngt_employee_expense", "ngt_land_rent", "ngt_electricity_unit_rate"}
        needs_sync = tracked.intersection(vals.keys())
        if needs_sync:
            self._gear_sync_ngt_request_expenses()
        return res

    def _gear_sync_ngt_request_expenses(self):
        """Push master expense inputs into the latest NGT request for the month."""
        for order in self:
            if not order.so_id or not order.date_start:
                continue
            month_key = order.date_start.replace(day=1)
            ngt_request = (
                order.env["gear.ngt.request"]
                .search(
                    [
                        ("so_id", "=", order.so_id.id),
                        ("month", "=", month_key),
                        ("state", "!=", "rejected"),
                    ],
                    order="approved_on desc, create_date desc, id desc",
                    limit=1,
                )
            )
            if not ngt_request:
                continue
            update = {
                "employee_expense": order.ngt_employee_expense,
                "land_rent": order.ngt_land_rent,
                "electricity_unit_rate": order.ngt_electricity_unit_rate,
            }
            # Only write when there is a change to avoid needless chatter
            if any(
                ngt_request[field] != update[field]
                for field in ("employee_expense", "land_rent", "electricity_unit_rate")
            ):
                ngt_request.write(update)

    @api.depends("docket_ids.runtime_minutes", "docket_ids.idle_minutes")
    def _compute_runtime_idle(self):
        for order in self:
            order.runtime_minutes = sum(order.docket_ids.mapped("runtime_minutes"))
            order.idle_minutes = sum(order.docket_ids.mapped("idle_minutes"))

    @api.depends(
        "docket_ids.excess_minutes",
        "docket_ids.excess_diesel_litre",
        "docket_ids.excess_diesel_amount",
        "docket_ids.reason_type",
    )
    def _compute_diesel_overrun_totals(self):
        for order in self:
            eligible = order.docket_ids.filtered(
                lambda d: (d.excess_minutes or 0.0) > 0.0 and d.reason_type != "maintenance"
            )
            order.excess_diesel_litre_total = sum(eligible.mapped("excess_diesel_litre"))
            order.excess_diesel_amount_total = sum(eligible.mapped("excess_diesel_amount"))

    @api.depends("docket_ids")
    def _compute_docket_count(self):
        for order in self:
            order.docket_count = len(order.docket_ids)

    def _gear_get_ngt_factor(self):
        self.ensure_one()
        # Priority: monthly snapshot -> contract snapshot -> derived from MGQ/days -> daily target fallback.
        factor = self.ngt_hourly_prorata_factor or 0.0
        contract = self.so_id
        if not factor and contract:
            factor = contract.ngt_hourly_prorata_factor or 0.0
        if not factor:
            mgq = self.mgq_monthly or self.monthly_target_qty or (contract and (contract.x_monthly_mgq or contract.mgq_monthly)) or 0.0
            date_ref = self.date_start or fields.Date.context_today(self)
            days_in_month = calendar.monthrange(date_ref.year, date_ref.month)[1]
            if mgq and days_in_month:
                factor = float_round((mgq / days_in_month) / 24.0, precision_digits=2)
        if not factor:
            # Last fallback: use the first daily target snapshot if present.
            daily_target = sum(self.production_ids.mapped("x_daily_target_qty")) / len(self.production_ids) if self.production_ids else 0.0
            if daily_target:
                factor = float_round(daily_target / 24.0, precision_digits=2)
        return float_round(factor or 0.0, precision_digits=2)

    def _gear_get_prorated_mgq(self):
        self.ensure_one()
        contract = self.so_id
        base_mgq = contract.x_monthly_mgq if contract else 0.0
        month_hours = self._gear_get_month_hours()
        window_hours = self._gear_get_window_hours()
        ratio = 0.0
        if month_hours:
            ratio = window_hours / month_hours if window_hours else 0.0
        else:
            month_days = self._gear_get_month_days()
            window_days = self._gear_get_window_days()
            ratio = window_days / month_days if month_days else 0.0
        ratio = max(min(ratio, 1.0), 0.0)
        if base_mgq:
            return base_mgq * ratio
        if self.x_monthly_mgq_snapshot:
            return self.x_monthly_mgq_snapshot
        return 0.0

    def _gear_get_window_hours(self):
        self.ensure_one()
        start = self.x_window_start
        end = self.x_window_end
        if not start and self.date_start:
            start = datetime.combine(self.date_start, time.min)
        if not end and self.date_end:
            end = datetime.combine(self.date_end, time(23, 59, 59))
        return self._gear_compute_hours(start, end)

    def _gear_get_month_hours(self):
        self.ensure_one()
        if not self.date_start:
            return 0.0
        month_start = self.date_start.replace(day=1)
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        start_dt = datetime.combine(month_start, time.min)
        end_dt = datetime.combine(month_end, time(23, 59, 59))
        return self._gear_compute_hours(start_dt, end_dt)

    def _gear_get_window_days(self):
        self.ensure_one()
        if not self.date_start or not self.date_end or self.date_end < self.date_start:
            return 0
        return (self.date_end - self.date_start).days + 1

    def _gear_get_month_days(self):
        self.ensure_one()
        if not self.date_start:
            return 0
        last_day = monthrange(self.date_start.year, self.date_start.month)[1]
        month_start = self.date_start.replace(day=1)
        month_end = self.date_start.replace(day=last_day)
        return (month_end - month_start).days + 1

    @staticmethod
    def _gear_compute_hours(start_dt, end_dt):
        if not start_dt or not end_dt or end_dt < start_dt:
            return 0.0
        return max(((end_dt - start_dt).total_seconds() + 1.0) / 3600.0, 0.0)

    def action_schedule_orders(self, until_date=False):
        """Generate or refresh the daily manufacturing orders for the month."""
        for order in self:
            processed = order._generate_daily_productions(until_date=until_date)
            if processed:
                order.state = "scheduled"

    def action_mark_done(self):
        for order in self:
            order.state = "done"
            if order.so_id:
                order.so_id.gear_generate_next_monthly_order()
        # Ensure debit notes are generated as soon as wastage is finalized.
        self._gear_create_over_wastage_debit_note()

    def _generate_daily_productions(self, until_date=False):
        Production = self.env["mrp.production"]
        Workorder = self.env["mrp.workorder"]
        processed_any = False
        for order in self:
            if not order.product_id:
                raise UserError(_("Please select an RMC product before scheduling daily orders."))

            workcenter = order.workcenter_id or order.so_id.x_workcenter_id or order.product_id.gear_workcenter_id
            if not workcenter:
                raise UserError(
                    _(
                        "Please assign a work center to either the monthly order, the sale order, or the product itself."
                    )
                )

            if not order.workcenter_id:
                order.workcenter_id = workcenter

            days_in_month = (
                (order.date_end - order.date_start).days + 1
                if order.date_start and order.date_end
                else 0
            )
            if days_in_month <= 0:
                raise UserError(_("The monthly order must span at least one day."))

            target_qty = order.monthly_target_qty or 0.0
            daily_target = round(target_qty / days_in_month, 2) if days_in_month else 0.0

            if daily_target <= 0:
                raise UserError(
                    _(
                        "Monthly MGQ must be a positive value before generating daily orders for %s. "
                        "Please update the contract's Monthly MGQ."
                    )
                    % (order.so_id.display_name or order.name)
                )

            user_tz = order._gear_get_user_tz()
            if not order.last_generated_date and order.production_ids:
                existing_dates = [
                    order._gear_datetime_to_local_date(prod.date_start, user_tz)
                    for prod in order.production_ids
                    if prod.date_start
                ]
                existing_dates = [d for d in existing_dates if d]
                if existing_dates:
                    order.last_generated_date = max(existing_dates)
            if until_date:
                generation_end = min(until_date, order.date_end)
            else:
                generation_end = order.date_end

            if not generation_end or generation_end < order.date_start:
                continue

            if until_date:
                start_day = order.last_generated_date + timedelta(days=1) if order.last_generated_date else order.date_start
                cursor = max(order.date_start, start_day)
            else:
                cursor = order.date_start

            if cursor > generation_end:
                continue

            # Clean up productions and dockets that fall outside the monthly window
            cleanup_productions = order.production_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            for production in cleanup_productions:
                local_date = order._gear_datetime_to_local_date(production.date_start, user_tz)
                if not local_date:
                    continue
                if local_date < order.date_start or local_date > order.date_end:
                    if production.x_docket_ids:
                        continue
                    try:
                        production.unlink()
                    except Exception:
                        _logger.exception("Failed to remove out-of-window production %s", production.display_name)

            draft_dockets = order.docket_ids.filtered(lambda d: d.state == "draft" and d.date)
            if draft_dockets:
                before_start = draft_dockets.filtered(lambda d: d.date < order.date_start)
                if before_start:
                    before_start.write({"date": order.date_start})
                after_end = draft_dockets.filtered(lambda d: d.date > order.date_end)
                if after_end:
                    after_end.write({"date": order.date_end})

            existing_map = {
                order._gear_datetime_to_local_date(production.date_start, user_tz): production
                for production in order.production_ids
                if production.date_start
            }

            processed_order = False

            routing = order._gear_resolve_inventory_targets()

            while cursor <= generation_end:
                start_dt, end_dt = order._gear_get_day_bounds(cursor, user_tz)

                production = existing_map.get(cursor)
                if production:
                    if production.state not in ("done", "cancel"):
                        production.write(
                            {
                                "product_qty": daily_target,
                                "x_daily_target_qty": daily_target,
                                "x_is_cooling_period": order.x_is_cooling_period,
                                "warehouse_id": routing["warehouse"].id,
                                "picking_type_id": routing["picking_type"].id,
                                "location_src_id": routing["location_src"].id,
                                "location_dest_id": routing["location_dest"].id,
                                "x_inventory_mode": routing["inventory_mode"],
                                "x_target_warehouse_id": routing["warehouse"].id,
                                "wastage_allowed_percent": order.wastage_allowed_percent,
                                "wastage_penalty_rate": order.wastage_penalty_rate,
                            }
                        )
                else:
                    production_vals = {
                        "name": f"{order.name}-{cursor.strftime('%Y%m%d')}",
                        "product_id": order.product_id.id,
                        "product_qty": daily_target,
                        "product_uom_id": order.product_id.uom_id.id,
                        "company_id": order.company_id.id,
                        "origin": order.so_id.name,
                        "date_start": start_dt,
                        "date_finished": end_dt,
                        "x_monthly_order_id": order.id,
                        "x_sale_order_id": order.so_id.id,
                        "x_daily_target_qty": daily_target,
                        "x_is_cooling_period": order.x_is_cooling_period,
                        "warehouse_id": routing["warehouse"].id,
                        "picking_type_id": routing["picking_type"].id,
                        "location_src_id": routing["location_src"].id,
                        "location_dest_id": routing["location_dest"].id,
                        "x_inventory_mode": routing["inventory_mode"],
                        "x_target_warehouse_id": routing["warehouse"].id,
                        "wastage_allowed_percent": order.wastage_allowed_percent,
                        "wastage_penalty_rate": order.wastage_penalty_rate,
                    }
                    production = Production.search(
                        [
                            ("name", "=", production_vals["name"]),
                            ("company_id", "=", order.company_id.id),
                        ],
                        limit=1,
                    )
                    if production:
                        production.write(production_vals)
                    else:
                        production = Production.create(production_vals)
                        production.action_confirm()

                if production.state not in ("done", "cancel"):
                    self._gear_sync_production_workorders(production, workcenter, start_dt, end_dt)
                    order._gear_ensure_daily_docket(production, start_dt, user_tz)
                processed_order = True
                cursor += timedelta(days=1)

            if processed_order:
                order.last_generated_date = generation_end
                processed_any = True
        return processed_any

    def _gear_compute_billing_summary(self):
        summary = {
            "cooling": {
                "target_qty": 0.0,
                "adjusted_target_qty": 0.0,
                "prime_output_qty": 0.0,
                "standby_qty": 0.0,
                "ngt_m3": 0.0,
                "ngt_hours": 0.0,
                "waveoff_applied_hours": 0.0,
                "waveoff_chargeable_hours": 0.0,
                "diesel_excess_litre": 0.0,
                "diesel_excess_amount": 0.0,
            },
            "normal": {
                "target_qty": 0.0,
                "adjusted_target_qty": 0.0,
                "prime_output_qty": 0.0,
                "standby_qty": 0.0,
                "ngt_m3": 0.0,
                "ngt_hours": 0.0,
                "waveoff_applied_hours": 0.0,
                "waveoff_chargeable_hours": 0.0,
                "diesel_excess_litre": 0.0,
                "diesel_excess_amount": 0.0,
            },
        }
        for order in self:
            bucket = "cooling" if order.x_is_cooling_period else "normal"
            data = summary[bucket]
            target = order.monthly_target_qty or 0.0
            prime = order.prime_output_qty or 0.0
            standby = 0.0 if order.x_is_cooling_period else (order.optimized_standby_qty or 0.0)
            ngt_m3 = order.downtime_relief_qty or 0.0
            data["target_qty"] += target
            data["adjusted_target_qty"] += order.adjusted_target_qty or target
            data["prime_output_qty"] += prime
            data["standby_qty"] += standby
            data["ngt_m3"] += ngt_m3
            data["ngt_hours"] += order.ngt_hours or 0.0
            data["waveoff_applied_hours"] += order.waveoff_hours_applied or 0.0
            data["waveoff_chargeable_hours"] += order.waveoff_hours_chargeable or 0.0
            data["diesel_excess_litre"] += order.excess_diesel_litre_total or 0.0
            data["diesel_excess_amount"] += order.excess_diesel_amount_total or 0.0
        return summary

    def _gear_get_wastage_penalty_rate(self):
        self.ensure_one()
        return self.wastage_penalty_rate or self.so_id.wastage_penalty_rate

    @api.depends("invoice_ids.move_type", "invoice_ids.state", "invoice_ids.gear_period_end")
    def _compute_invoice_stats(self):
        for order in self:
            invoices = order.invoice_ids.filtered(lambda m: m.move_type == "out_invoice" and m.state != "cancel")
            order.invoice_count = len(invoices)
            order.has_active_invoice = bool(invoices)
            last_end = False
            if invoices:
                dated = [inv.gear_period_end or inv.invoice_date for inv in invoices if (inv.gear_period_end or inv.invoice_date)]
                if dated:
                    last_end = max(dated)
            order.last_billed_end = last_end
            if order.date_end:
                order.has_remaining_invoice_window = not last_end or last_end < order.date_end
            else:
                order.has_remaining_invoice_window = True

    def _gear_prepare_debit_note_vals(self, rate, month_ref):
        self.ensure_one()
        partner = self.so_id.partner_invoice_id or self.so_id.partner_id
        product = self.so_id._gear_get_primary_product()
        account = False
        if product:
            account = product.property_account_income_id or product.categ_id.property_account_income_categ_id
        if not account:
            Account = self.env["account.account"]
            domain = []
            if "company_id" in Account._fields:
                domain.append(("company_id", "=", self.company_id.id))
            elif "company_ids" in Account._fields and self.company_id:
                domain.append(("company_ids", "in", self.company_id.id))
            if "account_type" in Account._fields:
                domain.append(("account_type", "=", "income"))
            else:
                domain.append(("user_type_id.type", "=", "income"))
            account = Account.search(domain, limit=1)
        line_vals = {
            "name": _("Over-wastage deduction for %s") % (self.display_name,),
            "quantity": self.mwo_over_wastage_qty,
            "price_unit": rate,
            "product_id": product.id if product else False,
            "account_id": account.id if account else False,
        }
        move_vals = {
            "move_type": "out_refund",
            "partner_id": partner.id,
            "invoice_date": self.date_end or fields.Date.context_today(self),
            "invoice_origin": self.so_id.name,
            "ref": month_ref,
            "invoice_payment_term_id": self.so_id.payment_term_id.id,
            "currency_id": self.company_id.currency_id.id,
            "company_id": self.company_id.id,
            "gear_monthly_order_id": self.id,
            "invoice_line_ids": [(0, 0, line_vals)],
        }
        return move_vals

    def _gear_create_over_wastage_debit_note(self):
        created = self.env["account.move"]
        for order in self:
            rate = order._gear_get_wastage_penalty_rate()
            if not rate or order.mwo_over_wastage_qty <= 0 or not order.so_id:
                continue
            partner = order.so_id.partner_invoice_id or order.so_id.partner_id
            month_label = False
            if order.date_start:
                month_label = format_date(order.env, order.date_start, date_format="MMMM yyyy")
            ref = f"{order.name} - {month_label}" if month_label else order.name
            existing_move = self.env["account.move"].search(
                [
                    ("move_type", "=", "out_refund"),
                    ("company_id", "=", order.company_id.id),
                    ("gear_monthly_order_id", "=", order.id),
                    ("partner_id", "=", partner.id),
                    ("ref", "=", ref),
                ],
                limit=1,
            )
            if existing_move:
                continue
            move_vals = order._gear_prepare_debit_note_vals(rate, ref)
            move = self.env["account.move"].create(move_vals)
            invoice_link = self.env["account.move"].search(
                [
                    ("move_type", "=", "out_invoice"),
                    ("gear_monthly_order_id", "=", order.id),
                    ("partner_id", "=", partner.id),
                    ("state", "!=", "cancel"),
                ],
                order="invoice_date desc, id desc",
                limit=1,
            )
            try:
                move.action_post()
            except Exception:
                # If posting is blocked by configuration, leave the move in draft
                pass
            if invoice_link:
                move.reversed_entry_id = invoice_link.id
            message = _(
                "Auto Debit Note generated due to over-wastage exceeding tolerance. Debit Note %s for %s."
            ) % (move.display_name, move.amount_total)
            order.message_post(body=message)
            created |= move
        return created

    @api.model
    def _cron_generate_over_wastage_debit_notes(self):
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        last_day = monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day)
        candidates = self.search(
            [
                ("date_start", ">=", start),
                ("date_start", "<=", end),
                ("company_id", "in", self.env.companies.ids),
                ("mwo_over_wastage_qty", ">", 0),
            ]
        )
        candidates._gear_create_over_wastage_debit_note()

    def _check_invoice_constraints(self):
        for order in self:
            existing_invoice = order.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state != "cancel"
            )
            last_end = False
            if existing_invoice:
                dated = [inv.gear_period_end or inv.invoice_date for inv in existing_invoice if (inv.gear_period_end or inv.invoice_date)]
                if dated:
                    last_end = max(dated)
            if last_end and order.date_end and last_end >= order.date_end:
                raise UserError(_("This Monthly Work Order is fully billed up to its end date."))

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        action["domain"] = [("gear_monthly_order_id", "=", self.id), ("move_type", "=", "out_invoice")]
        action_context = action.get("context", {}) or {}
        if isinstance(action_context, str):
            try:
                action_context = safe_eval(action_context)
            except Exception:
                action_context = {}
        if not isinstance(action_context, dict):
            action_context = {}
        action_context.update(
            {
                "default_move_type": "out_invoice",
                "search_default_gear_monthly_order_id": self.id,
                "default_gear_monthly_order_id": self.id,
            }
        )
        action["context"] = action_context
        action["name"] = _("Invoices")
        return action

    def _gear_reassign_productions_to_windows(self):
        """Move daily productions under the window that matches their execution date."""
        all_orders = self.filtered("so_id")
        if not all_orders:
            return
        all_orders = all_orders.sorted(key=lambda o: (o.date_start or fields.Date.today(), o.id))
        user_tz = all_orders[0]._gear_get_user_tz()
        for production in all_orders.mapped("production_ids"):
            if production.state in ("done", "cancel"):
                continue
            local_date = all_orders[0]._gear_datetime_to_local_date(production.date_start, user_tz)
            if not local_date:
                continue
            target = all_orders.filtered(
                lambda mo: mo.date_start and mo.date_end and mo.date_start <= local_date <= mo.date_end
            )
            if target:
                target = target[0]
                if production.x_monthly_order_id != target:
                    production.x_monthly_order_id = target.id
                if production.x_is_cooling_period != target.x_is_cooling_period:
                    production.x_is_cooling_period = target.x_is_cooling_period

    def _gear_ensure_daily_docket(self, production, start_dt, user_tz):
        """Ensure a draft docket exists for the given production day."""
        self.ensure_one()
        if not production:
            return
        local_date = self._gear_datetime_to_local_date(start_dt, user_tz)
        if not local_date:
            return

        Docket = self.env["gear.rmc.docket"]
        existing = production.x_docket_ids[:1] or Docket.search(
            [
                ("production_id", "=", production.id),
            ],
            limit=1,
        )

        workorder = production.workorder_ids[:1]
        target_workcenter = (
            (workorder.workcenter_id if workorder else False)
            or self.workcenter_id
            or self.so_id.x_workcenter_id
        )
        updates = {}
        docket = existing and existing[0] or False

        if docket:
            if docket.date != local_date:
                updates["date"] = local_date
            if workorder and docket.workorder_id != workorder:
                updates["workorder_id"] = workorder.id
            if target_workcenter and docket.workcenter_id != target_workcenter:
                updates["workcenter_id"] = target_workcenter.id
            if updates:
                docket.write(updates)
        else:
            docket_reference = f"{production.name}-{local_date.strftime('%Y%m%d')}"
            docket_vals = {
                "so_id": self.so_id.id,
                "production_id": production.id,
                "workorder_id": workorder.id if workorder else False,
                "workcenter_id": target_workcenter.id if target_workcenter else False,
                "date": local_date,
                "docket_no": Docket._gear_allocate_docket_no(self.so_id),
                "name": docket_reference,
                "source": "cron",
                "state": "draft",
                "standard_loading_minutes": self.standard_loading_minutes,
                "actual_loading_minutes": self.standard_loading_minutes,
                "diesel_burn_rate_per_hour": self.diesel_burn_rate_per_hour,
                "diesel_rate_per_litre": self.diesel_rate_per_litre,
            }
            docket = Docket.create(docket_vals)

        if docket.source == "cron" and docket.state != "draft":
            docket.write({"state": "draft"})

    def _gear_get_user_tz(self):
        self.ensure_one()
        tz_name = (
            self.env.context.get("tz")
            or (self.so_id.partner_id.tz if self.so_id and self.so_id.partner_id and self.so_id.partner_id.tz else False)
            or (self.so_id.user_id.tz if self.so_id and self.so_id.user_id and self.so_id.user_id.tz else False)
            or (self.company_id.partner_id.tz if self.company_id and self.company_id.partner_id and self.company_id.partner_id.tz else False)
            or self.env.user.tz
            or "UTC"
        )
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.utc

    @staticmethod
    def _gear_datetime_to_local_date(dt, tz):
        if not dt:
            return False
        if dt.tzinfo:
            dt_utc = dt.astimezone(pytz.utc)
        else:
            dt_utc = pytz.utc.localize(dt)
        return dt_utc.astimezone(tz).date()

    def _gear_get_day_bounds(self, day, tz):
        """Return UTC datetimes that correspond to local midnight → 23:59."""
        local_start = tz.localize(datetime.combine(day, time.min))
        local_end = tz.localize(datetime.combine(day, time(23, 59, 59)))
        return (
            local_start.astimezone(pytz.utc).replace(tzinfo=None),
            local_end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.onchange("so_id")
    def _onchange_so_id(self):
        if not self.so_id:
            return
        primary_product = self.so_id._gear_get_primary_product()
        if primary_product:
            self.product_id = primary_product
        if not self.workcenter_id and self.so_id.x_workcenter_id:
            self.workcenter_id = self.so_id.x_workcenter_id
        if self.so_id.x_inventory_mode:
            self.x_inventory_mode = self.so_id.x_inventory_mode
        if not self.x_real_warehouse_id and self.so_id.x_real_warehouse_id:
            self.x_real_warehouse_id = self.so_id.x_real_warehouse_id
        self.standard_loading_minutes = self.so_id.standard_loading_minutes
        self.diesel_burn_rate_per_hour = self.so_id.diesel_burn_rate_per_hour
        self.diesel_rate_per_litre = self.so_id.diesel_rate_per_litre
        contract_start = self.so_id.x_contract_start
        if contract_start:
            start = contract_start.replace(day=1)
            last_day = monthrange(start.year, start.month)[1]
            end = start.replace(day=last_day)
            self.date_start = start
            self.date_end = end

    @api.onchange("date_start")
    def _onchange_date_start(self):
        if self.date_start and (not self.date_end or self.date_end < self.date_start):
            last_day = monthrange(self.date_start.year, self.date_start.month)[1]
            self.date_end = self.date_start.replace(day=last_day)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for order, vals in zip(records, vals_list):
            if not order.product_id and order.so_id:
                product = order.so_id._gear_get_primary_product()
                if product:
                    order.product_id = product
            if not order.workcenter_id and order.so_id.x_workcenter_id:
                order.workcenter_id = order.so_id.x_workcenter_id
            if not order.date_start and order.so_id.x_contract_start:
                start = order.so_id.x_contract_start.replace(day=1)
                last_day = monthrange(start.year, start.month)[1]
                order.date_start = start
                order.date_end = order.date_end or start.replace(day=last_day)
            if not vals.get("x_inventory_mode") and order.so_id.x_inventory_mode:
                order.x_inventory_mode = order.so_id.x_inventory_mode
            if not vals.get("x_real_warehouse_id") and order.so_id.x_real_warehouse_id:
                order.x_real_warehouse_id = order.so_id.x_real_warehouse_id
            if vals.get("standard_loading_minutes") is None:
                order.standard_loading_minutes = order.so_id.standard_loading_minutes
            if vals.get("diesel_burn_rate_per_hour") is None:
                order.diesel_burn_rate_per_hour = order.so_id.diesel_burn_rate_per_hour
            if vals.get("diesel_rate_per_litre") is None:
                order.diesel_rate_per_litre = order.so_id.diesel_rate_per_litre
            if vals.get("wastage_allowed_percent") is None:
                order.wastage_allowed_percent = order.so_id.wastage_allowed_percent
            if vals.get("wastage_penalty_rate") is None:
                order.wastage_penalty_rate = order.so_id.wastage_penalty_rate
        return records

    def _gear_sync_production_workorders(self, production, workcenter, start_dt, end_dt):
        """Ensure only the current chunk work order exists while queueing the remaining ones."""
        Workorder = self.env["mrp.workorder"]
        param = self.env["ir.config_parameter"].sudo().get_param("gear_on_rent.workorder_max_qty", "7.0")
        try:
            max_chunk = float(param)
        except (TypeError, ValueError):
            max_chunk = 7.0
        if max_chunk <= 0:
            max_chunk = 7.0

        total_qty = float(production.product_qty or 0.0)
        chunks = self._gear_split_quantity(total_qty, max_chunk)

        base_name = f"{production.name} / {workcenter.display_name}"

        entries = []
        for idx, qty in enumerate(chunks):
            seq = idx + 1
            entries.append(
                {
                    "seq": seq,
                    "qty": qty,
                    "name": base_name if len(chunks) == 1 else f"{base_name} ({seq})",
                    "date_start": fields.Datetime.to_string(start_dt) if start_dt else False,
                    "date_finished": fields.Datetime.to_string(end_dt) if end_dt else False,
                }
            )

        max_seq = entries[-1]["seq"] if entries else 0
        done_workorders = production.workorder_ids.filtered(lambda wo: wo.state == "done")
        known_sequences = sorted(seq for seq in done_workorders.mapped("gear_chunk_sequence") if seq)
        if known_sequences:
            next_seq = known_sequences[-1] + 1
        else:
            next_seq = len(done_workorders) + 1

        current_entry = (
            next((entry for entry in entries if entry["seq"] == next_seq), None)
            if next_seq and next_seq <= max_seq
            else None
        )
        pending_entries = [entry for entry in entries if current_entry and entry["seq"] > current_entry["seq"]]
        production.x_pending_workorder_chunks = pending_entries

        active_candidates = production.workorder_ids.filtered(lambda wo: wo.state not in ("done", "cancel"))
        active = (
            active_candidates.filtered(lambda wo: wo.gear_chunk_sequence == next_seq) if current_entry else self.env["mrp.workorder"]
        )
        extras = (active_candidates - active) if active else active_candidates

        if current_entry:
            vals = {
                "name": current_entry["name"],
                "production_id": production.id,
                "workcenter_id": workcenter.id,
                "qty_production": current_entry["qty"],
                "date_start": start_dt,
                "date_finished": end_dt,
                "sequence": current_entry["seq"],
                "gear_chunk_sequence": current_entry["seq"],
                "gear_qty_planned": current_entry["qty"],
            }
            if active:
                target = active[:1]
                if target.state == "progress":
                    safe_vals = dict(vals)
                    safe_vals.pop("date_start", None)
                    safe_vals.pop("date_finished", None)
                    target.write(safe_vals)
                elif target.state not in ("done", "cancel"):
                    target.write(vals)
            else:
                Workorder.create(vals)

        for wo in extras:
            if wo.state in ("done", "cancel", "progress"):
                continue
            if wo.gear_docket_ids:
                try:
                    wo.gear_docket_ids.unlink()
                except Exception:
                    _logger.info(
                        "Skipping removal of work order %s due to linked dockets.",
                        wo.display_name,
                    )
                    continue
            try:
                wo.unlink()
            except Exception:
                _logger.info("Failed to remove surplus work order %s", wo.display_name)

    @staticmethod
    def _gear_split_quantity(total_qty, max_chunk):
        """Split quantity into chunks capped by max_chunk, returning at least one entry."""
        if max_chunk <= 0:
            return [round(total_qty or 0.0, 2)]
        total_qty = round(total_qty or 0.0, 2)
        if total_qty <= 0:
            return [0.0]

        parts = int(ceil(total_qty / max_chunk))
        quantities = []
        remaining = total_qty
        for _ in range(parts):
            chunk = max_chunk if remaining > max_chunk else remaining
            quantities.append(round(chunk, 2))
            remaining = round(remaining - chunk, 2)
        # Correct final chunk to ensure sum equals total
        adjustment = round(total_qty - sum(quantities), 2)
        if quantities:
            quantities[-1] = round(quantities[-1] + adjustment, 2)
        return quantities or [0.0]

    @api.model
    def _cron_schedule_due_orders(self):
        """Scheduled task to generate daily orders as windows progress."""
        today = fields.Date.context_today(self)
        domain = [
            ("state", "!=", "done"),
            ("date_start", "<=", today),
            ("date_end", ">=", today),
        ]
        orders = self.search(domain)
        if not orders:
            return
        for order in orders:
            try:
                order.action_schedule_orders(until_date=today)
            except Exception:
                _logger.exception("Failed to schedule monthly order %s", order.display_name)

    def action_open_prepare_invoice(self):
        self.ensure_one()
        self._check_invoice_constraints()
        return {
            "type": "ir.actions.act_window",
            "res_model": "gear.prepare.invoice.mrp",
            "view_mode": "form",
            "view_id": self.env.ref("gear_on_rent.view_prepare_invoice_from_mrp_form").id,
            "target": "new",
            "context": {
                "default_monthly_order_id": self.id,
                "default_invoice_date": fields.Date.context_today(self),
            },
        }
