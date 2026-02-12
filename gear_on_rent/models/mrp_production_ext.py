from datetime import datetime, time, timedelta
import calendar
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
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
    x_daily_report_sent = fields.Boolean(
        string="Daily Report Sent",
        default=False,
        copy=False,
        help="Flag to avoid emailing the daily MO report multiple times.",
    )
    x_include_attendance_annexure = fields.Boolean(
        string="Include Attendance Annexure",
        default=True,
        help="When enabled, the attendance annexure block is shown on the daily report PDF/email.",
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

    _check_relief_not_negative = models.Constraint(
        "CHECK(x_relief_qty >= 0)",
        "Relief quantity cannot be negative.",
    )

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

    @api.depends("x_daily_target_qty", "product_qty", "x_prime_output_qty", "x_relief_qty")
    def _compute_optimized_standby_qty(self):
        for production in self:
            target_qty = production.x_daily_target_qty or production.product_qty or 0.0
            prime_output = production.x_prime_output_qty or 0.0
            relief_qty = production.x_relief_qty or 0.0
            production.x_optimized_standby_qty = max(target_qty - (prime_output + relief_qty), 0.0)

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

        force_email = bool(self.env.context.get("force_email"))
        email_only = bool(self.env.context.get("email_only"))

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
        contract = monthly.so_id if monthly else self.x_sale_order_id
        template = self.env.ref("gear_on_rent.mail_template_daily_mo_report", raise_if_not_found=False)
        send_email = template and ((not monthly or monthly.x_auto_email_daily) or force_email)
        mail_sent = False
        mail_message = False
        email_values = {}
        if send_email:
            if attachment:
                email_values["attachment_ids"] = [(4, attachment.id)]
            # Fallback recipients in case partner_to renders empty (e.g., missing invoice partner email).
            if contract and not email_values.get("email_to"):
                candidate_emails = [
                    contract.partner_invoice_id.email,
                    contract.partner_id.email,
                    contract.user_id.email,
                    self.env.user.email,
                ]
                email_to_list = [e for e in candidate_emails if e]
                if email_to_list:
                    email_values["email_to"] = ",".join(dict.fromkeys(email_to_list))
            mail_id = template.send_mail(self.id, force_send=True, email_values=email_values)
            mail_sent = bool(mail_id)
            if mail_sent:
                self.x_daily_report_sent = True
                mail_message = self.env["mail.mail"].browse(mail_id).mail_message_id
        elif email_only:
            raise UserError(_("Email template for daily MO report is missing."))
        elif force_email:
            raise UserError(_("Daily MO report email could not be sent. Please check the template and mail settings."))

        message_attachment_ids = attachment and [attachment.id] or False
        # Prefer cloning the real email message so chatter shows the envelope + body.
        if mail_sent and mail_message:
            if monthly:
                mail_message.copy(
                    {
                        "model": monthly._name,
                        "res_id": monthly.id,
                        "parent_id": False,
                    }
                )
        else:
            if send_email:
                message = _("Daily report email attempted for %(mo)s but no recipient was found.") % {
                    "mo": self.display_name
                }
                message_type = "comment"
            else:
                message = _("Daily report generated for %(mo)s.") % {"mo": self.display_name}
                message_type = "comment"

            if monthly:
                monthly.message_post(
                    body=message,
                    attachment_ids=message_attachment_ids,
                    message_type=message_type,
                    subtype_xmlid="mail.mt_comment",
                )
            # Always log on the MO as well so chatter shows the action on the child record.
            self.message_post(
                body=message,
                attachment_ids=message_attachment_ids,
                message_type=message_type,
                subtype_xmlid="mail.mt_comment",
            )

        if email_only:
            if not mail_sent:
                raise UserError(_("Daily MO report email could not be sent. Please check the template and mail settings."))
            return True
        return report.report_action(self)

    def action_send_daily_report_email(self):
        """Manually email the daily MO report from the list view without opening the PDF."""
        self.ensure_one()
        action = self.with_context(force_email=True, email_only=True).action_print_daily_report()
        if action is True:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Email queued"),
                    "message": _("Daily report email queued for %s.") % (self.display_name,),
                    "type": "success",
                    "sticky": False,
                },
            }
        return action

    def _gear_hours_to_qty(self, hours):
        self.ensure_one()
        if not hours:
            return 0.0

        monthly = self.x_monthly_order_id
        contract = monthly.so_id if monthly else self.x_sale_order_id
        # Prefer contract/monthly snapshot factor; fallback to derived MGQ per-hour rate.
        factor = 0.0
        if monthly and monthly.ngt_hourly_prorata_factor:
            factor = monthly.ngt_hourly_prorata_factor
        elif contract and contract.ngt_hourly_prorata_factor:
            factor = contract.ngt_hourly_prorata_factor
        else:
            # Derive from MGQ: (MGQ per month / days in month) / 24
            mgq = 0.0
            days_in_month = 0
            if monthly:
                mgq = monthly.mgq_monthly or monthly.monthly_target_qty or 0.0
                if monthly.date_start:
                    days_in_month = calendar.monthrange(monthly.date_start.year, monthly.date_start.month)[1]
            if not mgq and contract:
                mgq = contract.x_monthly_mgq or contract.mgq_monthly or 0.0
            if not days_in_month:
                date_ref = monthly.date_start if monthly and monthly.date_start else fields.Date.context_today(self)
                days_in_month = calendar.monthrange(date_ref.year, date_ref.month)[1]
            if mgq and days_in_month:
                factor = (mgq / days_in_month) / 24.0

        if not factor and self.x_daily_target_qty:
            factor = (self.x_daily_target_qty or 0.0) / 24.0

        return round((hours or 0.0) * factor, 2)

    def _gear_get_daily_report_payload(self):
        """Return a payload compatible with the month-end template for a single MO."""
        self.ensure_one()
        start_dt = False
        if self.date_start:
            start_dt = fields.Datetime.context_timestamp(self, self.date_start)
        start_date = start_dt.date() if start_dt else fields.Date.context_today(self)
        report_date = start_date

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

        monthly_target_qty = monthly_order.monthly_target_qty if monthly_order else contract.x_monthly_mgq if contract else 0.0
        monthly_adjusted = monthly_order.adjusted_target_qty if monthly_order else monthly_target_qty

        target_qty = self.x_daily_target_qty or self.product_qty or 0.0
        if not target_qty and monthly_order:
            target_qty = monthly_adjusted or monthly_target_qty or (monthly_order.mgq_monthly or 0.0)

        adjusted_qty = self.x_adjusted_target_qty or target_qty
        if monthly_order and not adjusted_qty:
            adjusted_qty = monthly_adjusted or monthly_target_qty or adjusted_qty
        ngt_hours = self.x_ngt_hours or 0.0
        relief_qty = self.x_relief_qty or 0.0
        workorder_output = sum(self.workorder_ids.mapped("qty_produced"))
        prime_output = self.x_prime_output_qty or workorder_output or (self.qty_produced or 0.0)
        is_cooling = bool(self.x_is_cooling_period or (monthly_order and monthly_order.x_is_cooling_period))
        # Standby = remaining MGQ after prime output and NGT relief.
        # Use monthly adjusted/target MGQ when available so the summary reflects contract-level MGQ.
        standby_base_qty = monthly_target_qty or monthly_adjusted or target_qty
        standby_qty = max(standby_base_qty - (prime_output + relief_qty), 0.0)
        waveoff_applied = self.x_waveoff_hours_applied or 0.0
        waveoff_chargeable = self.x_waveoff_hours_chargeable or 0.0
        total_waveoff = waveoff_applied + waveoff_chargeable
        allowed_wastage_qty = self.wastage_allowed_qty or 0.0
        actual_scrap_qty = self.actual_scrap_qty or 0.0
        over_wastage_qty = self.over_wastage_qty or 0.0
        deduction_qty = self.deduction_qty or 0.0
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
        # Keep standby populated even during cooling to reflect true shortfall/overage.
        bucket_data.update(
            {
                "target_qty": target_qty,
                "adjusted_target_qty": adjusted_qty,
                "prime_output_qty": prime_output,
                "standby_qty": standby_qty,
                "ngt_m3": relief_qty,
                "ngt_hours": ngt_hours,
                "waveoff_applied_hours": waveoff_applied,
                "waveoff_chargeable_hours": waveoff_chargeable,
            }
        )

        docket_records = self.x_docket_ids.sorted(key=lambda d: (d.date or fields.Date.today(), d.id))
        docket_rows = []
        manual_ops_map = {}
        if docket_records:
            first_docket = docket_records[0]
            candidate_date = first_docket.date
            if not candidate_date:
                dt_candidate = first_docket.batching_time or first_docket.payload_timestamp
                if dt_candidate:
                    dt_local = fields.Datetime.context_timestamp(self, dt_candidate)
                    candidate_date = dt_local.date() if dt_local else False
            if candidate_date:
                report_date = candidate_date
        manual_operations = self.env["gear.rmc.manual.operation"].search(
            [("docket_id", "in", docket_records.ids), ("state", "=", "approved")]
        )
        for op in manual_operations:
            mode = op.recipe_display_mode or "on_production"
            manual_ops_map.setdefault(op.docket_id.id, []).append(
                {
                    "description": op.docket_no or op.docket_id.display_name,
                    "quantity": op.manual_qty_total or op.qty_m3 or 0.0,
                    "remarks": dict(op._fields["recipe_display_mode"].selection).get(mode, mode.replace("_", " ").title()),
                    "mode": mode,
                }
            )

        manual_operations_rows = []
        manual_total_qty = 0.0

        for docket in docket_records:
            workorder = docket.workorder_id
            start_dt = workorder.date_start if workorder and workorder.date_start else docket.batching_time or docket.payload_timestamp
            end_dt = workorder.date_finished if workorder and workorder.date_finished else docket.payload_timestamp or docket.batching_time
            duration_minutes = (workorder.duration if workorder else 0.0) or docket.runtime_minutes or 0.0
            if not end_dt and start_dt and duration_minutes:
                end_dt = start_dt + timedelta(minutes=duration_minutes)
            manual_on = sum(op["quantity"] for op in manual_ops_map.get(docket.id, []) if op["mode"] == "on_production")
            manual_after = sum(op["quantity"] for op in manual_ops_map.get(docket.id, []) if op["mode"] == "after_production")
            if docket.id in manual_ops_map:
                for op in manual_ops_map[docket.id]:
                    manual_total_qty += op["quantity"]
                    manual_operations_rows.append(op)
            docket_rows.append(
                {
                    "docket_no": docket.docket_no,
                    "date": format_date(self.env, docket.date),
                    "timestamp": format_datetime(self.env, docket.payload_timestamp) if docket.payload_timestamp else "",
                    "batching_time": format_datetime(self.env, docket.batching_time) if docket.batching_time else "",
                    "start_time": format_datetime(self.env, start_dt) if start_dt else "",
                    "end_time": format_datetime(self.env, end_dt) if end_dt else "",
                    "duration_minutes": duration_minutes,
                    "customer_name": docket.customer_id.display_name or "",
                    "customer_address": docket.customer_id.contact_address or "",
                    "quantity_ordered": docket.quantity_ordered or 0.0,
                    "qty_m3": docket.qty_m3,
                    "manual_on_qty": manual_on,
                    "manual_after_qty": manual_after,
                    "workcenter": docket.workcenter_id.display_name,
                    "tm_number": docket.tm_number or "",
                    "recipe": docket.recipe_id.display_name or "",
                    "runtime_minutes": docket.runtime_minutes,
                    "idle_minutes": docket.idle_minutes,
                    "slump": docket.slump,
                    "alarms": ", ".join(docket.alarm_codes or []),
                    "notes": docket.notes,
                }
            )

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
                        "batching_time": timestamp_display,
                        "start_time": format_datetime(self.env, workorder.date_start) if workorder.date_start else "",
                        "end_time": format_datetime(self.env, workorder.date_finished) if workorder.date_finished else timestamp_display,
                        "duration_minutes": duration or 0.0,
                        "qty_m3": qty,
                        "manual_on_qty": 0.0,
                        "manual_after_qty": 0.0,
                        "workcenter": workorder.workcenter_id.display_name,
                        "runtime_minutes": duration,
                        "idle_minutes": 0.0,
                        "slump": "",
                        "alarms": "",
                        "notes": "",
                    }
                )

        month_label = format_date(self.env, report_date, date_format="d MMMM yyyy")

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
                "reason": _("Production scrap"),
            }
        ]

        day_start_dt = datetime.combine(report_date, time.min)
        day_end_dt = datetime.combine(report_date, time.max)

        # Capture scrap logs for the day (or this MO) similar to the month-end annexure.
        scrap_logs = []
        scrap_domain = [("state", "=", "done")]
        if self.workorder_ids:
            scrap_domain.append(("workorder_id", "in", self.workorder_ids.ids))
        else:
            scrap_domain.append(("production_id", "=", self.id))

        if report_date:
            start_dt = fields.Datetime.to_datetime(day_start_dt)
            end_dt = fields.Datetime.to_datetime(day_end_dt)
            scrap_domain.append(("date_done", ">=", start_dt))
            scrap_domain.append(("date_done", "<=", end_dt))

        scraps = self.env["stock.scrap"].search(scrap_domain, order="date_done asc, id asc")
        for scrap in scraps:
            reason = ", ".join(scrap.scrap_reason_tag_ids.mapped("name")) if getattr(scrap, "scrap_reason_tag_ids", False) else ""
            scrap_logs.append(
                {
                    "date": format_datetime(self.env, scrap.date_done) if scrap.date_done else "",
                    "reference": scrap.name,
                    "reason": reason or scrap.origin or (scrap.product_id and scrap.product_id.display_name) or "",
                    "quantity": scrap.scrap_qty or 0.0,
                }
            )

        if not scrap_logs:
            scrap_logs = [
                {
                    "date": mo.get("date_start"),
                    "reference": mo.get("reference"),
                    "reason": mo.get("reason") or _("Production scrap"),
                    "quantity": mo.get("actual_scrap", 0.0),
                }
                for mo in manufacturing_orders
                if mo.get("actual_scrap")
            ]

        if not scrap_logs and actual_scrap_qty:
            scrap_logs = [
                {
                    "date": month_label,
                    "reference": self.name or contract.name or _("Scrap"),
                    "reason": _("Total scrap (no log detail)"),
                    "quantity": actual_scrap_qty,
                }
            ]

        attendance_entries = []
        attendance_present = 0
        attendance_hours_total = 0.0
        if "hr.attendance" in self.env:
            Attendance = self.env["hr.attendance"]
            Employee = self.env["hr.employee"]
            operator_users = docket_records.mapped("operator_user_id")
            employees = Employee.search([("user_id", "in", operator_users.ids)]) if operator_users else Employee.browse()

            start_dt = fields.Datetime.to_datetime(day_start_dt)
            end_dt = fields.Datetime.to_datetime(day_end_dt)
            domain = [("check_in", "<=", end_dt), "|", ("check_out", "=", False), ("check_out", ">=", start_dt)]
            if employees:
                # Prefer narrowing to operators tied to the dockets for the day.
                domain.append(("employee_id", "in", employees.ids))

            attendances = Attendance.search(domain, order="employee_id, check_in")
            present_ids = set()
            for att in attendances:
                check_in = fields.Datetime.to_datetime(att.check_in) if att.check_in else False
                check_out = fields.Datetime.to_datetime(att.check_out) if att.check_out else False
                start_bound = max(start_dt, check_in) if check_in else start_dt
                end_bound = min(end_dt, check_out) if check_out else end_dt
                hours_val = 0.0
                if start_bound and end_bound and end_bound > start_bound:
                    hours_val = round((end_bound - start_bound).total_seconds() / 3600.0, 2)
                elif att.worked_hours:
                    hours_val = att.worked_hours
                attendance_entries.append(
                    {
                        "employee_id": att.employee_id.id,
                        "employee_name": att.employee_id.display_name or att.employee_id.name or "",
                        "check_in": format_datetime(self.env, att.check_in) if att.check_in else "",
                        "check_out": format_datetime(self.env, att.check_out) if att.check_out else "",
                        "worked_hours": hours_val,
                        "status": _("Open") if not att.check_out else _("Closed"),
                    }
                )
                present_ids.add(att.employee_id.id)
                attendance_hours_total += hours_val
            attendance_present = len(present_ids)

        # NGT requests for the same contract/day
        ngt_requests = self.env["gear.ngt.request"].search(
            [
                ("so_id", "=", contract.id if contract else False),
                ("state", "=", "approved"),
                ("date_start", "<=", day_end_dt),
                ("date_end", ">=", day_start_dt),
            ],
            order="date_start asc, approved_on desc, id desc",
        )
        ngt_requests_data = []
        currency_symbol_default = contract.currency_id.symbol if contract and contract.currency_id else (self.company_id.currency_id.symbol or "")
        ngt_hours_from_requests = 0.0
        ngt_qty_from_requests = 0.0
        for request in ngt_requests:
            meter_units = request.electricity_units or 0.0
            if not meter_units and request.meter_reading_start is not None and request.meter_reading_end is not None:
                meter_units = max(request.meter_reading_end - request.meter_reading_start, 0.0)
            ngt_hours_from_requests += request.hours_total or 0.0
            qty_val = request.ngt_qty or ((request.hours_total or 0.0) * (request.ngt_hourly_factor_effective or request.ngt_hourly_rate or request.ngt_hourly_prorata_factor or 0.0))
            ngt_qty_from_requests += qty_val
            ngt_requests_data.append(
                {
                    "name": request.name,
                    "company_name": request.company_id.display_name if request.company_id else "",
                    "contract_name": request.so_id.display_name or "",
                    "status": request.state,
                    "mgq_monthly": request.mgq_monthly or 0.0,
                    "period_start": format_datetime(self.env, request.date_start) if request.date_start else "",
                    "period_end": format_datetime(self.env, request.date_end) if request.date_end else "",
                    "hours": request.hours_total or 0.0,
                    "hour_rate": request.ngt_hourly_factor_effective
                    or request.ngt_hourly_rate
                    or request.ngt_hourly_prorata_factor
                    or 0.0,
                    "qty": qty_val,
                    "meter_start": request.meter_reading_start or 0.0,
                    "meter_end": request.meter_reading_end or 0.0,
                    "meter_units": meter_units,
                    "employee_expense": request.employee_expense or 0.0,
                    "land_rent": request.land_rent or 0.0,
                    "electricity_rate": request.electricity_unit_rate or 0.0,
                    "electricity_expense": request.electricity_expense or 0.0,
                    "total_expense": request.total_expense or 0.0,
                    "reason": request.reason or "",
                    "currency_symbol": request.currency_id.symbol
                    or (request.company_id.currency_id.symbol if request.company_id and request.company_id.currency_id else currency_symbol_default),
                    "show_expenses": any(
                        [
                            request.employee_expense,
                            request.land_rent,
                            request.electricity_unit_rate,
                            request.electricity_expense,
                            request.total_expense,
                        ]
                    ),
                }
            )

        # Override day-level NGT figures with approved requests overlapping the day
        if ngt_hours_from_requests:
            ngt_hours = ngt_hours_from_requests
        if ngt_qty_from_requests:
            relief_qty = ngt_qty_from_requests

        # Safety cap: a calendar day cannot exceed 24 hours
        max_hours = 24.0
        if ngt_hours > max_hours:
            scale = max_hours / ngt_hours if ngt_hours else 0.0
            ngt_hours = max_hours
            relief_qty = round(relief_qty * scale, 2)

        # Refresh standby after final relief adjustments (and keep visible even in cooling).
        standby_qty = max(target_qty - (prime_output + relief_qty), 0.0)
        bucket_data["standby_qty"] = standby_qty
        bucket_data["ngt_m3"] = relief_qty
        bucket_data["ngt_hours"] = ngt_hours
        if manufacturing_orders:
            manufacturing_orders[0]["optimized_standby"] = standby_qty
            manufacturing_orders[0]["ngt_hours"] = ngt_hours
        if not monthly_order:
            cumulative_standby = standby_qty
            cumulative_ngt = relief_qty
            cumulative_ngt_hours = ngt_hours

        # NGT expense snapshot from monthly order if available
        ngt_expense = {}
        if monthly_order:
            currency_symbol = monthly_order.company_id.currency_id.symbol or currency_symbol_default
            emp = monthly_order.ngt_employee_expense or 0.0
            land = monthly_order.ngt_land_rent or 0.0
            units = monthly_order.ngt_meter_units or 0.0
            unit_rate = monthly_order.ngt_electricity_unit_rate or 0.0
            elec_expense = monthly_order.ngt_electricity_expense or 0.0
            total_expense = monthly_order.ngt_total_expense or 0.0
            mgq_target = monthly_order.monthly_target_qty or monthly_order.mgq_monthly or contract.x_monthly_mgq if contract else 0.0
            rate_per_m3 = (total_expense / mgq_target) if mgq_target else 0.0
            ngt_expense = {
                "employee_expense": emp,
                "land_rent": land,
                "electricity_rate": unit_rate,
                "electricity_expense": elec_expense,
                "electricity_units": units,
                "total_expense": total_expense,
                "rate_per_m3": rate_per_m3,
                "mgq_target": mgq_target,
                "currency_symbol": currency_symbol,
                "show_expenses": any([emp, land, elec_expense, total_expense]),
            }

        # LOTO requests overlapping the day
        loto_requests = self.env["gear.loto.request"].search(
            [
                ("so_id", "=", contract.id if contract else False),
                ("state", "=", "approved"),
                ("date_start", "<=", day_end_dt),
                ("date_end", ">=", day_start_dt),
            ],
            order="date_start asc",
        )
        loto_requests_data = [
            {
                "name": req.name,
                "period_start": format_datetime(self.env, req.date_start) if req.date_start else "",
                "period_end": format_datetime(self.env, req.date_end) if req.date_end else "",
                "hours_total": req.hours_total or 0.0,
                "hours_waveoff": req.hours_waveoff_applied or 0.0,
                "hours_chargeable": req.hours_chargeable or 0.0,
                "reason": req.reason or "",
            }
            for req in loto_requests
        ]
        loto_total_hours = sum(l.get("hours_total", 0.0) for l in loto_requests_data)
        loto_chargeable_hours = sum(l.get("hours_chargeable", 0.0) for l in loto_requests_data)

        # Update manufacturing order row with final ngt_hours
        if manufacturing_orders:
            manufacturing_orders[0]["ngt_hours"] = ngt_hours

        show_normal_totals = any(
            normal_totals.get(key)
            for key in ("target_qty", "adjusted_target_qty", "prime_output_qty", "standby_qty", "ngt_m3")
        )

        payload = {
            "invoice_name": self.name,
            "month_label": month_label,
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
            "scrap_logs": scrap_logs,
            "ngt_requests": ngt_requests_data,
            "ngt_expense": ngt_expense,
            "loto_requests": loto_requests_data,
            "loto_total_hours": loto_total_hours,
            "loto_chargeable_hours": loto_chargeable_hours,
            "status_label": _("Approved"),
            "manual_operations": manual_operations_rows,
            "manual_total_qty": manual_total_qty,
            "attendance_entries": attendance_entries,
            "attendance_present": attendance_present,
            "attendance_hours_total": round(attendance_hours_total, 2),
            "include_attendance_annexure": bool(self.x_include_attendance_annexure),
        }
        return payload

    def action_open_self(self):
        """Open the manufacturing order form directly."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    @api.model
    def gear_find_mo_for_datetime(self, workcenter, timestamp):
        """Locate the MO whose work order is active at the given timestamp."""
        Workorder = self.env["mrp.workorder"]
        workorder = Workorder.gear_find_workorder(workcenter, timestamp)
        return workorder.production_id if workorder else self.browse()

    def _gear_client_dockets(self):
        self.ensure_one()
        return self.x_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance")

    @api.model
    def _cron_email_daily_reports(self):
        """Send daily MO reports (PDF + email) once per day when enabled on the monthly order."""
        today = fields.Date.context_today(self)
        target_date = today - timedelta(days=1)
        domain = [
            ("x_daily_report_sent", "=", False),
            ("x_monthly_order_id", "!=", False),
            ("x_monthly_order_id.x_auto_email_daily", "=", True),
            ("date_start", "!=", False),
            ("state", "not in", ("cancel",)),
        ]
        candidates = self.search(domain)
        for production in candidates:
            monthly = production.x_monthly_order_id
            if not monthly:
                continue
            tz = monthly._gear_get_user_tz()
            local_date = monthly._gear_datetime_to_local_date(production.date_start, tz) if production.date_start else False
            if not local_date or local_date > target_date:
                continue
            # Skip backlog: mark older days as sent so the cron doesn't try to send months of history.
            if local_date < target_date:
                production.x_daily_report_sent = True
                continue
            try:
                production.action_print_daily_report()
            except Exception:
                _logger.exception("Failed to auto-send daily report for %s", production.display_name)


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
    gear_docket_qty_m3 = fields.Float(
        string="Quantity (m³)",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
        digits=(16, 2),
    )
    gear_docket_tm_number = fields.Char(
        string="TM Number",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_driver_name = fields.Char(
        string="Driver Name",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_operator_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Operator User",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_recipe_id = fields.Many2one(
        comodel_name="mrp.bom",
        string="Recipe",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_batching_time = fields.Datetime(
        string="Batching Time",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_no = fields.Char(
        string="Docket Number",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
    )
    gear_docket_customer_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        compute="_compute_primary_docket_fields",
        inverse="_inverse_primary_docket_fields",
        store=True,
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
    gear_cumulative_qty_produced = fields.Float(
        string="Produced Quantity (Cumulative)",
        compute="_compute_gear_cumulative_qty_produced",
        digits=(16, 2),
        help="Running total of produced quantity up to and including this work order.",
    )
    gear_remaining_qty = fields.Float(
        string="Remaining Qty (m³)",
        compute="_compute_gear_remaining_qty",
        digits=(16, 2),
        help="Remaining MO target after accounting for cumulative produced quantity.",
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

    @api.depends(
        "gear_prime_output_qty",
        "gear_docket_qty_m3",
        "production_id.workorder_ids.gear_prime_output_qty",
        "production_id.workorder_ids.gear_docket_qty_m3",
        "production_id.workorder_ids.gear_chunk_sequence",
        "production_id.workorder_ids.sequence",
        "production_id.workorder_ids.state",
    )
    def _compute_gear_cumulative_qty_produced(self):
        for workorder in self:
            production = workorder.production_id
            if not production:
                produced = (
                    workorder.gear_prime_output_qty
                    or workorder.gear_docket_qty_m3
                    or workorder.qty_produced
                    or 0.0
                )
                workorder.gear_cumulative_qty_produced = produced
                continue
            siblings = production.workorder_ids.filtered(lambda w: w.state != "cancel")
            siblings = siblings.sorted(
                key=lambda w: (w.gear_chunk_sequence or w.sequence or w.id, w.id)
            )
            total = 0.0
            for sibling in siblings:
                produced = (
                    sibling.gear_prime_output_qty
                    or sibling.gear_docket_qty_m3
                    or sibling.qty_produced
                    or 0.0
                )
                total += produced
                if sibling == workorder:
                    break
            workorder.gear_cumulative_qty_produced = total

    @api.depends("gear_cumulative_qty_produced", "production_id.product_qty")
    def _compute_gear_remaining_qty(self):
        for workorder in self:
            target_qty = workorder.production_id.product_qty if workorder.production_id else 0.0
            produced_qty = workorder.gear_cumulative_qty_produced or 0.0
            workorder.gear_remaining_qty = max(target_qty - produced_qty, 0.0)

    @api.depends(
        "gear_recipe_id",
        "gear_recipe_id.bom_line_ids",
        "gear_docket_ids.recipe_id",
        "gear_docket_ids.recipe_id.bom_line_ids",
    )
    def _compute_gear_recipe_line_ids(self):
        for workorder in self:
            recipe = workorder.gear_recipe_id
            if not recipe:
                primary_docket = workorder._gear_get_primary_docket(create_if_missing=False)
                recipe = primary_docket.recipe_id if primary_docket else False
            workorder.gear_recipe_line_ids = recipe.bom_line_ids if recipe else False

    @api.depends("gear_docket_ids.docket_batch_ids")
    def _compute_gear_batch_ids(self):
        for workorder in self:
            batches = workorder.gear_docket_ids.mapped("docket_batch_ids")
            workorder.gear_batch_ids = batches

    @api.depends(
        "gear_docket_ids.qty_m3",
        "gear_docket_ids.tm_number",
        "gear_docket_ids.driver_name",
        "gear_docket_ids.operator_user_id",
        "gear_docket_ids.recipe_id",
        "gear_docket_ids.batching_time",
        "gear_docket_ids.docket_no",
        "gear_docket_ids.customer_id",
        "gear_docket_ids.cycle_reason_type",
    )
    def _compute_primary_docket_fields(self):
        for workorder in self:
            docket = workorder.gear_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance").sorted(
                key=lambda d: (d.date or fields.Date.today(), d.id)
            )[:1]
            docket = docket and docket[0] or False
            workorder.gear_docket_qty_m3 = docket.qty_m3 if docket else 0.0
            workorder.gear_docket_tm_number = docket.tm_number if docket else False
            workorder.gear_docket_driver_name = docket.driver_name if docket else False
            workorder.gear_docket_operator_user_id = docket.operator_user_id if docket else False
            workorder.gear_docket_recipe_id = docket.recipe_id if docket else False
            workorder.gear_docket_batching_time = docket.batching_time if docket else False
            workorder.gear_docket_no = docket.docket_no if docket else False
            workorder.gear_docket_customer_id = docket.customer_id if docket else (
                workorder.production_id.x_sale_order_id.partner_id if workorder.production_id else False
            )

    def _gear_get_primary_docket(self, create_if_missing=False):
        self.ensure_one()
        docket = self.gear_docket_ids.filtered(lambda d: d.cycle_reason_type != "maintenance").sorted(
            key=lambda d: (d.date or fields.Date.today(), d.id)
        )[:1]
        if docket:
            return docket[0]
        if not create_if_missing:
            return False

        production = self.production_id
        sale_order = getattr(production, "x_sale_order_id", False)
        if not production or not sale_order:
            return False

        docket_model = self.env["gear.rmc.docket"]
        monthly_order = getattr(production, "x_monthly_order_id", False)
        date_value = fields.Date.context_today(self)
        if self.date_start or production.date_start:
            try:
                wo_start = self.date_start or production.date_start
                local_date = False
                if monthly_order:
                    user_tz = monthly_order._gear_get_user_tz()
                    local_date = monthly_order._gear_datetime_to_local_date(wo_start, user_tz)
                if not local_date:
                    local_dt = fields.Datetime.context_timestamp(self, wo_start)
                    local_date = local_dt.date() if local_dt else False
                date_value = local_date or date_value
            except Exception:
                pass

        docket_vals = {
            "so_id": sale_order.id,
            "production_id": production.id,
            "workorder_id": self.id,
            "workcenter_id": self.workcenter_id.id if self.workcenter_id else False,
            "monthly_order_id": monthly_order.id if monthly_order else False,
            "docket_no": docket_model._gear_allocate_docket_no(sale_order),
            "name": f"{production.name}-{date_value}" if production and production.name else False,
            "date": date_value,
            "source": "manual",
            "state": "draft",
            "quantity_ordered": self.gear_qty_planned or self.qty_production or production.product_qty,
            "payload_timestamp": self.date_start or production.date_start,
        }
        docket = docket_model.create(docket_vals)
        return docket

    def _inverse_primary_docket_fields(self):
        for workorder in self:
            docket = workorder._gear_get_primary_docket(create_if_missing=True)
            if not docket:
                continue
            vals = {}
            if workorder.gear_docket_qty_m3 is not None:
                vals["qty_m3"] = workorder.gear_docket_qty_m3
            if workorder.gear_docket_tm_number is not None:
                vals["tm_number"] = workorder.gear_docket_tm_number
            if workorder.gear_docket_driver_name is not None:
                vals["driver_name"] = workorder.gear_docket_driver_name
            if workorder.gear_docket_operator_user_id:
                vals["operator_user_id"] = workorder.gear_docket_operator_user_id.id
            elif "gear_docket_operator_user_id" in workorder._fields and workorder.gear_docket_operator_user_id is False:
                vals["operator_user_id"] = False
            if workorder.gear_docket_recipe_id:
                vals["recipe_id"] = workorder.gear_docket_recipe_id.id
            elif workorder.gear_docket_recipe_id is False:
                vals["recipe_id"] = False
            if workorder.gear_docket_batching_time is not None:
                vals["batching_time"] = workorder.gear_docket_batching_time
            if workorder.gear_docket_no:
                vals["docket_no"] = workorder.gear_docket_no
            elif workorder.gear_docket_no is False:
                vals["docket_no"] = False
            if workorder.gear_docket_customer_id:
                vals["customer_id"] = workorder.gear_docket_customer_id.id
            elif workorder.gear_docket_customer_id is False:
                vals["customer_id"] = False
            if workorder.scrap_qty is not None:
                vals["quantity_produced"] = max((workorder.gear_docket_qty_m3 or 0.0) - workorder.scrap_qty, 0.0)

            if vals:
                docket.write(vals)

    @api.onchange("production_id")
    def _onchange_production_id_set_recipe_product(self):
        if self.production_id and not self.gear_recipe_product_id:
            self.gear_recipe_product_id = self.production_id.product_id

    @api.onchange("gear_recipe_product_id")
    def _onchange_recipe_product(self):
        if self.gear_recipe_id and self.gear_recipe_id.product_tmpl_id != self.gear_recipe_product_id.product_tmpl_id:
            self.gear_recipe_id = False

    def _gear_set_qty_producing(self):
        """Keep the MO qty_producing aligned to the chunk size for this workorder."""
        for workorder in self:
            production = workorder.production_id
            if not production:
                continue
            target_qty = workorder.gear_qty_planned or workorder.qty_production
            if not target_qty:
                continue
            if production.product_uom_id:
                target_qty = production.product_uom_id.round(target_qty)
                if production.product_uom_id.is_zero(target_qty):
                    continue
            if production.qty_producing != target_qty:
                production.qty_producing = target_qty
                try:
                    production._set_qty_producing(False)
                except Exception:
                    # If stock moves are missing, allow the work order to keep running; operator can retry.
                    pass

    def button_start(self, raise_on_invalid_state=False, bypass=False):
        self._gear_set_qty_producing()
        res = super().button_start(raise_on_invalid_state=raise_on_invalid_state, bypass=bypass)
        self._gear_update_docket_states(target_state="in_production")
        return res

    def button_finish(self):
        workorders = self.with_context(allow_qty_produced_done=True)
        workorders._gear_set_qty_producing()
        res = super(MrpWorkorder, workorders).button_finish()
        for workorder in workorders:
            if (
                workorder.gear_qty_planned
                and workorder.qty_produced
                and workorder.qty_produced > workorder.gear_qty_planned
            ):
                # Cap the produced quantity to the planned chunk to avoid blocking future chunk creation.
                workorder.qty_produced = workorder.gear_qty_planned
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
        allowed_states = {"blocked", "ready", "progress", "done", "cancel"}
        sanitized_vals = []
        for vals in vals_list:
            vals = dict(vals)
            state = vals.get("state")
            if not state or state not in allowed_states:
                vals["state"] = "ready"
            sanitized_vals.append(vals)

        workorders = super().create(sanitized_vals)
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
            docket_no = docket_model._gear_allocate_docket_no(sale_order)
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
                "name": base_no,
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
        MonthlyOrder = self.env["gear.rmc.monthly.order"]
        for workorder in self:
            production = workorder.production_id
            if not production:
                continue
            if production.workorder_ids.filtered(lambda wo: wo.state == "progress"):
                continue
            workcenter = workorder.workcenter_id or production.workorder_ids[:1].workcenter_id
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
            elif not next_candidate and not pending_entries:
                if not workcenter:
                    _logger.info(
                        "Cannot auto-create next work order for %s due to missing workcenter.",
                        production.display_name,
                    )
                    continue
                active_workorders = production.workorder_ids.filtered(lambda w: w.state not in ("cancel",))
                open_workorders = active_workorders.filtered(lambda w: w.state not in ("done", "cancel"))
                planned_qty = sum((wo.gear_qty_planned or wo.qty_production or 0.0) for wo in open_workorders)
                remaining_qty = round((production.product_qty or 0.0) - planned_qty, 2)
                if remaining_qty <= 0:
                    production.x_pending_workorder_chunks = []
                    continue
                param = self.env["ir.config_parameter"].sudo().get_param("gear_on_rent.workorder_max_qty", "7.0")
                try:
                    max_chunk = float(param)
                except (TypeError, ValueError):
                    max_chunk = 7.0
                if max_chunk <= 0:
                    max_chunk = 7.0

                qty_splits = MonthlyOrder._gear_split_quantity(remaining_qty, max_chunk)
                existing_sequences = [seq for seq in active_workorders.mapped("gear_chunk_sequence") if seq]
                seq = max(existing_sequences) + 1 if existing_sequences else len(active_workorders) + 1
                base_name = f"{production.name} / {workcenter.display_name}"
                base_start_dt = workorder.date_finished or fields.Datetime.now()

                name = base_name if seq == 1 else f"{base_name} ({seq})"
                first_qty = qty_splits.pop(0)
                vals = {
                    "name": name,
                    "production_id": production.id,
                    "workcenter_id": workcenter.id,
                    "qty_production": first_qty,
                    "date_start": base_start_dt,
                    "date_finished": base_start_dt,
                    "sequence": seq,
                    "gear_chunk_sequence": seq,
                    "gear_qty_planned": first_qty,
                }
                next_candidate = Workorder.create(vals)
                created = True
                pending_entries = []
                next_seq = seq + 1
                for qty in qty_splits:
                    pending_entries.append(
                        {
                            "seq": next_seq,
                            "qty": qty,
                            "name": base_name if next_seq == 1 else f"{base_name} ({next_seq})",
                            "date_start": fields.Datetime.to_string(base_start_dt),
                            "date_finished": fields.Datetime.to_string(base_start_dt),
                        }
                    )
                    next_seq += 1
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

    def action_open_scrap_wizard(self):
        """Open the standard Odoo scrap popup prefilled for this work order."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("stock.action_stock_scrap")
        raw_ctx = action.get("context", {}) or {}
        if isinstance(raw_ctx, str):
            from odoo.tools.safe_eval import safe_eval

            raw_ctx = safe_eval(raw_ctx)
        ctx = dict(raw_ctx or {})

        production = self.production_id
        company = self.company_id or self.env.company

        ctx["default_workorder_id"] = self.id
        if production:
            ctx.setdefault("default_production_id", production.id)
            if production.bom_id:
                ctx.setdefault("default_gear_bom_id", production.bom_id.id)
        if production and production.name:
            ctx.setdefault("default_origin", production.name)
        if production and production.product_id:
            ctx.setdefault("default_product_id", production.product_id.id)
        if company:
            ctx.setdefault("default_company_id", company.id)

        if production and production.location_src_id:
            ctx.setdefault("default_location_id", production.location_src_id.id)
        else:
            stock_location = getattr(company, "stock_warehouse_id", False)
            stock_location = stock_location and stock_location.lot_stock_id
            if stock_location:
                ctx.setdefault("default_location_id", stock_location.id)

        scrap_location = getattr(company, "stock_scrap_location_id", False)
        if not scrap_location:
            scrap_location = self.env.ref("stock.stock_location_scrap", raise_if_not_found=False)
        if scrap_location:
            ctx.setdefault("default_scrap_location_id", scrap_location.id)

        # Force opening directly in form view for quick entry.
        form_view = self.env.ref("stock.stock_scrap_form_view", raise_if_not_found=False) or self.env.ref(
            "stock.view_stock_scrap_form", raise_if_not_found=False
        )
        views = [(form_view.id, "form")] if form_view else [(False, "form")]

        action.update(
            {
                "context": ctx,
                "target": "new",
                "view_mode": "form",
                "views": views,
                "res_id": False,
            }
        )
        return action
