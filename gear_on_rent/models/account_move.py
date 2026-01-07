import base64
from calendar import monthrange

from odoo import _, api, fields, models
from odoo.tools import format_date, format_datetime


class AccountMove(models.Model):
    """Extends invoices with Gear On Rent billing metadata."""

    _inherit = "account.move"

    x_billing_category = fields.Selection(
        selection=[
            ("rental", "Rental"),
            ("rmc", "RMC"),
            ("plant", "Plant"),
        ],
        string="Billing Category",
        copy=False,
        tracking=True,
    )
    gear_month_end_version = fields.Integer(
        string="Month-End Report Version",
        default=1,
        copy=False,
    )
    gear_monthly_order_id = fields.Many2one(
        comodel_name="gear.rmc.monthly.order",
        string="Monthly Work Order",
        copy=False,
    )
    gear_period_start = fields.Date(string="Billing From", copy=False)
    gear_period_end = fields.Date(string="Billing To", copy=False)
    gear_target_qty = fields.Float(string="Monthly MGQ", copy=False)
    gear_adjusted_target_qty = fields.Float(string="Adjusted MGQ", copy=False)
    gear_prime_output_qty = fields.Float(string="Prime Output (m³)", copy=False)
    gear_optimized_standby_qty = fields.Float(string="Optimized Standby (m³)", copy=False)
    gear_ngt_hours = fields.Float(string="NGT Hours", copy=False)
    gear_loto_chargeable_hours = fields.Float(string="LOTO Chargeable Hours", copy=False)
    gear_waveoff_applied_hours = fields.Float(string="Wave-Off Applied (Hours)", copy=False)
    gear_waveoff_allowance_hours = fields.Float(string="Wave-Off Allowance (Hours)", copy=False)
    gear_diesel_overrun_litre = fields.Float(string="Diesel Overrun (L)", copy=False)
    gear_diesel_overrun_amount = fields.Monetary(
        string="Diesel Overrun Amount",
        currency_field="currency_id",
        copy=False,
    )
    gear_log_summary_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Log Summary Attachment",
        copy=False,
    )
    gear_month_end_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Month-End Attachment",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if not move.x_billing_category:
                move._gear_sync_category_from_sale_orders()
        return moves

    def write(self, vals):
        res = super().write(vals)
        missing_category_moves = self.filtered(lambda m: not m.x_billing_category)
        if missing_category_moves:
            missing_category_moves._gear_sync_category_from_sale_orders()
        return res

    def _gear_sync_category_from_sale_orders(self):
        for move in self:
            if move.x_billing_category:
                continue
            orders = move._gear_get_related_sale_orders()
            categories = [cat for cat in orders.mapped("x_billing_category") if cat]
            if categories:
                move.x_billing_category = categories[0]

    def _gear_get_related_sale_orders(self):
        self.ensure_one()
        return self.invoice_line_ids.mapped("sale_line_ids.order_id")

    def _gear_get_month_end_payload(self):
        self.ensure_one()
        month_date = self.invoice_date or fields.Date.context_today(self)
        month_date = fields.Date.to_date(month_date)
        month_start = month_date.replace(day=1)
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        month_key = month_start

        orders = self._gear_get_related_sale_orders()
        contract = orders[:1]
        ngt_requests = self.env["gear.ngt.request"].browse()
        loto_requests = self.env["gear.loto.request"].browse()
        if contract:
            ngt_requests = self.env["gear.ngt.request"].search(
                [
                    ("so_id", "=", contract.id),
                    ("month", "=", month_key),
                    ("state", "=", "approved"),
                ],
                order="date_start asc",
            )
            loto_requests = self.env["gear.loto.request"].search(
                [
                    ("so_id", "=", contract.id),
                    ("month", "=", month_key),
                    ("state", "=", "approved"),
                ],
                order="date_start asc",
            )

        month_orders = self.gear_monthly_order_id
        if not month_orders:
            month_orders = self.env["gear.rmc.monthly.order"]
            if contract:
                month_orders = month_orders.search(
                    [
                        ("so_id", "=", contract.id),
                        ("date_start", ">=", month_start),
                        ("date_start", "<=", month_end),
                    ]
                )

        if month_orders:
            summary = month_orders._gear_compute_billing_summary()
            cooling = summary["cooling"]
            normal = summary["normal"]
            total_target = cooling["target_qty"] + normal["target_qty"]
            total_adjusted = cooling["adjusted_target_qty"] + normal["adjusted_target_qty"]
            total_prime = cooling["prime_output_qty"] + normal["prime_output_qty"]
            total_standby = normal["standby_qty"]
            total_ngt_m3 = cooling["ngt_m3"] + normal["ngt_m3"]
            ngt_hours = self.gear_ngt_hours or (cooling["ngt_hours"] + normal["ngt_hours"])
            waveoff_applied = self.gear_waveoff_applied_hours or (
                cooling["waveoff_applied_hours"] + normal["waveoff_applied_hours"]
            )
            loto_chargeable = self.gear_loto_chargeable_hours or (
                cooling["waveoff_chargeable_hours"] + normal["waveoff_chargeable_hours"]
            )
            waveoff_allowance = self.gear_waveoff_allowance_hours or (contract.x_loto_waveoff_hours if contract else 0.0)
            diesel_excess_litre = self.gear_diesel_overrun_litre or (
                cooling["diesel_excess_litre"] + normal["diesel_excess_litre"]
            )
            diesel_excess_amount = self.gear_diesel_overrun_amount or (
                cooling["diesel_excess_amount"] + normal["diesel_excess_amount"]
            )

            allowed_wastage_qty = sum(month_orders.mapped("mwo_allowed_wastage_qty"))
            actual_scrap_qty = sum(month_orders.mapped("mwo_actual_scrap_qty"))
            over_wastage_qty = max(actual_scrap_qty - allowed_wastage_qty, 0.0)
            deduction_qty = sum(month_orders.mapped("mwo_deduction_qty")) or over_wastage_qty
            prime_output_total = sum(month_orders.mapped("mwo_prime_output_qty")) or total_prime

            target_qty = self.gear_target_qty or total_target
            adjusted_target = self.gear_adjusted_target_qty or total_adjusted or target_qty
            prime_output = self.gear_prime_output_qty or prime_output_total
            optimized_standby = self.gear_optimized_standby_qty or total_standby

            dockets = month_orders.mapped("docket_ids").filtered(lambda d: month_start <= d.date <= month_end)
            dockets = dockets.sorted(key=lambda d: (d.date, d.id))
            productions = month_orders.mapped("production_ids").filtered(
                lambda p: p.date_start and month_start <= fields.Datetime.to_datetime(p.date_start).date() <= month_end
            )
            productions = productions.filtered(
                lambda p: (p.x_prime_output_qty or p.qty_produced or p.actual_scrap_qty or 0.0) > 0.0
            )
            productions = productions.sorted(key=lambda p: (p.date_start or fields.Datetime.now(), p.id))
            manufacturing_orders = [
                {
                    "date_start": format_datetime(self.env, production.date_start) if production.date_start else "",
                    "reference": production.name,
                    "is_cooling": bool(production.x_is_cooling_period),
                    "daily_mgq": production.x_daily_target_qty or 0.0,
                    "adjusted_mgq": production.x_adjusted_target_qty or 0.0,
                    "prime_output": production.x_prime_output_qty or 0.0,
                    "allowed_wastage": production.wastage_allowed_qty,
                    "actual_scrap": production.actual_scrap_qty,
                    "over_wastage": production.over_wastage_qty,
                    "deduction": production.deduction_qty,
                    "optimized_standby": production.x_optimized_standby_qty or 0.0,
                    "ngt_hours": production.x_ngt_hours or 0.0,
                    "loto_hours": production.x_loto_hours or 0.0,
                }
                for production in productions
            ]
            cooling_totals = {
                "target_qty": cooling["target_qty"],
                "prime_output_qty": cooling["prime_output_qty"],
                "ngt_m3": cooling["ngt_m3"],
            }
            normal_totals = {
                "target_qty": normal["target_qty"],
                "prime_output_qty": normal["prime_output_qty"],
                "standby_qty": normal["standby_qty"],
                "ngt_m3": normal["ngt_m3"],
            }
        else:
            docket_env = self.env["gear.rmc.docket"]
            dockets = docket_env.search(
                [
                    ("so_id", "in", orders.ids),
                    ("date", ">=", month_start),
                    ("date", "<=", month_end),
                ],
                order="date asc",
            )
            target_qty = self.gear_target_qty or (contract.x_monthly_mgq if contract else 0.0)
            adjusted_target = self.gear_adjusted_target_qty or target_qty
            prime_output = self.gear_prime_output_qty or sum(dockets.mapped("qty_m3"))
            optimized_standby = self.gear_optimized_standby_qty or max(adjusted_target - prime_output, 0.0)
            ngt_hours = self.gear_ngt_hours or 0.0
            waveoff_applied = self.gear_waveoff_applied_hours or 0.0
            loto_chargeable = self.gear_loto_chargeable_hours or 0.0
            waveoff_allowance = self.gear_waveoff_allowance_hours or (contract.x_loto_waveoff_hours if contract else 0.0)
            total_ngt_m3 = 0.0
            diesel_excess_litre = self.gear_diesel_overrun_litre or 0.0
            diesel_excess_amount = self.gear_diesel_overrun_amount or 0.0
            allowed_wastage_qty = 0.0
            actual_scrap_qty = 0.0
            over_wastage_qty = 0.0
            deduction_qty = 0.0
            cooling_totals = {
                "target_qty": 0.0,
                "prime_output_qty": 0.0,
                "ngt_m3": 0.0,
            }
            normal_totals = {
                "target_qty": target_qty,
                "prime_output_qty": prime_output,
                "standby_qty": optimized_standby,
                "ngt_m3": 0.0,
            }
            manufacturing_orders = []
        if month_orders:
            total_ngt_m3 = cooling["ngt_m3"] + normal["ngt_m3"]

        payload = {
            "invoice_name": self.name,
            "month_label": format_date(self.env, month_start, date_format="MMMM yyyy"),
            "version_label": f"v{self.gear_month_end_version}",
            "contract_name": contract.name if contract else "",
            "customer_name": self.partner_id.display_name,
            "inventory_mode": dict(month_orders[:1]._fields['x_inventory_mode'].selection).get(month_orders[:1].x_inventory_mode) if month_orders and month_orders[:1].x_inventory_mode else "N/A",
            "real_warehouse": month_orders[:1].x_real_warehouse_id.display_name if month_orders and month_orders[:1].x_real_warehouse_id else "N/A",
            "target_qty": target_qty,
            "adjusted_target_qty": adjusted_target,
            "ngt_hours": ngt_hours,
            "ngt_qty": total_ngt_m3 if month_orders else 0.0,
            "loto_total_hours": waveoff_applied + loto_chargeable,
            "waveoff_allowance": waveoff_allowance,
            "waveoff_applied": waveoff_applied,
            "loto_chargeable_hours": loto_chargeable,
            "prime_output_qty": prime_output,
            "allowed_wastage_qty": allowed_wastage_qty,
            "actual_scrap_qty": actual_scrap_qty,
            "over_wastage_qty": over_wastage_qty,
            "deduction_qty": deduction_qty,
            "optimized_standby": optimized_standby,
            "diesel_excess_litre": diesel_excess_litre,
            "diesel_excess_amount": diesel_excess_amount,
            "cooling_totals": cooling_totals,
            "normal_totals": normal_totals,
            "materials_shortage": contract.gear_materials_shortage_note if contract else "",
            "manpower_notes": contract.gear_manpower_note if contract else "",
            "asset_notes": contract.gear_asset_note if contract else "",
            "dockets": [
                {
                    "docket_no": docket.docket_no,
                    "date": format_date(self.env, docket.date),
                    "qty_m3": docket.qty_m3,
                    "workcenter": docket.workcenter_id.display_name,
                    "runtime_minutes": docket.runtime_minutes,
                    "idle_minutes": docket.idle_minutes,
                    "slump": docket.slump,
                    "alarms": ", ".join(docket.alarm_codes or []),
                    "notes": docket.notes,
                }
                for docket in dockets
            ],
            "manufacturing_orders": manufacturing_orders,
            "loto_requests": [
                {
                    "name": request.name,
                    "period_start": format_datetime(self.env, request.date_start) if request.date_start else "",
                    "period_end": format_datetime(self.env, request.date_end) if request.date_end else "",
                    "hours_total": request.hours_total or 0.0,
                    "hours_waveoff": request.hours_waveoff_applied or 0.0,
                    "hours_chargeable": request.hours_chargeable or 0.0,
                    "reason": request.reason or "",
                }
                for request in loto_requests
            ],
            "ngt_requests": [
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
                    "qty": request.ngt_qty
                    or ((request.hours_total or 0.0) * (request.ngt_hourly_factor_effective or request.ngt_hourly_rate or request.ngt_hourly_prorata_factor or 0.0)),
                    "rate_per_m3": (request.total_expense / request.ngt_qty) if request.ngt_qty else 0.0,
                    "meter_start": request.meter_reading_start or 0.0,
                    "meter_end": request.meter_reading_end or 0.0,
                    "meter_units": request.electricity_units or 0.0,
                    "employee_expense": request.employee_expense or 0.0,
                    "land_rent": request.land_rent or 0.0,
                    "electricity_rate": request.electricity_unit_rate or 0.0,
                    "electricity_expense": request.electricity_expense or 0.0,
                    "total_expense": request.total_expense or 0.0,
                    "reason": request.reason or "",
                    "currency_symbol": request.currency_id and request.currency_id.symbol or (request.company_id.currency_id and request.company_id.currency_id.symbol) or "",
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
                for request in ngt_requests
            ],
            "show_cooling": any(
                [
                    cooling_totals.get("target_qty"),
                    cooling_totals.get("prime_output_qty"),
                    cooling_totals.get("ngt_m3"),
                ]
            ),
            "show_wastage": any(
                [
                    prime_output,
                    allowed_wastage_qty,
                    actual_scrap_qty,
                    over_wastage_qty,
                    deduction_qty,
                ]
            ),
            "show_diesel": bool(diesel_excess_litre or diesel_excess_amount),
        }
        return payload

    def _gear_generate_invoice_pdf(self):
        self.ensure_one()
        report = self.partner_id.invoice_template_pdf_report_id or self.env.ref("account.account_invoices", raise_if_not_found=False)
        if not report:
            return False, False
        try:
            pdf_content, report_type = report._render_qweb_pdf(report.id, res_ids=self.ids)
        except Exception:
            return False, False
        if report_type != "pdf" or not pdf_content:
            return False, False
        filename = self._get_invoice_report_filename(report=report)
        return base64.b64encode(pdf_content), filename

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move, vals in zip(moves, vals_list):
            if move.move_type == "out_refund" and not move.gear_monthly_order_id:
                src = False
                reversed_id = vals.get("reversed_entry_id")
                if reversed_id:
                    src = self.browse(reversed_id)
                elif self.env.context.get("active_model") == "account.move":
                    active_ids = self.env.context.get("active_ids") or []
                    src = self.browse(active_ids[:1])
                if src and src.gear_monthly_order_id:
                    move.gear_monthly_order_id = src.gear_monthly_order_id.id
            if not move.x_billing_category:
                move._gear_sync_category_from_sale_orders()
        return moves
    def action_post(self):
        res = super().action_post()
        # Log invoice posting on the related Monthly Work Order
        for move in self.filtered(lambda m: m.gear_monthly_order_id and m.move_type in ("out_invoice", "out_refund")):
            doc_label = _("Invoice") if move.move_type == "out_invoice" else _("Credit/Debit Note")
            attachment_id = False
            pdf_data, filename = move._gear_generate_invoice_pdf()
            if pdf_data:
                attachment_vals = {
                    "name": filename.replace("/", "_") if filename else f"{move.display_name}.pdf".replace("/", "_"),
                    "type": "binary",
                    "datas": pdf_data,
                    "mimetype": "application/pdf",
                    "res_model": move.gear_monthly_order_id._name,
                    "res_id": move.gear_monthly_order_id.id,
                }
                attachment_id = self.env["ir.attachment"].create(attachment_vals).id

            body = _("%(label)s %(name)s posted.") % {"label": doc_label, "name": move.display_name}
            if attachment_id:
                body += " " + _("PDF attached.")

            move.gear_monthly_order_id.message_post(
                body=body,
                subtype_xmlid="mail.mt_note",
                attachment_ids=[attachment_id] if attachment_id else False,
            )
        self._gear_attach_month_end_report()
        return res

    def _gear_attach_log_summary(self):
        report = self.env.ref("gear_on_rent.action_report_log_summary", raise_if_not_found=False)
        if not report:
            return
        for move in self:
            pdf_content, report_type = report._render_qweb_pdf(report.id, res_ids=move.ids)
            if report_type != "pdf":
                continue
            filename = "%s - %s.pdf" % (move.name or _("Invoice"), _("Log Summary"))
            attachment_vals = {
                "name": filename.replace("/", "_"),
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "mimetype": "application/pdf",
                "res_model": move._name,
                "res_id": move.id,
            }
            attachment = move.gear_log_summary_attachment_id
            if attachment:
                attachment.write(attachment_vals)
            else:
                attachment = self.env["ir.attachment"].create(attachment_vals)
                move.gear_log_summary_attachment_id = attachment.id

    def _gear_attach_month_end_report(self):
        report = self.env.ref("gear_on_rent.action_report_month_end", raise_if_not_found=False)
        if not report:
            return
        for move in self.filtered(lambda m: m.x_billing_category == "rmc"):
            pdf_content, report_type = report._render_qweb_pdf(report.id, res_ids=move.ids)
            if report_type != "pdf":
                continue
            filename = "%s - %s.pdf" % (move.name or _("Invoice"), _("Month-End Report"))
            attachment_vals = {
                "name": filename.replace("/", "_"),
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "mimetype": "application/pdf",
                "res_model": move._name,
                "res_id": move.id,
            }
            attachment = move.gear_month_end_attachment_id
            if attachment:
                attachment.write(attachment_vals)
            else:
                attachment = self.env["ir.attachment"].search(
                    [
                        ("res_model", "=", move._name),
                        ("res_id", "=", move.id),
                        ("name", "=", filename.replace("/", "_")),
                    ],
                    limit=1,
                )
                if attachment:
                    attachment.write(attachment_vals)
                else:
                    attachment = self.env["ir.attachment"].create(attachment_vals)
                move.gear_month_end_attachment_id = attachment.id
