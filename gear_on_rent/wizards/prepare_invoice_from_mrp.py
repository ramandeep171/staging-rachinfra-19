from calendar import monthrange
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PrepareInvoiceFromMrp(models.TransientModel):
    """Aggregate MRP work orders and dockets into an invoice."""

    _name = "gear.prepare.invoice.mrp"
    _description = "Prepare Gear On Rent Invoice (MRP)"

    monthly_order_id = fields.Many2one(
        comodel_name="gear.rmc.monthly.order",
        string="Monthly Work Order",
        domain=[("state", "!=", "draft")],
        required=True,
    )
    so_id = fields.Many2one(
        comodel_name="sale.order",
        related="monthly_order_id.so_id",
        store=False,
        readonly=True,
    )
    currency_id = fields.Many2one("res.currency", related="so_id.currency_id", store=False, readonly=True)
    invoice_date = fields.Date(
        string="Invoice Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    period_start = fields.Date(string="Bill From")
    period_end = fields.Date(string="Bill To")
    x_unproduced_delta = fields.Float(
        string="Unproduced Rate Delta",
        default=50.0,
        help="Deduction from the base rate when billing unproduced MGQ.",
    )
    prime_output_qty = fields.Float(
        string="Prime Output (m³)",
        related="monthly_order_id.prime_output_qty",
        store=False,
        readonly=True,
    )
    optimized_standby_qty = fields.Float(
        string="Optimized Standby (m³)",
        related="monthly_order_id.optimized_standby_qty",
        store=False,
        readonly=True,
    )
    adjusted_target_qty = fields.Float(
        string="Adjusted MGQ",
        related="monthly_order_id.adjusted_target_qty",
        store=False,
        readonly=True,
    )
    downtime_relief_qty = fields.Float(
        string="NGT Relief (m³)",
        related="monthly_order_id.downtime_relief_qty",
        store=False,
        readonly=True,
    )
    ngt_hours = fields.Float(
        string="NGT Hours",
        related="monthly_order_id.ngt_hours",
        store=False,
        readonly=True,
    )
    loto_chargeable_hours = fields.Float(
        string="LOTO Chargeable Hours",
        related="monthly_order_id.waveoff_hours_chargeable",
        store=False,
        readonly=True,
    )
    diesel_excess_litre = fields.Float(
        string="Excess Diesel (L)",
        related="monthly_order_id.excess_diesel_litre_total",
        store=False,
        readonly=True,
    )
    diesel_excess_amount = fields.Monetary(
        string="Diesel Overrun Amount",
        related="monthly_order_id.excess_diesel_amount_total",
        currency_field="currency_id",
        store=False,
        readonly=True,
    )

    @api.onchange("monthly_order_id")
    def _onchange_monthly_order(self):
        if self.monthly_order_id:
            start, end = self._gear_default_period(self.monthly_order_id)
            self.period_start = start
            self.period_end = end

    def _gear_default_period(self, monthly):
        start = monthly.date_start
        end = monthly.date_end
        last_invoice = self._gear_last_invoice(monthly)
        if last_invoice and last_invoice.gear_period_end:
            start = last_invoice.gear_period_end + timedelta(days=1)
        if start and end and start > end:
            start = end
        return start, end

    def _gear_last_invoice(self, monthly):
        return self.env["account.move"].search(
            [
                ("gear_monthly_order_id", "=", monthly.id),
                ("move_type", "=", "out_invoice"),
                ("state", "!=", "cancel"),
            ],
            order="gear_period_end desc, id desc",
            limit=1,
        )

    def action_prepare_invoice(self):
        self.ensure_one()
        monthly = self.monthly_order_id
        order = monthly.so_id
        if not order:
            raise UserError(_("Please select a monthly work order linked to a sale order."))
        if order.x_billing_category != "rmc":
            raise UserError(_("This wizard can only prepare invoices for RMC contracts."))
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise UserError(_("Bill From date cannot be after Bill To date."))
        existing_invoice = self._gear_last_invoice(monthly)
        billable_lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if not billable_lines:
            raise UserError(_("The sale order must have at least one billable product line."))

        def _classify(line):
            parts = [
                line.product_id.display_name or "",
                " ".join(line.product_id.product_template_attribute_value_ids.mapped("name") or []),
                line.name or "",
            ]
            label = " ".join(parts).lower()
            if "ngt" in label or "no-generation" in label:
                return "ngt"
            if "standby" in label or "shortfall" in label or "optimized" in label:
                return "standby"
            if "prime" in label:
                return "prime"
            return ""

        line_by_mode = {"prime": None, "standby": None, "ngt": None}
        for line in billable_lines:
            mode = _classify(line)
            if mode and not line_by_mode[mode]:
                line_by_mode[mode] = line

        main_line = line_by_mode.get("prime") or billable_lines[:1]

        def _extract_taxes(line):
            taxes_field = getattr(line, "tax_id", False) or getattr(line, "taxes_id", self.env["account.tax"])
            if taxes_field:
                taxes_field = taxes_field.filtered(lambda t: t.company_id == order.company_id)
            if taxes_field and taxes_field.exists():
                return taxes_field

            product = line.product_id if line else False
            if not product:
                return self.env["account.tax"]

            taxes = product.taxes_id.filtered(lambda t: t.company_id == order.company_id)
            if not taxes:
                taxes = getattr(order.company_id, "account_sale_tax_id", False) or self.env["account.tax"]
            fiscal_position = order.fiscal_position_id or order.partner_id.property_account_position_id
            if fiscal_position:
                # On v19 the fiscal position mapper no longer accepts product/partner kwargs.
                taxes = fiscal_position.map_tax(taxes)
            return taxes

        def _extract_analytic(line):
            distribution = getattr(line, "analytic_distribution", {}) or {}
            return {str(key): value for key, value in distribution.items() if value}

        def _compose_line_name(product, label):
            product_label = product.display_name or product.name or _("Unnamed Product")
            return f"{product_label} - {label}"

        taxes_prime = _extract_taxes(line_by_mode["prime"] or main_line)
        taxes_standby = _extract_taxes(line_by_mode["standby"] or main_line)
        taxes_ngt = _extract_taxes(line_by_mode["ngt"] or main_line)
        analytic_prime = _extract_analytic(line_by_mode["prime"] or main_line)
        analytic_standby = _extract_analytic(line_by_mode["standby"] or main_line)
        analytic_ngt = _extract_analytic(line_by_mode["ngt"] or main_line)

        if monthly.date_start:
            month_start = monthly.date_start.replace(day=1)
        else:
            today = fields.Date.context_today(self)
            month_start = today.replace(day=1)
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        period_start = self.period_start or monthly.date_start or month_start
        period_end = self.period_end or monthly.date_end or month_end
        if existing_invoice and existing_invoice.gear_period_end and period_start <= existing_invoice.gear_period_end:
            raise UserError(
                _("This Monthly Work Order is already billed through %s. Choose a start date after that.")
                % fields.Date.to_string(existing_invoice.gear_period_end)
            )
        if monthly.date_start and period_start < monthly.date_start:
            raise UserError(_("Bill From date cannot be before the Monthly Work Order start date."))
        if monthly.date_end and period_end > monthly.date_end:
            raise UserError(_("Bill To date cannot be after the Monthly Work Order end date."))

        def _production_local_date(prod):
            if not prod.date_start:
                return False
            try:
                tz_dt = fields.Datetime.context_timestamp(self, prod.date_start)
            except Exception:
                tz_dt = fields.Datetime.to_datetime(prod.date_start)
            return tz_dt.date() if tz_dt else False

        productions = monthly.production_ids.filtered(
            lambda p: _production_local_date(p) and period_start <= _production_local_date(p) <= period_end
        )
        dockets = monthly.docket_ids.filtered(lambda d: d.date and period_start <= d.date <= period_end)

        if not productions and not dockets:
            raise UserError(_("No production or dockets found in the selected period."))

        prime_output = sum(productions.mapped(lambda p: p.x_prime_output_qty or p.qty_produced or 0.0))
        # Use monthly snapshot as the base MGQ for all calculations to avoid overcounting summed daily targets.
        target_qty = (
            monthly.monthly_target_qty
            or monthly.x_monthly_mgq_snapshot
            or monthly.so_id.x_monthly_mgq
            or sum(productions.mapped(lambda p: p.x_daily_target_qty or p.product_qty or 0.0))
        )
        adjusted_target_qty = (
            monthly.adjusted_target_qty
            or max(target_qty - sum(productions.mapped(lambda p: p.x_relief_qty or 0.0)), 0.0)
        )
        manual_ops = self.env["gear.rmc.manual.operation"].search(
            [
                ("docket_id.monthly_order_id", "=", monthly.id),
                ("docket_id.date", ">=", period_start),
                ("docket_id.date", "<=", period_end),
                ("state", "=", "approved"),
            ]
        )
        manual_on_qty = sum(
            manual_ops.filtered(lambda m: m.recipe_display_mode == "on_production").mapped(
                lambda m: m.manual_qty_total or 0.0
            )
        )
        manual_after_qty = sum(
            manual_ops.filtered(lambda m: m.recipe_display_mode == "after_production").mapped(
                lambda m: m.manual_qty_total or 0.0
            )
        )
        ngt_hours = monthly.ngt_hours or sum(productions.mapped(lambda p: p.x_ngt_hours or 0.0))
        waveoff_chargeable = monthly.waveoff_hours_chargeable or sum(productions.mapped(lambda p: p.x_waveoff_hours_chargeable or 0.0))
        waveoff_applied = monthly.waveoff_hours_applied or sum(productions.mapped(lambda p: p.x_waveoff_hours_applied or 0.0))
        downtime_qty = monthly.downtime_relief_qty or sum(
            p._gear_hours_to_qty((p.x_ngt_hours or 0.0) + (p.x_waveoff_hours_chargeable or 0.0))
            for p in productions
        )
        diesel_excess_litre = sum(dockets.mapped(lambda d: d.excess_diesel_litre or 0.0))
        diesel_excess_amount = sum(dockets.mapped(lambda d: d.excess_diesel_amount or 0.0))

        # Fallback to monthly rollups when period-filtered aggregates are zero so invoicing isn't blocked.
        if prime_output <= 0 and monthly.prime_output_qty:
            prime_output = monthly.prime_output_qty
        if downtime_qty <= 0 and monthly.downtime_relief_qty:
            downtime_qty = monthly.downtime_relief_qty
        if ngt_hours <= 0 and monthly.ngt_hours:
            ngt_hours = monthly.ngt_hours
        if waveoff_chargeable <= 0 and monthly.waveoff_hours_chargeable:
            waveoff_chargeable = monthly.waveoff_hours_chargeable
        if waveoff_applied <= 0 and monthly.waveoff_hours_applied:
            waveoff_applied = monthly.waveoff_hours_applied
        if target_qty <= 0 and monthly.monthly_target_qty:
            target_qty = monthly.monthly_target_qty
        if adjusted_target_qty <= 0 and monthly.adjusted_target_qty:
            adjusted_target_qty = monthly.adjusted_target_qty

        # Optimized Standby = Monthly MGQ Snapshot - (Prime Output + NGT/Downtime Relief), floored at zero.
        if monthly and monthly.x_is_cooling_period:
            standby_qty = 0.0
        else:
            standby_qty = max((target_qty or 0.0) - (prime_output + downtime_qty), 0.0)

        # Prevent overlap with previous invoice end date
        if existing_invoice and existing_invoice.gear_period_end and period_start <= existing_invoice.gear_period_end:
            raise UserError(
                _("This Monthly Work Order is already billed through %s. Choose a start date after that.")
                % fields.Date.to_string(existing_invoice.gear_period_end)
            )

        if (
            prime_output <= 0
            and standby_qty <= 0
            and downtime_qty <= 0
            and manual_on_qty <= 0
            and manual_after_qty <= 0
        ):
            raise UserError(_("Nothing to invoice: no prime output, standby, or NGT quantities computed."))

        # Manual quantities reduce the optimized standby billed quantity.
        standby_billable_qty = max(standby_qty - manual_on_qty - manual_after_qty, 0.0)

        invoice_vals = {
            "move_type": "out_invoice",
            "partner_id": order.partner_invoice_id.id or order.partner_id.id,
            "currency_id": order.currency_id.id,
            "invoice_origin": order.name,
            "invoice_date": self.invoice_date,
            "x_billing_category": "rmc",
            "gear_monthly_order_id": monthly.id,
            "gear_period_start": period_start,
            "gear_period_end": period_end,
            "gear_target_qty": target_qty,
            "gear_adjusted_target_qty": adjusted_target_qty,
            "gear_prime_output_qty": prime_output,
            "gear_optimized_standby_qty": standby_billable_qty,
            "gear_ngt_hours": ngt_hours,
            "gear_loto_chargeable_hours": waveoff_chargeable,
            "gear_waveoff_applied_hours": waveoff_applied,
            "gear_waveoff_allowance_hours": order.x_loto_waveoff_hours,
            "gear_diesel_overrun_litre": diesel_excess_litre,
            "gear_diesel_overrun_amount": diesel_excess_amount,
        }

        period_start_label = fields.Date.to_string(period_start)
        period_end_label = fields.Date.to_string(period_end)

        line_commands = []

        def _section(label):
            return (
                0,
                0,
                {
                    "display_type": "line_section",
                    "name": label,
                },
            )

        prime_section_added = False

        def _ensure_prime_section():
            nonlocal prime_section_added
            if prime_section_added:
                return
            line_commands.append(_section(_("Prime Output")))
            prime_section_added = True

        if prime_output > 0:
            _ensure_prime_section()
            prime_product = (line_by_mode["prime"] or main_line).product_id
            prime_sale_line_ids = (line_by_mode["prime"] or main_line).ids
            prime_price_unit = (line_by_mode["prime"] or main_line).price_unit
            prime_label = _("Prime Output for %s - %s") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _compose_line_name(prime_product, prime_label),
                        "product_id": prime_product.id,
                        "quantity": prime_output,
                        "price_unit": prime_price_unit,
                        "tax_ids": [(6, 0, taxes_prime.ids)] if taxes_prime else False,
                        "analytic_distribution": analytic_prime or False,
                        "sale_line_ids": [(6, 0, prime_sale_line_ids)],
                    },
                )
            )

        if manual_on_qty:
            _ensure_prime_section()
            manual_product = (line_by_mode["prime"] or main_line).product_id
            manual_sale_line_ids = (line_by_mode["prime"] or main_line).ids
            manual_label = _("Manual Quantity (On Production) for %s - %s") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _compose_line_name(manual_product, manual_label),
                        "product_id": manual_product.id,
                        "quantity": manual_on_qty,
                        "price_unit": prime_price_unit,
                        "tax_ids": [(6, 0, taxes_prime.ids)] if taxes_prime else False,
                        "analytic_distribution": analytic_prime or False,
                        "sale_line_ids": [(6, 0, manual_sale_line_ids)],
                    },
                )
            )

        if manual_after_qty:
            _ensure_prime_section()
            manual_product = (line_by_mode["prime"] or main_line).product_id
            manual_sale_line_ids = (line_by_mode["prime"] or main_line).ids
            manual_label = _("Manual Quantity (After Production) for %s - %s") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _compose_line_name(manual_product, manual_label),
                        "product_id": manual_product.id,
                        "quantity": manual_after_qty,
                        "price_unit": prime_price_unit,
                        "tax_ids": [(6, 0, taxes_prime.ids)] if taxes_prime else False,
                        "analytic_distribution": analytic_prime or False,
                        "sale_line_ids": [(6, 0, manual_sale_line_ids)],
                    },
                )
            )

        if standby_billable_qty > 0:
            line_commands.append(_section(_("Optimized Standby")))
            standby_line = line_by_mode["standby"]
            if standby_line:
                standby_product = standby_line.product_id
                standby_price_unit = standby_line.price_unit
                standby_sale_line_ids = standby_line.ids
            else:
                standby_product = (line_by_mode["prime"] or main_line).product_id
                standby_price_unit = max(main_line.price_unit - self.x_unproduced_delta, 0.0)
                standby_sale_line_ids = main_line.ids
            standby_label = _("MGQ Shortfall Adjustment (%s - %s)") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _compose_line_name(standby_product, standby_label),
                        "product_id": standby_product.id,
                        "quantity": standby_billable_qty,
                        "price_unit": standby_price_unit,
                        "tax_ids": [(6, 0, taxes_standby.ids)] if taxes_standby else False,
                        "analytic_distribution": analytic_standby or False,
                        "sale_line_ids": [(6, 0, standby_sale_line_ids)],
                    },
                )
            )

        if downtime_qty > 0:
            line_commands.append(_section(_("NGT / Downtime Relief")))
            ngt_line = line_by_mode["ngt"]
            ngt_product = (ngt_line or main_line).product_id
            ngt_sale_line_ids = (ngt_line or main_line).ids
            # If NGT total expense is tracked, derive a per-unit rate from MGQ; otherwise fall back to SO line price.
            # Refresh NGT expense snapshot so we pick up the latest meter log and unit rate.
            monthly._compute_ngt_expense_totals()
            monthly._compute_ngt_effective_rate()
            mgq_base = (
                monthly.monthly_target_qty
                or monthly.adjusted_target_qty
                or monthly.mgq_monthly
                or monthly.x_monthly_mgq_snapshot
                or 0.0
            )
            ngt_price_unit = 0.0
            if monthly.ngt_total_expense and mgq_base:
                ngt_price_unit = monthly.ngt_total_expense / mgq_base
            else:
                ngt_price_unit = (ngt_line.price_unit if ngt_line else 0.0)
            ngt_label = _("NGT Relief (%s - %s)") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _compose_line_name(ngt_product, ngt_label),
                        "product_id": ngt_product.id,
                        "quantity": downtime_qty,
                        "price_unit": ngt_price_unit,
                        "tax_ids": [(6, 0, taxes_ngt.ids)] if taxes_ngt else False,
                        "analytic_distribution": analytic_ngt or False,
                        "sale_line_ids": [(6, 0, ngt_sale_line_ids)],
                    },
                )
            )

        if diesel_excess_amount > 0:
            label = _("HSD Loading Overrun Charges (%s - %s)") % (period_start_label, period_end_label)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": label,
                        "product_id": (line_by_mode["prime"] or main_line).product_id.id,
                        "quantity": 1,
                        "price_unit": diesel_excess_amount,
                        "tax_ids": [(6, 0, taxes_prime.ids)] if taxes_prime else False,
                        "analytic_distribution": analytic_prime or False,
                    },
                )
            )

        # Apply TDS 194C @ 2% as a withholding line on the invoice total (untaxed).
        tds_rate = 0.02
        untaxed_base = sum(
            cmd[2].get("quantity", 0.0) * cmd[2].get("price_unit", 0.0)
            for cmd in line_commands
            if not cmd[2].get("display_type")
        )
        if untaxed_base > 0:
            tds_amount = round(untaxed_base * tds_rate, 2)
            line_commands.append(_section(_("Withholding (TDS 194C)")))
            tds_product = (line_by_mode["prime"] or main_line).product_id
            # Try to post TDS against a dedicated receivable account so ledger is clear.
            ICP = self.env["ir.config_parameter"].sudo()
            tds_account_id = int(ICP.get_param("gear_on_rent.tds_receivable_account_id", 0) or 0)
            tds_account = (
                self.env["account.account"].browse(tds_account_id)
                if tds_account_id
                else self.env["account.account"]
            )
            if not tds_account or not tds_account.exists():
                tds_account = (
                    self.env["account.account"]
                    .search(
                        [
                            ("code", "=like", "1312%"),
                            ("company_ids", "in", order.company_id.id),
                        ],
                        limit=1,
                    )
                )
            # Resolve account for the line: prefer configured TDS account; otherwise pick a liability/payable account.
            account_id = False
            if tds_account and tds_account.exists():
                account_id = tds_account.id
            else:
                liability_account = (
                    self.env["account.account"]
                    .search(
                        [
                            ("internal_group", "in", ["liability", "asset"]),
                            ("company_ids", "in", order.company_id.id),
                        ],
                        limit=1,
                    )
                )
                account_id = liability_account.id if liability_account else False
            line_commands.append(
                (
                    0,
                    0,
                    {
                        # Clear, ledger-friendly label for the withholding line.
                        "name": _("TDS 194C Withholding @ 2%"),
                        "product_id": False,  # treat as ledger line, not a product
                        "quantity": 1.0,
                        "price_unit": -tds_amount,
                        "account_id": account_id,
                        "tax_ids": False,
                        "analytic_distribution": False,
                    },
                )
            )

        invoice_vals["invoice_line_ids"] = line_commands

        invoice = self.env["account.move"].create(invoice_vals)
        message = _(
            "Prime output: %(prime).2f m³, optimized standby: %(standby).2f m³, "
            "NGT billed: %(ngt_qty).2f m³, NGT hours: %(ngt_hours).2f h, LOTO chargeable: %(loto).2f h."
        ) % {
            "prime": prime_output,
            "standby": standby_billable_qty,
            "ngt_qty": downtime_qty,
            "ngt_hours": ngt_hours,
            "loto": waveoff_chargeable,
        }
        invoice.message_post(body=message)
        link = '<a href="#" data-oe-model="account.move" data-oe-id="%(id)s">%(name)s</a>' % {
            "id": invoice.id,
            "name": invoice.display_name,
        }
        monthly.message_post(
            body=_("Invoice %(link)s created for this Monthly Work Order.") % {"link": link},
            subtype_xmlid="mail.mt_note",
        )

        action = {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "context": {"default_move_type": "out_invoice"},
        }
        return action
