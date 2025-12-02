from datetime import timedelta
import base64
import logging

from odoo import _, api, fields, models
from odoo.tools import format_date, format_datetime

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    """Extend MOs with Gear On Rent scheduling metadata."""

    _inherit = "mrp.production"

    x_monthly_order_id = fields.Many2one(
        comodel_name="gear.rmc.monthly.order",
        string="Monthly Work Order",
        index=True,
        ondelete="set null",
    )
    x_sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract / SO",
        index=True,
        ondelete="set null",
        help="Contract responsible for this production order.",
    )
    x_daily_target_qty = fields.Float(
        string="Daily MGQ",
        digits=(16, 2),
        help="Baseline MGQ allocated to this daily manufacturing order.",
    )
    x_relief_qty = fields.Float(
        string="Relief Quantity",
        digits=(16, 2),
        help="Quantity relieved by NGT/LOTO approvals.",
    )
    x_adjusted_target_qty = fields.Float(
        string="Adjusted MGQ",
        digits=(16, 2),
        compute="_compute_adjusted_target_qty",
        store=True,
    )
    x_ngt_hours = fields.Float(
        string="NGT Relief (Hours)",
        digits=(16, 2),
        default=0.0,
    )
    x_loto_hours = fields.Float(
        string="LOTO (Hours)",
        digits=(16, 2),
        default=0.0,
    )
    x_waveoff_hours_applied = fields.Float(
        string="Wave-Off Applied (Hours)",
        digits=(16, 2),
        default=0.0,
    )
    x_waveoff_hours_chargeable = fields.Float(
        string="Wave-Off Chargeable (Hours)",
        digits=(16, 2),
        default=0.0,
    )
    x_is_cooling_period = fields.Boolean(
        string="Cooling Period Window",
        help="Indicates the parent monthly work order is within the cooling period.",
    )
    x_inventory_mode = fields.Selection(
        selection=[
            ("without_inventory", "Without Inventory"),
            ("with_inventory", "With Inventory"),
        ],
        string="Inventory Mode",
        default="without_inventory",
        help="Snapshot of the inventory routing mode at MO creation time.",
    )
    x_target_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Inventory Warehouse",
        help="Warehouse resolved for this MO based on the sales order inventory mode.",
    )
    company_currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="company_id.currency_id",
        readonly=True,
        string="Company Currency",
    )
    prime_rate = fields.Float(
        string="Prime Rate Snapshot",
        digits=(16, 2),
        help="Prime production rate captured from the parent sales order variables.",
    )
    optimize_rate = fields.Float(
        string="Optimize Rate Snapshot",
        digits=(16, 2),
        help="Optimize standby rate captured from the parent sales order variables.",
    )
    ngt_rate = fields.Float(
        string="NGT Rate Snapshot",
        digits=(16, 2),
        help="NGT rate captured from the parent sales order variables.",
    )
    excess_rate = fields.Float(
        string="Excess Rate Snapshot",
        digits=(16, 2),
        help="Excess production rate captured from the parent sales order variables.",
    )
    mgq_monthly = fields.Float(
        string="MGQ (Monthly) Snapshot",
        digits=(16, 2),
        help="Variable-based monthly MGQ captured for this manufacturing order window.",
    )
    wastage_allowed_percent = fields.Float(
        string="Allowed Wastage (%)",
        digits=(16, 4),
        help="Scrap tolerance percent snapshot from the parent monthly order or sales order.",
    )
    wastage_penalty_rate = fields.Monetary(
        string="Wastage Penalty Rate",
        currency_field="company_currency_id",
        help="Penalty rate snapshot used to value over-wastage quantities (copied from SO/MWO).",
    )
    cooling_months = fields.Integer(
        string="Cooling Months Snapshot",
        help="Cooling period length captured when the manufacturing order was created.",
    )
    loto_waveoff_hours = fields.Float(
        string="LOTO Wave-Off Allowance Snapshot",
        digits=(16, 2),
        help="Wave-off allowance captured from the sales order variables.",
    )
    bank_pull_limit = fields.Float(
        string="Bank Pull Limit Snapshot",
        digits=(16, 2),
        help="Maximum allowed bank pull captured from the sales order variables.",
    )
    ngt_hourly_prorata_factor = fields.Float(
        string="NGT Hourly Prorata Factor Snapshot",
        digits=(16, 4),
        help="Hourly to m³ conversion factor captured for NGT relief calculations.",
    )
    x_docket_ids = fields.One2many(
        comodel_name="gear.rmc.docket",
        inverse_name="production_id",
        string="Dockets",
    )
    x_prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        compute="_compute_prime_output_qty",
        store=True,
        digits=(16, 2),
    )
    x_optimized_standby_qty = fields.Float(
        string="Optimized Standby (m³)",
        compute="_compute_optimized_standby_qty",
        store=True,
        digits=(16, 2),
    )
    x_runtime_minutes = fields.Float(
        string="Runtime (min)",
        compute="_compute_runtime_idle_minutes",
        store=True,
        digits=(16, 2),
    )
    x_idle_minutes = fields.Float(
        string="Idle (min)",
        compute="_compute_runtime_idle_minutes",
        store=True,
        digits=(16, 2),
    )
    actual_scrap_qty = fields.Float(
        string="Actual Scrap (m³)",
        compute="_compute_actual_scrap_qty",
        store=True,
        digits=(16, 2),
        help="Total scrap recorded across all work orders for this manufacturing order.",
    )
    prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        related="x_prime_output_qty",
        store=True,
        readonly=True,
    )
    wastage_allowed_qty = fields.Float(
        string="Allowed Wastage (m³)",
        compute="_compute_wastage_kpis",
        store=True,
        digits=(16, 2),
        help="Quantity of scrap permitted under the wastage tolerance.",
    )
    over_wastage_qty = fields.Float(
        string="Over Wastage (m³)",
        compute="_compute_wastage_kpis",
        store=True,
        digits=(16, 2),
        help="Scrap above the allowed tolerance.",
    )
    deduction_qty = fields.Float(
        string="Deduction Quantity (m³)",
        compute="_compute_wastage_kpis",
        store=True,
        digits=(16, 2),
        help="Quantity to be used for wastage-based deductions.",
    )
    x_pending_workorder_chunks = fields.Json(
        string="Queued Work Order Chunks",
        default=list,
        help="Remaining work order payloads (quantity/date) to instantiate after the current chunk completes.",
    )

    _sql_constraints = [
        (
            "check_relief_not_negative",
            "CHECK(x_relief_qty >= 0)",
            "Relief quantity cannot be negative.",
        ),
    ]

    @api.depends("x_daily_target_qty", "x_relief_qty")
    def _compute_adjusted_target_qty(self):
        for production in self:
            base = production.x_daily_target_qty or 0.0
            relief = min(base, production.x_relief_qty or 0.0)
            production.x_adjusted_target_qty = max(base - relief, 0.0)

    @api.depends("x_docket_ids.qty_m3")
    def _compute_prime_output_qty(self):
        for production in self:
            client_dockets = production._gear_client_dockets()
            production.x_prime_output_qty = sum(client_dockets.mapped("qty_m3"))

    @api.depends("x_adjusted_target_qty", "x_prime_output_qty")
    def _compute_optimized_standby_qty(self):
        for production in self:
            adjusted = production.x_adjusted_target_qty or 0.0
            prime = production.x_prime_output_qty or 0.0
            production.x_optimized_standby_qty = max(adjusted - prime, 0.0)

    @api.depends("x_docket_ids.runtime_minutes", "x_docket_ids.idle_minutes")
    def _compute_runtime_idle_minutes(self):
        for production in self:
            client_dockets = production._gear_client_dockets()
            production.x_runtime_minutes = sum(client_dockets.mapped("runtime_minutes"))
            production.x_idle_minutes = sum(client_dockets.mapped("idle_minutes"))

    @api.depends("workorder_ids.scrap_qty")
    def _compute_actual_scrap_qty(self):
        for production in self:
            production.actual_scrap_qty = sum(production.workorder_ids.mapped("scrap_qty"))

    @api.depends("prime_output_qty", "wastage_allowed_percent", "actual_scrap_qty")
    def _compute_wastage_kpis(self):
        for production in self:
            prime_output = production.prime_output_qty or 0.0
            allowed_percent = production.wastage_allowed_percent or 0.0
            allowed_qty = (prime_output * allowed_percent) / 100.0 if allowed_percent else 0.0
            actual_scrap = production.actual_scrap_qty or 0.0
            over_wastage = max(actual_scrap - allowed_qty, 0.0)
            production.wastage_allowed_qty = round(allowed_qty, 2)
            production.over_wastage_qty = round(over_wastage, 2)
            production.deduction_qty = production.over_wastage_qty

    @api.model_create_multi
    def create(self, vals_list):
        productions = super().create(vals_list)
        for production, vals in zip(productions, vals_list):
            if vals.get("wastage_allowed_percent") is None:
                percent = False
                if production.x_monthly_order_id:
                    percent = production.x_monthly_order_id.wastage_allowed_percent
                elif production.x_sale_order_id:
                    percent = production.x_sale_order_id.wastage_allowed_percent
                production.wastage_allowed_percent = percent
            if vals.get("wastage_penalty_rate") is None:
                rate = False
                if production.x_monthly_order_id:
                    rate = production.x_monthly_order_id.wastage_penalty_rate
                elif production.x_sale_order_id:
                    rate = production.x_sale_order_id.wastage_penalty_rate
                production.wastage_penalty_rate = rate
        return productions

    def gear_allocate_relief_hours(self, hours, reason):
        """Apply downtime hours to the MO and adjust MGQ relief when applicable."""
        if not hours:
            return
        for production in self:
            qty_relief = production._gear_hours_to_qty(hours)
            if qty_relief:
                production._gear_apply_relief_qty(qty_relief)
            if reason == "ngt":
                production.x_ngt_hours = (production.x_ngt_hours or 0.0) + hours
            elif reason == "loto":
                production.x_loto_hours = (production.x_loto_hours or 0.0) + hours
            else:
                # generic relief path already handled by qty_relief conversion
                continue

    def _gear_apply_relief_qty(self, qty_relief):
        if not qty_relief:
            return
        for production in self:
            base = production.x_daily_target_qty or 0.0
            current = production.x_relief_qty or 0.0
            new_relief = max(current + qty_relief, 0.0)
            if base:
                new_relief = min(new_relief, base)
            production.x_relief_qty = new_relief

    def gear_apply_loto_waveoff(self, applied_hours, chargeable_hours):
        for production in self:
            production.x_waveoff_hours_applied = (production.x_waveoff_hours_applied or 0.0) + applied_hours
            production.x_waveoff_hours_chargeable = (
                production.x_waveoff_hours_chargeable or 0.0
            ) + chargeable_hours

    def action_print_daily_report(self):
        """Open the daily MO report for this production order and log it on the monthly order."""
        self.ensure_one()
        report = self.env.ref("gear_on_rent.action_report_daily_mo", raise_if_not_found=False)
        if not report:
            raise UserError(_("Daily MO report configuration is missing."))

        attachment = False
        try:
            pdf_content, report_type = report._render_qweb_pdf(report.id, res_ids=self.ids)
        except Exception:
            pdf_content = False
        if pdf_content:
            filename = "%s - Daily MO.pdf" % (self.name or _("MO"))
            attachment_vals = {
                "name": filename.replace("/", "_"),
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "mimetype": "application/pdf",
                "res_model": self._name,
                "res_id": self.id,
            }
            attachment = self.env["ir.attachment"].create(attachment_vals)

        monthly = self.x_monthly_order_id
        template = self.env.ref("gear_on_rent.mail_template_daily_mo_report", raise_if_not_found=False)
        if template and (not monthly or monthly.x_auto_email_daily):
            email_values = {}
            if attachment:
                email_values["attachment_ids"] = [(4, attachment.id)]
            template.send_mail(self.id, force_send=True, email_values=email_values)

        if monthly:
            message = _("Daily report generated for %(mo)s.") % {"mo": self.display_name}
            monthly.message_post(body=message, attachment_ids=attachment and [attachment.id] or False)

        return report.report_action(self)

    def _gear_hours_to_qty(self, hours):
        self.ensure_one()
        target = self.x_daily_target_qty or 0.0
        if not target:
            return 0.0
        # Assume uniform production across the day; convert hours to MGQ relief.
        return target * (hours / 24.0)

    def _gear_get_daily_report_payload(self):
        """Return a payload compatible with the month-end template for a single MO."""
        self.ensure_one()
        start_dt = False
        if self.date_start:
            start_dt = fields.Datetime.context_timestamp(self, self.date_start)
        start_date = start_dt.date() if start_dt else fields.Date.context_today(self)

        monthly_order = self.x_monthly_order_id
        if not monthly_order and self.x_sale_order_id and start_date:
            monthly_order = (
                self.env["gear.rmc.monthly.order"]
                .search(
                    [
                        ("so_id", "=", self.x_sale_order_id.id),
                        ("date_start", "<=", start_date),
                        ("date_end", ">=", start_date),
                    ],
                    limit=1,
                )
            )

        contract = self.x_sale_order_id or (monthly_order and monthly_order.so_id)
        customer = contract.partner_id if contract else False

        target_qty = self.x_daily_target_qty or self.product_qty or 0.0
        adjusted_qty = self.x_adjusted_target_qty or target_qty
        workorder_output = sum(self.workorder_ids.mapped("qty_produced"))
        prime_output = self.x_prime_output_qty or workorder_output or (self.qty_produced or 0.0)
        is_cooling = bool(self.x_is_cooling_period or (monthly_order and monthly_order.x_is_cooling_period))
        standby_qty = self.x_optimized_standby_qty or max(adjusted_qty - prime_output, 0.0)
        if is_cooling:
            standby_qty = 0.0
        ngt_hours = self.x_ngt_hours or 0.0
        relief_qty = self.x_relief_qty or 0.0
        waveoff_applied = self.x_waveoff_hours_applied or 0.0
        waveoff_chargeable = self.x_waveoff_hours_chargeable or 0.0
        total_waveoff = waveoff_applied + waveoff_chargeable
        allowed_wastage_qty = self.wastage_allowed_qty or 0.0
        actual_scrap_qty = self.actual_scrap_qty or 0.0
        over_wastage_qty = self.over_wastage_qty or 0.0
        deduction_qty = self.deduction_qty or 0.0
        monthly_target_qty = monthly_order.monthly_target_qty if monthly_order else contract.x_monthly_mgq if contract else 0.0
        monthly_adjusted = monthly_order.adjusted_target_qty if monthly_order else monthly_target_qty
        cumulative_prime = monthly_order.prime_output_qty if monthly_order else prime_output
        cumulative_standby = monthly_order.optimized_standby_qty if monthly_order else standby_qty
        cumulative_ngt = monthly_order.downtime_relief_qty if monthly_order else relief_qty
        cumulative_ngt_hours = monthly_order.ngt_hours if monthly_order else ngt_hours
        cumulative_waveoff = monthly_order.waveoff_hours_applied if monthly_order else waveoff_applied
        cumulative_waveoff_chargeable = monthly_order.waveoff_hours_chargeable if monthly_order else waveoff_chargeable

        cooling_totals = {
            "target_qty": 0.0,
            "adjusted_target_qty": 0.0,
            "prime_output_qty": 0.0,
            "standby_qty": 0.0,
            "ngt_m3": 0.0,
            "ngt_hours": 0.0,
            "waveoff_applied_hours": 0.0,
            "waveoff_chargeable_hours": 0.0,
        }
        normal_totals = {
            "target_qty": 0.0,
            "adjusted_target_qty": 0.0,
            "prime_output_qty": 0.0,
            "standby_qty": 0.0,
            "ngt_m3": 0.0,
            "ngt_hours": 0.0,
            "waveoff_applied_hours": 0.0,
            "waveoff_chargeable_hours": 0.0,
        }

        bucket_data = cooling_totals if is_cooling else normal_totals
        bucket_data.update(
            {
                "target_qty": target_qty,
                "adjusted_target_qty": adjusted_qty,
                "prime_output_qty": prime_output,
                "standby_qty": 0.0 if is_cooling else standby_qty,
                "ngt_m3": relief_qty,
                "ngt_hours": ngt_hours,
                "waveoff_applied_hours": waveoff_applied,
                "waveoff_chargeable_hours": waveoff_chargeable,
            }
        )

        docket_records = self.x_docket_ids.sorted(key=lambda d: (d.date or fields.Date.today(), d.id))
        docket_rows = [
            {
                "docket_no": docket.docket_no,
                "date": format_date(self.env, docket.date),
                "timestamp": format_datetime(self.env, docket.payload_timestamp) if docket.payload_timestamp else "",
                "qty_m3": docket.qty_m3,
                "workcenter": docket.workcenter_id.display_name,
                "runtime_minutes": docket.runtime_minutes,
                "idle_minutes": docket.idle_minutes,
                "slump": docket.slump,
                "alarms": ", ".join(docket.alarm_codes or []),
                "notes": docket.notes,
            }
            for docket in docket_records
        ]

        if not docket_rows:
            fallback_workorders = self.workorder_ids.sorted(
                key=lambda wo: (wo.date_start or fields.Datetime.now(), wo.id)
            )
            for workorder in fallback_workorders:
                qty = workorder.qty_produced or 0.0
                duration = workorder.duration or 0.0
                if not qty and not duration:
                    continue
                date_display = ""
                if workorder.date_start:
                    local_start = fields.Datetime.context_timestamp(self, workorder.date_start)
                    date_display = format_date(self.env, local_start.date())
                timestamp_dt = workorder.date_finished or workorder.date_start
                timestamp_display = ""
                if timestamp_dt:
                    timestamp_display = format_datetime(self.env, timestamp_dt)
                docket_rows.append(
                    {
                        "docket_no": workorder.name,
                        "date": date_display,
                        "timestamp": timestamp_display,
                        "qty_m3": qty,
                        "workcenter": workorder.workcenter_id.display_name,
                        "runtime_minutes": duration,
                        "idle_minutes": 0.0,
                        "slump": "",
                        "alarms": "",
                        "notes": "",
                    }
                )

        manufacturing_orders = [
            {
                "date_start": format_datetime(self.env, self.date_start) if self.date_start else "",
                "reference": self.name,
                "is_cooling": is_cooling,
                "daily_mgq": target_qty,
                "adjusted_mgq": adjusted_qty,
                "prime_output": prime_output,
                "allowed_wastage": allowed_wastage_qty,
                "actual_scrap": actual_scrap_qty,
                "over_wastage": over_wastage_qty,
                "deduction": deduction_qty,
                "optimized_standby": standby_qty,
                "ngt_hours": ngt_hours,
                "loto_hours": waveoff_chargeable,
            }
        ]

        show_normal_totals = any(
            normal_totals.get(key)
            for key in ("target_qty", "adjusted_target_qty", "prime_output_qty", "standby_qty", "ngt_m3")
        )

        payload = {
            "invoice_name": self.name,
            "month_label": format_date(self.env, start_date, date_format="d MMMM yyyy"),
            "version_label": _("Daily Summary"),
            "contract_name": contract.name if contract else "",
            "customer_name": customer.display_name if customer else "",
            "inventory_mode": dict(monthly_order._fields['x_inventory_mode'].selection).get(monthly_order.x_inventory_mode) if monthly_order and monthly_order.x_inventory_mode else "N/A",
            "real_warehouse": monthly_order.x_real_warehouse_id.display_name if monthly_order and monthly_order.x_real_warehouse_id else "N/A",
            "loto_total_hours": total_waveoff,
            "waveoff_allowance": contract.x_loto_waveoff_hours if contract else 0.0,
            "waveoff_applied": waveoff_applied,
            "loto_chargeable_hours": waveoff_chargeable,
            "target_qty": target_qty,
            "adjusted_target_qty": adjusted_qty,
            "ngt_hours": ngt_hours,
            "ngt_qty": relief_qty,
            "prime_output_qty": prime_output,
            "allowed_wastage_qty": allowed_wastage_qty,
            "actual_scrap_qty": actual_scrap_qty,
            "over_wastage_qty": over_wastage_qty,
            "deduction_qty": deduction_qty,
            "optimized_standby": standby_qty,
            "show_cooling_totals": is_cooling,
            "show_normal_totals": show_normal_totals,
            "monthly_target_qty": monthly_target_qty,
            "monthly_adjusted_qty": monthly_adjusted,
            "monthly_prime_output_qty": cumulative_prime,
            "monthly_standby_qty": cumulative_standby,
            "monthly_ngt_qty": cumulative_ngt,
            "monthly_ngt_hours": cumulative_ngt_hours,
            "monthly_waveoff_applied": cumulative_waveoff,
            "monthly_waveoff_chargeable": cumulative_waveoff_chargeable,
            "cooling_totals": cooling_totals,
            "normal_totals": normal_totals,
            "materials_shortage": contract.gear_materials_shortage_note if contract else "",
            "manpower_notes": contract.gear_manpower_note if contract else "",
            "asset_notes": contract.gear_asset_note if contract else "",
            "dockets": docket_rows,
            "manufacturing_orders": manufacturing_orders,
        }
        return payload

    @api.model
    def gear_find_mo_for_datetime(self, workcenter, timestamp):
        """Locate the MO whose work order is active at the given timestamp."""
        Workorder = self.env["mrp.workorder"]
        workorder = Workorder.gear_find_workorder(workcenter, timestamp)
        return workorder.production_id if workorder else self.browse()

    def _gear_client_dockets(self):
        self.ensure_one()
        return self.x_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance")


