# Review findings before rework (annual reconciliation gaps):
# 1) No annual reconciliation models or FY grid exist; there is no storage for MGQ x12 vs actual or bank rollovers.
# 2) No snapshot of SO variable table on reconciliation artifacts, leaving policy and billing disconnected from contract rates.
# 3) No reconciliation policy engine (bill_now / forfeit / rollover) or invoice linkage to settle bank balances.
# 4) No monthly child lines to hold MGQ targets, bank add/pull/closing, NGT conversion, or cooling flags per month.
# 5) No loaders to aggregate MWOs/MOs/dockets by fiscal window, apply cooling logic, or enforce bank pull limits.
# 6) No portal/QWeb/report hooks or exports for customers to view annual reconciliation outcomes.

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GearRmcAnnualReconciliation(models.Model):
    """Annual reconciliation for MGQ-driven RMC contracts."""

    _name = "gear.rmc.annual.reconciliation"
    _description = "Gear RMC Annual Reconciliation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "fiscal_year_start desc, name"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("gear.rmc.annual.reconciliation")
        or _("New"),
        tracking=True,
    )
    so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract / SO",
        required=True,
        tracking=True,
        domain=[("state", "in", ["sale", "done"])],
    )
    fiscal_year_start = fields.Date(string="FY Start", required=True, tracking=True)
    fiscal_year_end = fields.Date(string="FY End", required=True, tracking=True)
    bank_opening_qty = fields.Float(string="Opening Bank", digits=(16, 2), tracking=True)
    bank_closing_qty = fields.Float(
        string="Closing Bank", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    bank_added_total = fields.Float(
        string="Bank Added (FY)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    bank_pulled_total = fields.Float(
        string="Bank Pulled (FY)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    mgq_annual_target = fields.Float(
        string="MGQ (Annual)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    mgq_annual_actual = fields.Float(
        string="Prime Actual (FY)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    excess_total = fields.Float(
        string="Excess After Bank (FY)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    ngt_total_qty = fields.Float(
        string="NGT Qty (m³)", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    loto_total_hours = fields.Float(
        string="LOTO Chargeable Hours", digits=(16, 2), tracking=True, compute="_compute_totals", store=True
    )
    policy = fields.Selection(
        selection=[
            ("bill_now", "Bill Remaining Bank"),
            ("forfeit", "Forfeit Bank"),
            ("rollover", "Rollover Bank"),
        ],
        string="Reconciliation Policy",
        default="bill_now",
        tracking=True,
    )
    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Reconciliation Invoice",
        tracking=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="so_id.company_id",
        store=True,
        readonly=True,
    )
    version = fields.Integer(string="Version", default=1, tracking=True)
    regenerated_on = fields.Datetime(string="Regenerated On", tracking=True)
    line_ids = fields.One2many(
        comodel_name="gear.rmc.annual.reconciliation.line",
        inverse_name="reconciliation_id",
        string="Monthly Lines",
    )

    # Snapshot of contract variables (enforce variable-based billing)
    prime_rate = fields.Float(string="Prime Rate", digits=(16, 2), tracking=True)
    optimize_rate = fields.Float(string="Optimize Rate", digits=(16, 2), tracking=True)
    ngt_rate = fields.Float(string="NGT Rate", digits=(16, 2), tracking=True)
    excess_rate = fields.Float(string="Excess Rate", digits=(16, 2), tracking=True)
    mgq_monthly = fields.Float(string="MGQ Monthly", digits=(16, 2), tracking=True)
    cooling_months = fields.Integer(string="Cooling Months", tracking=True)
    cooling_end = fields.Datetime(string="Cooling Ends", tracking=True)
    loto_waveoff_hours = fields.Float(string="LOTO Wave-Off Hours", digits=(16, 2), tracking=True)
    bank_pull_limit = fields.Float(string="Bank Pull Limit", digits=(16, 2), tracking=True)
    ngt_hourly_prorata_factor = fields.Float(
        string="NGT Hourly Prorata Factor",
        digits=(16, 4),
        tracking=True,
    )
    variable_version = fields.Char(
        string="Variable Snapshot Version",
        help="Optional checksum/version of the SO variable table used for this reconciliation.",
    )

    def _get_contract_product(self):
        self.ensure_one()
        product = self.so_id.order_line[:1].product_id
        if not product:
            raise UserError(_("Please configure at least one product on the contract to raise reconciliation lines."))
        return product

    def _snapshot_contract_variables(self):
        for rec in self:
            order = rec.so_id
            rec.update(
                {
                    "prime_rate": order.prime_rate,
                    "optimize_rate": order.optimize_rate,
                    "ngt_rate": order.ngt_rate,
                    "excess_rate": order.excess_rate,
                    "mgq_monthly": order.mgq_monthly,
                    "cooling_months": order.cooling_months,
                    "cooling_end": order.x_cooling_end,
                    "loto_waveoff_hours": order.x_loto_waveoff_hours,
                    "bank_pull_limit": order.bank_pull_limit,
                    "ngt_hourly_prorata_factor": order.ngt_hourly_prorata_factor,
                    "variable_version": order.write_date and order.write_date.strftime("%Y%m%d%H%M%S"),
                }
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._snapshot_contract_variables()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(
            field in vals
            for field in [
                "prime_rate",
                "optimize_rate",
                "ngt_rate",
                "excess_rate",
                "mgq_monthly",
                "cooling_months",
                "cooling_end",
                "loto_waveoff_hours",
                "bank_pull_limit",
                "ngt_hourly_prorata_factor",
            ]
        ):
            self._compute_totals()
        return res

    def action_regenerate_lines(self):
        for rec in self:
            rec._snapshot_contract_variables()
            rec._load_monthly_lines()
            rec.version += 1
            rec.regenerated_on = fields.Datetime.now()
            rec._compute_totals()
            rec.state = "in_progress"
        return True

    def _load_monthly_lines(self):
        self.ensure_one()
        lines = []
        running_bank = self.bank_opening_qty or 0.0
        mwo_domain = [
            ("so_id", "=", self.so_id.id),
            ("date_start", ">=", self.fiscal_year_start),
            ("date_end", "<=", self.fiscal_year_end),
        ]
        monthly_orders = self.env["gear.rmc.monthly.order"].search(mwo_domain, order="date_start asc")
        line_model = self.env["gear.rmc.annual.reconciliation.line"]
        # drop old lines
        self.line_ids.unlink()
        for monthly in monthly_orders:
            mgq_target = monthly.adjusted_target_qty or monthly.monthly_target_qty or self.mgq_monthly
            prime_qty = monthly.prime_output_qty
            bank_add = 0.0
            bank_pull = 0.0
            excess_after_bank = 0.0
            bank_limit = monthly.bank_pull_limit or self.bank_pull_limit
            cooling = bool(monthly.x_is_cooling_period)
            ngt_qty = monthly.downtime_relief_qty
            if not cooling:
                bank_add = max((mgq_target or 0.0) - (prime_qty or 0.0), 0.0)
            gross_excess = max((prime_qty or 0.0) - (mgq_target or 0.0), 0.0)
            available_bank = running_bank + bank_add
            if gross_excess > 0.0 and available_bank > 0.0:
                bank_pull = min(gross_excess, available_bank, bank_limit or gross_excess)
            excess_after_bank = gross_excess - bank_pull
            bank_closing = available_bank - bank_pull
            running_bank = bank_closing
            ngt_hours = monthly.ngt_hours
            ngt_factor = monthly.ngt_hourly_prorata_factor or self.ngt_hourly_prorata_factor or 0.0
            ngt_converted = (ngt_hours or 0.0) * (ngt_factor or 0.0)
            lines.append(
                line_model.new(
                    {
                        "reconciliation_id": self.id,
                        "month_name": monthly.date_start.strftime("%b %Y") if monthly.date_start else "",
                        "mwo_id": monthly.id,
                        "mgq_target": mgq_target,
                        "prime_output": prime_qty,
                        "optimize_add": bank_add,
                        "bank_add": bank_add,
                        "bank_pull": bank_pull,
                        "bank_closing": bank_closing,
                        "excess_after_bank": excess_after_bank,
                        "ngt_qty": ngt_converted,
                        "ngt_hours": ngt_hours,
                        "loto_chargeable": monthly.waveoff_hours_chargeable,
                        "cooling_flag": cooling,
                        "prime_rate": monthly.prime_rate or self.prime_rate,
                        "optimize_rate": monthly.optimize_rate or self.optimize_rate,
                        "ngt_rate": monthly.ngt_rate or self.ngt_rate,
                        "excess_rate": monthly.excess_rate or self.excess_rate,
                        "raw_production_ids": [(6, 0, monthly.production_ids.ids)],
                        "raw_docket_ids": [(6, 0, monthly.docket_ids.ids)],
                    }
                )
            )
        if lines:
            self.line_ids = [fields.Command.create(line._convert_to_write(line._cache)) for line in lines]
        else:
            self.line_ids = False

    @api.depends(
        "line_ids.bank_add",
        "line_ids.bank_pull",
        "line_ids.prime_output",
        "line_ids.excess_after_bank",
        "line_ids.ngt_qty",
        "line_ids.loto_chargeable",
        "mgq_monthly",
        "bank_opening_qty",
    )
    def _compute_totals(self):
        for rec in self:
            annual_mgq = sum(rec.line_ids.mapped("mgq_target")) or ((rec.mgq_monthly or 0.0) * 12.0)
            bank_added_total = sum(rec.line_ids.mapped("bank_add"))
            bank_pulled_total = sum(rec.line_ids.mapped("bank_pull"))
            closing_bank = rec.bank_opening_qty + bank_added_total - bank_pulled_total
            rec.update(
                {
                    "mgq_annual_target": annual_mgq,
                    "mgq_annual_actual": sum(rec.line_ids.mapped("prime_output")),
                    "bank_added_total": bank_added_total,
                    "bank_pulled_total": bank_pulled_total,
                    "bank_closing_qty": closing_bank,
                    "excess_total": sum(rec.line_ids.mapped("excess_after_bank")),
                    "ngt_total_qty": sum(rec.line_ids.mapped("ngt_qty")),
                    "loto_total_hours": sum(rec.line_ids.mapped("loto_chargeable")),
                }
            )

    def action_apply_policy(self):
        for rec in self:
            if rec.invoice_id:
                raise UserError(_("A reconciliation invoice is already linked."))
            if rec.policy == "bill_now":
                rate = rec.optimize_rate or rec.prime_rate
                rec.invoice_id = rec._create_policy_invoice(amount_qty=rec.bank_closing_qty, rate=rate)
            elif rec.policy == "forfeit":
                rec._log_policy_note(_("Bank balance forfeited; no billing generated."))
                rec.bank_closing_qty = 0.0
            elif rec.policy == "rollover":
                rec._log_policy_note(_("Bank balance rolled over to next fiscal year."))
            else:
                raise UserError(_("Please select a reconciliation policy."))
            rec.state = "closed"
        return True

    def _log_policy_note(self, message):
        if message:
            for rec in self:
                rec.message_post(body=message)

    def _create_policy_invoice(self, amount_qty, rate):
        self.ensure_one()
        if not amount_qty:
            raise UserError(_("Nothing to bill for this reconciliation."))
        product = self._get_contract_product()
        move_vals = {
            "move_type": "out_invoice",
            "partner_id": self.so_id.partner_id.id,
            "invoice_origin": self.name,
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": product.id,
                    "quantity": amount_qty,
                    "price_unit": rate,
                    "name": _("Annual reconciliation bank pull for %s") % (self.so_id.name or self.name),
                })
            ],
        }
        invoice = self.env["account.move"].create(move_vals)
        self.message_post(body=_("Reconciliation invoice %s created via policy %s.") % (invoice.name, self.policy))
        return invoice


