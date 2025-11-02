from calendar import monthrange

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
    invoice_date = fields.Date(
        string="Invoice Date",
        required=True,
        default=lambda self: fields.Date.context_today(self),
    )
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

    def action_prepare_invoice(self):
        self.ensure_one()
        monthly = self.monthly_order_id
        order = monthly.so_id
        if not order:
            raise UserError(_("Please select a monthly work order linked to a sale order."))
        if order.x_billing_category != "rmc":
            raise UserError(_("This wizard can only prepare invoices for RMC contracts."))
        product = order._gear_get_primary_product()
        if not product:
            raise UserError(_("The sale order must have a billable product line to derive the rate."))

        main_line = order.order_line.filtered(lambda l: not l.display_type)[:1]
        if not main_line:
            raise UserError(_("The sale order must have at least one billable line."))

        taxes = getattr(main_line, "tax_id", False) or getattr(main_line, "taxes_id", self.env["account.tax"])
        analytic_distribution = getattr(main_line, "analytic_distribution", {}) or {}
        analytic_distribution = {
            str(key): value for key, value in analytic_distribution.items() if value
        }

        if monthly.date_start:
            month_start = monthly.date_start.replace(day=1)
        else:
            today = fields.Date.context_today(self)
            month_start = today.replace(day=1)
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)

        month_orders = self.env["gear.rmc.monthly.order"].search(
            [
                ("so_id", "=", order.id),
                ("date_start", ">=", month_start),
                ("date_start", "<=", month_end),
            ]
        )
        if not month_orders:
            month_orders = monthly
        else:
            month_orders |= monthly

        summary = month_orders._gear_compute_billing_summary()
        cooling = summary["cooling"]
        normal = summary["normal"]
        prime_output = cooling["prime_output_qty"] + normal["prime_output_qty"]
        standby_qty = normal["standby_qty"]
        downtime_qty = cooling["ngt_m3"] + normal["ngt_m3"]
        adjusted_target_qty = cooling["adjusted_target_qty"] + normal["adjusted_target_qty"]
        target_qty = cooling["target_qty"] + normal["target_qty"]
        ngt_hours = cooling["ngt_hours"] + normal["ngt_hours"]
        waveoff_applied = cooling["waveoff_applied_hours"] + normal["waveoff_applied_hours"]
        waveoff_chargeable = cooling["waveoff_chargeable_hours"] + normal["waveoff_chargeable_hours"]

        if prime_output <= 0 and standby_qty <= 0 and downtime_qty <= 0:
            raise UserError(_("Nothing to invoice: no prime output, standby, or NGT quantities computed."))

        invoice_vals = {
            "move_type": "out_invoice",
            "partner_id": order.partner_invoice_id.id or order.partner_id.id,
            "currency_id": order.currency_id.id,
            "invoice_origin": order.name,
            "invoice_date": self.invoice_date,
            "x_billing_category": "rmc",
            "gear_monthly_order_id": monthly.id,
            "gear_target_qty": target_qty,
            "gear_adjusted_target_qty": adjusted_target_qty,
            "gear_prime_output_qty": prime_output,
            "gear_optimized_standby_qty": standby_qty,
            "gear_ngt_hours": ngt_hours,
            "gear_loto_chargeable_hours": waveoff_chargeable,
            "gear_waveoff_applied_hours": waveoff_applied,
            "gear_waveoff_allowance_hours": order.x_loto_waveoff_hours,
        }

        period_start_label = fields.Date.to_string(month_start)
        period_end_label = fields.Date.to_string(month_end)

        line_commands = []
        if prime_output > 0:
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _("Prime Output for %s - %s") % (period_start_label, period_end_label),
                        "product_id": product.id,
                        "quantity": prime_output,
                        "price_unit": main_line.price_unit,
                        "tax_ids": [(6, 0, taxes.ids)] if taxes else False,
                        "analytic_distribution": analytic_distribution or False,
                        "sale_line_ids": [(6, 0, main_line.ids)],
                    },
                )
            )

        if standby_qty > 0:
            standby_rate = max(main_line.price_unit - self.x_unproduced_delta, 0.0)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _("MGQ Shortfall Adjustment (%s - %s)") % (period_start_label, period_end_label),
                        "product_id": product.id,
                        "quantity": standby_qty,
                        "price_unit": standby_rate,
                        "tax_ids": [(6, 0, taxes.ids)] if taxes else False,
                        "analytic_distribution": analytic_distribution or False,
                        "sale_line_ids": [(6, 0, main_line.ids)],
                    },
                )
            )

        if downtime_qty > 0:
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "name": _("NGT Relief (%s - %s)") % (period_start_label, period_end_label),
                        "product_id": product.id,
                        "quantity": downtime_qty,
                        "price_unit": 0.0,
                        "tax_ids": [(6, 0, taxes.ids)] if taxes else False,
                        "analytic_distribution": analytic_distribution or False,
                        "sale_line_ids": [(6, 0, main_line.ids)],
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
            "standby": standby_qty,
            "ngt_qty": downtime_qty,
            "ngt_hours": ngt_hours,
            "loto": waveoff_chargeable,
        }
        invoice.message_post(body=message)

        action = {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": invoice.id,
            "view_mode": "form",
            "context": {"default_move_type": "out_invoice"},
        }
        return action