class MrpWorkorder(models.Model):
    """Extend work orders to maintain IMS telemetry totals."""

    _inherit = "mrp.workorder"

    gear_recipe_product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Recipe Product Template",
        related="gear_recipe_product_id.product_tmpl_id",
        readonly=True,
    )

    gear_docket_ids = fields.One2many(
        comodel_name="gear.rmc.docket",
        inverse_name="workorder_id",
        string="Dockets",
    )
    gear_last_ids_timestamp = fields.Datetime(
        string="Last IDS Update",
        help="Timestamp of the latest IDS payload processed for this work order.",
    )
    gear_prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        compute="_compute_prime_output_qty",
        store=True,
        digits=(16, 2),
    )
    gear_runtime_minutes = fields.Float(
        string="Runtime (min)",
        compute="_compute_runtime_idle_minutes",
        store=True,
        digits=(16, 2),
    )
    gear_idle_minutes = fields.Float(
        string="Idle (min)",
        compute="_compute_runtime_idle_minutes",
        store=True,
        digits=(16, 2),
    )
    scrap_qty = fields.Float(
        string="Scrap Quantity (m³)",
        digits=(16, 2),
        help="Quantity scrapped for this work order.",
    )
    gear_recipe_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Recipe Product",
        help="Concrete product whose recipe should be followed for this work order.",
    )
    gear_cycle_reason_id = fields.Many2one(
        comodel_name="gear.cycle.reason",
        string="Cycle Reason",
        tracking=True,
    )
    gear_cycle_reason_type = fields.Selection(
        related="gear_cycle_reason_id.reason_type",
        store=True,
        readonly=True,
    )
    gear_recipe_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Recipe (BoM)",
        domain="[('company_id', 'in', [company_id, False]), "
        " '|', ('product_id', '=', gear_recipe_product_id), "
        " ('product_tmpl_id', '=', gear_recipe_product_tmpl_id)]",
        help="Select the PLM recipe/Bill of Materials that defines batching for this work order.",
    )
    gear_recipe_line_ids = fields.Many2many(
        comodel_name="mrp.bom.line",
        compute="_compute_gear_recipe_line_ids",
        string="Recipe Components",
        help="Snapshot of the selected recipe lines for quick reference.",
    )
    gear_batch_ids = fields.Many2many(
        comodel_name="gear.rmc.docket.batch",
        compute="_compute_gear_batch_ids",
        string="Aggregated Batches",
        help="All batches captured on dockets linked to this work order.",
    )
    gear_chunk_sequence = fields.Integer(
        string="Gear Chunk Sequence",
        help="Sequential index used to release work orders one at a time.",
    )
    gear_qty_planned = fields.Float(
        string="Gear Planned Quantity",
        digits=(16, 2),
        help="Target quantity (m³) allocated to this work order chunk.",
    )

    @api.depends("gear_docket_ids.qty_m3")
    def _compute_prime_output_qty(self):
        for workorder in self:
            dockets = workorder.gear_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance")
            workorder.gear_prime_output_qty = sum(dockets.mapped("qty_m3"))

    @api.depends("gear_docket_ids.runtime_minutes", "gear_docket_ids.idle_minutes")
    def _compute_runtime_idle_minutes(self):
        for workorder in self:
            dockets = workorder.gear_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance")
            workorder.gear_runtime_minutes = sum(dockets.mapped("runtime_minutes"))
            workorder.gear_idle_minutes = sum(dockets.mapped("idle_minutes"))

    @api.depends("gear_recipe_id", "gear_recipe_id.bom_line_ids")
    def _compute_gear_recipe_line_ids(self):
        for workorder in self:
            workorder.gear_recipe_line_ids = workorder.gear_recipe_id.bom_line_ids

    @api.depends("gear_docket_ids.docket_batch_ids")
    def _compute_gear_batch_ids(self):
        for workorder in self:
            batches = workorder.gear_docket_ids.mapped("docket_batch_ids")
            workorder.gear_batch_ids = batches

    @api.onchange("production_id")
    def _onchange_production_id_set_recipe_product(self):
        if self.production_id and not self.gear_recipe_product_id:
            self.gear_recipe_product_id = self.production_id.product_id

    @api.onchange("gear_recipe_product_id")
    def _onchange_recipe_product(self):
        if self.gear_recipe_id and self.gear_recipe_id.product_tmpl_id != self.gear_recipe_product_id.product_tmpl_id:
            self.gear_recipe_id = False

    def button_start(self, raise_on_invalid_state=False, bypass=False):
        res = super().button_start(raise_on_invalid_state=raise_on_invalid_state, bypass=bypass)
        self._gear_update_docket_states(target_state="in_production")
        return res

    def button_finish(self):
        workorders = self.with_context(allow_qty_produced_done=True)
        res = super(MrpWorkorder, workorders).button_finish()
        self._gear_finalize_dockets()
        return res

    def write(self, vals):
        next_release_candidates = self.env["mrp.workorder"]
        if vals.get("state") == "done":
            next_release_candidates = self.filtered(lambda wo: wo.state != "done")
        res = super().write(vals)
        if any(key in vals for key in ["date_start", "workcenter_id"]):
            for workorder in self:
                if not workorder.gear_docket_ids:
                    continue
                for docket in workorder.gear_docket_ids:
                    docket._gear_backfill_links()
        if vals.get("state") == "done":
            next_release_candidates._gear_release_next_workorder()
        return res

    def action_cancel(self):
        res = super().action_cancel()
        self._gear_update_docket_states(target_state="cancel")
        return res

    @api.model_create_multi
    def create(self, vals_list):
        workorders = super().create(vals_list)
        workorders._gear_autocreate_dockets()
        return workorders

    def _gear_autocreate_dockets(self):
        docket_model = self.env["gear.rmc.docket"]
        for workorder in self:
            production = workorder.production_id
            sale_order = getattr(production, "x_sale_order_id", False)
            if not sale_order or sale_order.x_billing_category != "rmc":
                continue
            if workorder.gear_docket_ids:
                continue
            base_no = workorder.name or f"WO-{workorder.id}"
            docket_no = base_no
            suffix = 1
            while docket_model.search_count([("so_id", "=", sale_order.id), ("docket_no", "=", docket_no)]):
                suffix += 1
                docket_no = f"{base_no}-{suffix}"
            monthly_order = getattr(production, "x_monthly_order_id", False)
            if workorder.date_start:
                date_value = False
                if monthly_order:
                    try:
                        user_tz = monthly_order._gear_get_user_tz()
                        date_value = monthly_order._gear_datetime_to_local_date(workorder.date_start, user_tz)
                    except Exception:
                        date_value = False
                if not date_value:
                    local_dt = fields.Datetime.context_timestamp(workorder, workorder.date_start)
                    date_value = local_dt.date() if local_dt else fields.Date.context_today(workorder)
            else:
                date_value = fields.Date.context_today(workorder)
            docket_vals = {
                "so_id": sale_order.id,
                "production_id": production.id,
                "workorder_id": workorder.id,
                "workcenter_id": workorder.workcenter_id.id if workorder.workcenter_id else False,
                "monthly_order_id": getattr(production, "x_monthly_order_id", False) and production.x_monthly_order_id.id or False,
                "docket_no": docket_no,
                "date": date_value,
                "source": "manual",
                "state": "draft",
                "quantity_ordered": workorder.gear_qty_planned or workorder.qty_production or production.product_qty,
                "payload_timestamp": workorder.date_start,
            }
            if workorder.gear_cycle_reason_id:
                docket_vals["cycle_reason_id"] = workorder.gear_cycle_reason_id.id
            docket_model.create(docket_vals)

    def _gear_update_docket_states(self, target_state):
        valid_states = {"draft", "in_production", "ready", "dispatched"}
        for workorder in self:
            dockets = workorder.gear_docket_ids.filtered(
                lambda d: d.state in valid_states and d.cycle_reason_type != "maintenance"
            )
            if not dockets:
                continue
            if target_state == "in_production":
                now = fields.Datetime.now()
                for docket in dockets:
                    vals = {"state": target_state}
                    if not docket.payload_timestamp:
                        vals["payload_timestamp"] = now
                    docket.write(vals)
            else:
                dockets.write({"state": target_state})

    def _gear_finalize_dockets(self):
        for workorder in self:
            dockets = workorder.gear_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance")
            if not dockets:
                continue
            produced_qty = (
                workorder.qty_produced
                or workorder.gear_qty_planned
                or workorder.qty_production
                or 0.0
            )
            runtime_minutes = workorder.duration or 0.0

            # Only auto-allocate quantities for dockets that haven't been filled yet
            pending_dockets = dockets.filtered(lambda d: not d.qty_m3)
            if produced_qty and pending_dockets:
                remaining = produced_qty
                cumulative = 0.0
                ordered_dockets = pending_dockets.sorted(key=lambda d: d.date or workorder.date_start or fields.Date.today())
                for docket in ordered_dockets:
                    preferred = docket.quantity_ordered or remaining
                    allocation = min(preferred, remaining) if preferred else 0.0
                    if allocation <= 0 and remaining > 0 and docket == ordered_dockets[-1]:
                        allocation = remaining
                    cumulative += allocation
                    vals = {
                        "qty_m3": allocation,
                        "quantity_produced": allocation,
                        "cumulative_quantity": cumulative,
                        "state": "delivered",
                    }
                    if runtime_minutes and not docket.runtime_minutes:
                        vals["runtime_minutes"] = runtime_minutes
                    docket.write(vals)
                    remaining = max(remaining - allocation, 0.0)
                if remaining > 0 and ordered_dockets:
                    last = ordered_dockets[-1]
                    cumulative += remaining
                    last.write(
                        {
                            "qty_m3": last.qty_m3 + remaining,
                            "quantity_produced": last.quantity_produced + remaining,
                            "cumulative_quantity": cumulative,
                        }
                    )

            # Update states/runtime for all related dockets still in intermediate states
            finalizable = dockets.filtered(lambda d: d.state in {"draft", "in_production", "ready", "dispatched"})
            vals = {"state": "delivered"}
            if runtime_minutes:
                for docket in finalizable.filtered(lambda d: not d.runtime_minutes):
                    docket.write({"runtime_minutes": runtime_minutes})
            if finalizable:
                finalizable.write({"state": "delivered"})

            monthly_orders = workorder.production_id.mapped("x_monthly_order_id")
            if monthly_orders:
                monthly_orders.invalidate_model(
                    [
                        "prime_output_qty",
                        "optimized_standby_qty",
                        "runtime_minutes",
                        "idle_minutes",
                        "ngt_hours",
                        "loto_hours",
                        "waveoff_hours_applied",
                        "waveoff_hours_chargeable",
                    ]
                )

    @api.model
    def gear_find_workorder(self, workcenter, timestamp):
        """Resolve an active work order for the provided work center and timestamp."""
        if not workcenter:
            return self.browse()

        if not timestamp:
            timestamp = fields.Datetime.now()

        domain = [
            ("workcenter_id", "=", workcenter.id),
            ("state", "in", ["ready", "progress"]),
        ]
        candidate_workorders = self.search(domain, order="date_start desc", limit=5)
        timestamp = fields.Datetime.to_datetime(timestamp)

        for workorder in candidate_workorders:
            window_start = workorder.date_start or (timestamp - timedelta(hours=1))
            window_end = workorder.date_finished or (timestamp + timedelta(hours=1))
            if window_start <= timestamp <= window_end:
                return workorder

        # fallback to the most recent in-progress workorder
        fallback = candidate_workorders.filtered(lambda w: w.state == "progress")
        if fallback:
            return fallback[0]

        return candidate_workorders[:1]

    def gear_register_ids_payload(self, payload):
        """Handle IDS payload and update dockets + Metrics."""
        self.ensure_one()
        payload = payload or {}

        if payload.get("timestamp"):
            self.gear_last_ids_timestamp = payload["timestamp"]

        docket_payload = {
            "docket_no": payload.get("docket_no"),
            "date": payload.get("date") or fields.Date.to_string(fields.Date.context_today(self)),
            "payload_timestamp": payload.get("timestamp"),
            "qty_m3": payload.get("produced_m3", 0.0),
            "runtime_minutes": payload.get("runtime_min", 0.0),
            "idle_minutes": payload.get("idle_min", 0.0),
            "alarms": payload.get("alarms") or [],
            "notes": payload.get("notes"),
            "source": "ids",
        }
        if self.gear_cycle_reason_id:
            docket_payload["cycle_reason_id"] = self.gear_cycle_reason_id.id
        if payload.get("slump"):
            docket_payload["slump"] = payload["slump"]

        docket = self.env["gear.rmc.docket"].gear_create_from_workorder(self, docket_payload)
        self.invalidate_model(
            [
                "gear_prime_output_qty",
                "gear_runtime_minutes",
                "gear_idle_minutes",
            ]
        )
        if self.production_id:
            self.production_id.invalidate_model(
                [
                    "x_prime_output_qty",
                    "x_runtime_minutes",
                    "x_idle_minutes",
                ]
            )
        return docket

    def _gear_release_next_workorder(self):
        Workorder = self.env["mrp.workorder"]
        for workorder in self:
            production = workorder.production_id
            if not production:
                continue
            if production.workorder_ids.filtered(lambda wo: wo.state == "progress"):
                continue
            pending_entries = list(production.x_pending_workorder_chunks or [])
            next_candidate = production.workorder_ids.filtered(
                lambda wo: wo.state in ("ready", "blocked") and wo.id != workorder.id
            ).sorted(lambda wo: (wo.gear_chunk_sequence or wo.sequence, wo.id))[:1]
            created = False
            if not next_candidate and pending_entries:
                payload = pending_entries.pop(0)
                qty = payload.get("qty") or 0.0
                if qty > 0:
                    seq = payload.get("seq")
                    workcenter = workorder.workcenter_id or production.workorder_ids[:1].workcenter_id
                    if not workcenter:
                        _logger.info(
                            "Cannot auto-create next work order for %s due to missing workcenter.",
                            production.display_name,
                        )
                        production.x_pending_workorder_chunks = pending_entries
                        continue
                    name = payload.get("name") or (
                        f"{production.name} / {workcenter.display_name}"
                        if seq == 1
                        else f"{production.name} / {workcenter.display_name} ({seq})"
                    )
                    start_dt_str = payload.get("date_start")
                    end_dt_str = payload.get("date_finished")
                    if start_dt_str:
                        start_dt = fields.Datetime.from_string(start_dt_str)
                    else:
                        start_dt = workorder.date_finished or fields.Datetime.now()
                    if end_dt_str:
                        end_dt = fields.Datetime.from_string(end_dt_str)
                    else:
                        end_dt = start_dt
                    vals = {
                        "name": name,
                        "production_id": production.id,
                        "workcenter_id": workcenter.id,
                        "qty_production": qty,
                        "date_start": start_dt,
                        "date_finished": end_dt,
                        "sequence": seq,
                        "gear_chunk_sequence": seq,
                        "gear_qty_planned": qty,
                    }
                    next_candidate = Workorder.create(vals)
                    created = True
                else:
                    _logger.info(
                        "Skipping automatic creation of next work order for %s due to zero-quantity chunk.",
                        production.display_name,
                    )
            production.x_pending_workorder_chunks = pending_entries
            if not next_candidate:
                continue
            candidate = next_candidate[:1]
            if candidate.state in ("done", "cancel"):
                continue
            if candidate.state == "progress":
                continue
            if candidate.state == "blocked" and not created:
                continue
            if candidate.state != "ready":
                try:
                    candidate.write({"state": "ready"})
                except Exception:
                    # ignore if compute-driven or forbidden; manual intervention needed
                    pass

    @api.constrains("gear_runtime_minutes", "gear_cycle_reason_id")
    def _check_cycle_reason_threshold(self):
        threshold = self.env["gear.rmc.docket"]._get_cycle_runtime_threshold()
        for workorder in self:
            exceeds = workorder.gear_runtime_minutes and workorder.gear_runtime_minutes > threshold
            docket_reasons = workorder.gear_docket_ids.filtered("cycle_reason_id")
            has_reason = workorder.gear_cycle_reason_id or docket_reasons
            client_reason = (
                workorder.gear_cycle_reason_type == "client"
                or any(dr.cycle_reason_type == "client" for dr in docket_reasons)
            )
            if exceeds and not has_reason:
                raise ValidationError(
                    _("A cycle reason is required when runtime exceeds %(threshold)s minutes.", threshold=threshold)
                )
            if exceeds and not client_reason:
                raise ValidationError(_("Client workflows require a Client reason."))