class GearRmcAnnualReconciliationLine(models.Model):
    """Monthly detail line inside annual reconciliation."""

    _name = "gear.rmc.annual.reconciliation.line"
    _description = "Gear RMC Annual Reconciliation Line"
    _order = "id"

    reconciliation_id = fields.Many2one(
        comodel_name="gear.rmc.annual.reconciliation",
        string="Annual Reconciliation",
        required=True,
        ondelete="cascade",
    )
    month_name = fields.Char(string="Month")
    mwo_id = fields.Many2one("gear.rmc.monthly.order", string="Monthly Work Order")
    mgq_target = fields.Float(string="MGQ Target", digits=(16, 2))
    prime_output = fields.Float(string="Prime Output", digits=(16, 2))
    optimize_add = fields.Float(string="Optimize Add", digits=(16, 2))
    bank_add = fields.Float(string="Bank Add", digits=(16, 2))
    bank_pull = fields.Float(string="Bank Pull", digits=(16, 2))
    bank_closing = fields.Float(string="Closing Bank", digits=(16, 2))
    excess_after_bank = fields.Float(string="Excess After Bank", digits=(16, 2))
    ngt_qty = fields.Float(string="NGT Qty (m³)", digits=(16, 2))
    ngt_hours = fields.Float(string="NGT Hours", digits=(16, 2))
    loto_chargeable = fields.Float(string="Chargeable LOTO Hours", digits=(16, 2))
    cooling_flag = fields.Boolean(string="Cooling Month")
    prime_rate = fields.Float(string="Prime Rate", digits=(16, 2))
    optimize_rate = fields.Float(string="Optimize Rate", digits=(16, 2))
    ngt_rate = fields.Float(string="NGT Rate", digits=(16, 2))
    excess_rate = fields.Float(string="Excess Rate", digits=(16, 2))
    raw_production_ids = fields.Many2many(
        comodel_name="mrp.production",
        string="Daily MOs",
        relation="gear_rmc_recon_mo_rel",
        column1="recon_line_id",
        column2="production_id",
    )
    raw_docket_ids = fields.Many2many(
        comodel_name="gear.rmc.docket",
        string="Dockets",
        relation="gear_rmc_recon_docket_rel",
        column1="recon_line_id",
        column2="docket_id",
    )

    @api.onchange("prime_output", "mgq_target", "bank_add", "bank_pull")
    def _onchange_bank_math(self):
        for line in self:
            available_bank = (line.bank_add or 0.0) + (line.bank_closing or 0.0)
            gross_excess = max((line.prime_output or 0.0) - (line.mgq_target or 0.0), 0.0)
            line.bank_pull = min(gross_excess, available_bank)
            line.excess_after_bank = gross_excess - line.bank_pull
            line.bank_closing = available_bank - line.bank_pull
