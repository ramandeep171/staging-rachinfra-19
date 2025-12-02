from collections import defaultdict
from calendar import monthrange
from datetime import datetime, time, timedelta
# Branding Patch Stage-5 applied for SP Nexgen Automind Pvt Ltd — Tech Paras

try:  # pragma: no cover - keep optional deps optional in CI
    from dateutil.relativedelta import relativedelta
except ModuleNotFoundError:  # pragma: no cover
    from odoo_shims.relativedelta import relativedelta

try:  # pragma: no cover - fallback shim for lightweight runtimes
    import pytz
except ModuleNotFoundError:  # pragma: no cover
    from odoo_shims import pytz

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv.expression import AND, OR


_logger = logging.getLogger(__name__)
# © SP Nexgen Automind Pvt Ltd · www.smarterpeak.com


class SaleOrder(models.Model):
    """Extends sale orders with Gear On Rent contract settings."""

    _inherit = "sale.order"

    x_billing_category = fields.Selection(
        selection=[
            ("rental", "Rental"),
            ("rmc", "RMC"),
            ("plant", "Plant"),
        ],
        string="Billing Category",
        default="rental",
        tracking=True,
    )
    x_workcenter_id = fields.Many2one(
        comodel_name="mrp.workcenter",
        string="Primary Work Center",
        help="Work center that will receive IDS telemetry for this contract.",
        tracking=True,
    )
    x_inventory_mode = fields.Selection(
        selection=[
            ("without_inventory", "Without Inventory"),
            ("with_inventory", "With Inventory"),
        ],
        string="Inventory Mode",
        default="without_inventory",
        tracking=True,
        help="Choose whether this contract consumes real inventory or runs via the silent warehouse.",
    )
    x_real_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Real Warehouse",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="Warehouse to route production when Inventory Mode is set to With Inventory.",
    )
    mgq_monthly = fields.Float(
        string="MGQ (Monthly)",
        digits=(16, 2),
        compute="_compute_mgq_monthly",
        inverse="_inverse_mgq_monthly",
        store=True,
        tracking=True,
        help="Variable-based monthly MGQ value used for billing calculations.",
    )
    x_monthly_mgq = fields.Float(
        string="Monthly MGQ",
        digits=(16, 2),
        tracking=True,
    )
    wastage_allowed_percent = fields.Float(
        string="Allowed Wastage (%)",
        digits=(16, 4),
        tracking=True,
        help="Tolerance percent for scrap/wastage that will cascade to monthly and daily orders.",
    )
    wastage_penalty_rate = fields.Monetary(
        string="Wastage Penalty Rate",
        currency_field="currency_id",
        tracking=True,
        help="Rate used to value over-wastage quantities during month-end debit note creation.",
    )
    prime_rate = fields.Float(
        string="Prime Rate",
        digits=(16, 2),
        tracking=True,
        help="Variable billing rate for prime production (per m³).",
    )
    optimize_rate = fields.Float(
        string="Optimize Standby Rate",
        digits=(16, 2),
        tracking=True,
        help="Variable billing rate for optimize standby quantities.",
    )
    ngt_rate = fields.Float(
        string="NGT Rate",
        digits=(16, 2),
        tracking=True,
        help="Variable billing rate used to convert NGT hours to m³ relief.",
    )
    excess_rate = fields.Float(
        string="Excess Production Rate",
        digits=(16, 2),
        tracking=True,
        help="Variable billing rate for excess production beyond MGQ and bank pulls.",
    )
    x_loto_waveoff_hours = fields.Float(
        string="Monthly LOTO Wave-Off Allowance",
        digits=(16, 2),
        default=48.0,
        tracking=True,
    )
    ngt_hourly_prorata_factor = fields.Float(
        string="NGT Hourly Prorata Factor",
        digits=(16, 4),
        tracking=True,
        help="Conversion factor to derive NGT m³ relief from approved hours.",
    )
    bank_pull_limit = fields.Float(
        string="Bank Pull Limit",
        digits=(16, 2),
        tracking=True,
        help="Maximum quantity that can be pulled from the optimize bank per billing cycle.",
    )
    standard_loading_minutes = fields.Float(
        string="Standard Loading (min)",
        digits=(16, 2),
        tracking=True,
        help="Expected loading time per trip; overruns will trigger diesel charges.",
    )
    diesel_burn_rate_per_hour = fields.Float(
        string="Diesel Burn Rate (L/hr)",
        digits=(16, 2),
        tracking=True,
        help="Diesel consumption rate used to value loading overruns.",
    )
    diesel_rate_per_litre = fields.Monetary(
        string="Diesel Rate per Litre",
        currency_field="currency_id",
        tracking=True,
        help="Rate charged to the customer for diesel overrun consumption.",
    )
    x_contract_start = fields.Date(string="Contract Start", tracking=True)
    x_contract_end = fields.Date(string="Contract End", tracking=True)
    x_cooling_period_months = fields.Integer(
        string="Cooling Period (Months)",
        default=3,
        help="Number of months to keep returned assets on hold before the contract can restart.",
        tracking=True,
    )
    cooling_months = fields.Integer(
        string="Cooling Months",
        compute="_compute_cooling_months",
        inverse="_inverse_cooling_months",
        store=True,
        tracking=True,
        help="Variable-based cooling period duration for MGQ billing logic.",
    )
    x_cooling_end = fields.Datetime(
        string="Cooling Ends",
        compute="_compute_x_cooling_end",
        store=True,
        help="Last day of the cooling period window.",
    )
    gear_ngt_relief_days = fields.Float(
        string="NGT Relief (Days)",
        digits=(16, 2),
        default=0.0,
        tracking=True,
    )
    gear_loto_relief_days = fields.Float(
        string="LOTO Relief (Days)",
        digits=(16, 2),
        default=0.0,
        tracking=True,
    )
    gear_materials_shortage_note = fields.Text(string="Materials Shortage Notes")
    gear_manpower_note = fields.Text(string="Manpower Notes")
    gear_asset_note = fields.Text(string="Asset Notes")
    gear_service_id = fields.Many2one(
        comodel_name="gear.service.master",
        string="Service Category",
        tracking=True,
    )
    gear_service_type = fields.Selection(
        selection=[("dedicated", "Dedicated Plant"), ("turnkey", "Full Factory (Turnkey)")],
        string="Service Type",
        tracking=True,
        help="Engagement model for the batching plant (dedicated site setup or full turnkey factory).",
    )
    gear_capacity_id = fields.Many2one(
        comodel_name="gear.plant.capacity.master",
        string="Plant Capacity",
        tracking=True,
    )
    gear_mgq_rate_id = fields.Many2one(
        comodel_name="gear.mgq.rate.master",
        string="MGQ Rate Tier",
        tracking=True,
        domain="[('service_id', '=', gear_service_id), ('capacity_id', '=', gear_capacity_id)]",
    )
    gear_design_mix_id = fields.Many2one(
        comodel_name="gear.design.mix.master",
        string="Design Mix",
        tracking=True,
        help="Grade mix used for inventory quotations (M10–M30).",
    )
    gear_material_area_id = fields.Many2one(
        comodel_name="gear.material.area.master",
        string="Material Area",
        tracking=True,
        help="Area-wise rate card to value cement/aggregate/admixture inputs.",
    )
    gear_cement_area_id = fields.Many2one(
        comodel_name="gear.material.area.master",
        string="Cement Source Area",
        tracking=True,
        help="Area source/rate card applied to cement inputs for the quotation.",
    )
    gear_agg_10mm_area_id = fields.Many2one(
        comodel_name="gear.material.area.master",
        string="10mm Aggregate Source Area",
        tracking=True,
        help="Area source/rate card applied to 10mm aggregate inputs for the quotation.",
    )
    gear_agg_20mm_area_id = fields.Many2one(
        comodel_name="gear.material.area.master",
        string="20mm Aggregate Source Area",
        tracking=True,
        help="Area source/rate card applied to 20mm aggregate inputs for the quotation.",
    )
    gear_admixture_area_id = fields.Many2one(
        comodel_name="gear.material.area.master",
        string="Admixture Source Area",
        tracking=True,
        help="Area source/rate card applied to admixture inputs for the quotation.",
    )
    gear_optional_service_ids = fields.Many2many(
        comodel_name="gear.optional.service.master",
        string="Optional Services",
        tracking=True,
        help="Optional surcharges such as transport, pump, manpower, diesel, or JCB.",
    )
    gear_transport_opt_in = fields.Boolean(string="Transport Required", tracking=True)
    gear_pumping_opt_in = fields.Boolean(string="Pumping Required", tracking=True)
    gear_manpower_opt_in = fields.Boolean(string="Manpower Required", tracking=True)
    gear_diesel_opt_in = fields.Boolean(string="Diesel Required", tracking=True)
    gear_jcb_opt_in = fields.Boolean(string="JCB Required", tracking=True)
    gear_dead_cost_amount = fields.Monetary(
        string="Dead Cost Amount",
        currency_field="currency_id",
        tracking=True,
        help="Capital expenditure to amortize for turnkey engagements.",
    )
    gear_dead_cost_months = fields.Integer(
        string="Dead Cost Term (Months)",
        tracking=True,
        help="Amortization window (typically 36–120 months) for turnkey plants.",
    )
    gear_project_duration_years = fields.Selection(
        selection=[("3", "3 Years"), ("6", "6 Years"), ("10", "10 Years")],
        string="Project Duration (Years)",
        tracking=True,
        help="High-level contract duration options for turnkey or long-term rentals.",
    )
    gear_project_duration_months = fields.Integer(
        string="Project Duration (Months)",
        tracking=True,
    )
    gear_civil_scope = fields.Selection(
        selection=[("vendor", "Vendor Scope"), ("customer", "Customer Scope")],
        string="Civil Scope",
        tracking=True,
    )
    gear_expected_production_qty = fields.Float(
        string="Expected Production (m³)",
        digits=(16, 2),
        tracking=True,
        help="Expected production volume to assess optimize (shortfall) quantities against MGQ.",
    )
    gear_prime_rate_final = fields.Float(
        string="Prime Rate (Final)",
        digits=(16, 2),
        tracking=True,
        help="Prime rate inclusive of optional services and dead-cost amortization.",
    )
    gear_optimize_rate_final = fields.Float(
        string="Optimize Rate (Final)",
        digits=(16, 2),
        tracking=True,
        help="Optimize/shortfall rate inclusive of optional services and dead-cost amortization.",
    )
    gear_after_mgq_rate_final = fields.Float(
        string="After MGQ Rate (Final)",
        digits=(16, 2),
        tracking=True,
        help="After-MGQ (excess/discount) rate inclusive of optional services and dead-cost amortization.",
    )
    gear_base_plant_rate = fields.Float(
        string="Base Plant Rate", digits=(16, 2), tracking=True, help="Base plant rate per CUM used for inventory mode."
    )
    gear_material_cost_total = fields.Monetary(
        string="Material Cost (Per CUM)",
        currency_field="currency_id",
        tracking=True,
        help="Material cost per CUM based on the selected design mix and area pricing.",
    )
    gear_optional_services_cost = fields.Monetary(
        string="Optional Services (Per CUM)",
        currency_field="currency_id",
        tracking=True,
        help="Aggregated optional service surcharge per CUM.",
    )
    gear_dead_cost_per_cum = fields.Monetary(
        string="Dead Cost (Per CUM)",
        currency_field="currency_id",
        tracking=True,
        help="Dead-cost amortization per CUM for turnkey vendor-scope engagements.",
    )
    gear_total_per_cum_rate = fields.Monetary(
        string="Total Rate (Per CUM)",
        currency_field="currency_id",
        tracking=True,
        help="Total per-CUM rate for inventory mode (base + material + optional + dead-cost).",
    )
    gear_transport_per_cum = fields.Monetary(
        string="Transport (Per CUM)", currency_field="currency_id", tracking=True
    )
    gear_pump_per_cum = fields.Monetary(string="Pump (Per CUM)", currency_field="currency_id", tracking=True)
    gear_manpower_per_cum = fields.Monetary(
        string="Manpower (Per CUM)", currency_field="currency_id", tracking=True
    )
    gear_diesel_per_cum = fields.Monetary(string="Diesel (Per CUM)", currency_field="currency_id", tracking=True)
    gear_jcb_monthly = fields.Monetary(string="JCB (Monthly)", currency_field="currency_id", tracking=True)
    gear_quote_state = fields.Selection(
        selection=[("draft", "Draft"), ("sent", "Sent"), ("accepted", "Accepted")],
        string="Batching Quote State",
        default="draft",
        tracking=True,
        help="Tracks acceptance for batching-plant quotations without altering the base sale order state machine.",
    )
    gear_generated_so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Generated Sales Order",
        help="Sales Order created when the batching-plant quotation was accepted.",
        tracking=True,
    )
    gear_quote_source_id = fields.Many2one(
        comodel_name="sale.order",
        string="Source Batching Quote",
        help="Original batching-plant quotation that produced this Sales Order.",
        tracking=True,
    )

    @api.depends("x_monthly_mgq")
    def _compute_mgq_monthly(self):
        for order in self:
            order.mgq_monthly = order.x_monthly_mgq

    def _inverse_mgq_monthly(self):
        for order in self:
            order.x_monthly_mgq = order.mgq_monthly

    @api.depends("x_cooling_period_months")
    def _compute_cooling_months(self):
        for order in self:
            order.cooling_months = order.x_cooling_period_months

    def _inverse_cooling_months(self):
        for order in self:
            order.x_cooling_period_months = order.cooling_months

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._gear_sync_billing_category()
        return orders

    def write(self, vals):
        audit_fields = {
            "gear_optional_service_ids",
            "gear_transport_opt_in",
            "gear_pumping_opt_in",
            "gear_manpower_opt_in",
            "gear_diesel_opt_in",
            "gear_jcb_opt_in",
            "gear_material_area_id",
            "gear_cement_area_id",
            "gear_agg_10mm_area_id",
            "gear_agg_20mm_area_id",
            "gear_admixture_area_id",
            "gear_dead_cost_amount",
            "gear_dead_cost_months",
            "gear_design_mix_id",
        }
        should_audit = bool(set(vals).intersection(audit_fields))

        previous_state = {}
        if should_audit:
            for order in self:
                previous_state[order.id] = {
                    "optional_services": set(order.gear_optional_service_ids.ids),
                    "optional_names": order.gear_optional_service_ids.mapped("name"),
                    "transport": order.gear_transport_opt_in,
                    "pumping": order.gear_pumping_opt_in,
                    "manpower": order.gear_manpower_opt_in,
                    "diesel": order.gear_diesel_opt_in,
                    "jcb": order.gear_jcb_opt_in,
                    "material_area": order.gear_material_area_id,
                    "cement_area": order.gear_cement_area_id,
                    "agg10_area": order.gear_agg_10mm_area_id,
                    "agg20_area": order.gear_agg_20mm_area_id,
                    "admixture_area": order.gear_admixture_area_id,
                    "dead_cost": order.gear_dead_cost_amount,
                    "dead_cost_months": order.gear_dead_cost_months,
                    "design_mix": order.gear_design_mix_id,
                }

        if "x_inventory_mode" in vals or "x_real_warehouse_id" in vals:
            self._gear_validate_inventory_mode_change(vals.get("x_inventory_mode"))
        res = super().write(vals)

        if should_audit:
            for order in self:
                prev = previous_state.get(order.id)
                if not prev:
                    continue

                def _name(record):
                    return record.display_name if record else _("None")

                messages = []

                current_services = set(order.gear_optional_service_ids.ids)
                if prev["optional_services"] != current_services:
                    removed = prev["optional_services"] - current_services
                    added = current_services - prev["optional_services"]
                    if added:
                        names = order.gear_optional_service_ids.filtered(lambda s: s.id in added).mapped("name")
                        messages.append(_("Optional services added: %s") % ", ".join(names))
                    if removed:
                        names = [s.name for s in self.env["gear.optional.service.master"].browse(removed)]
                        messages.append(_("Optional services removed: %s") % ", ".join(names))

                toggle_fields = [
                    ("gear_transport_opt_in", "transport", _("Transport requirement updated: %s")),
                    ("gear_pumping_opt_in", "pumping", _("Pumping requirement updated: %s")),
                    ("gear_manpower_opt_in", "manpower", _("Manpower requirement updated: %s")),
                    ("gear_diesel_opt_in", "diesel", _("Diesel requirement updated: %s")),
                    ("gear_jcb_opt_in", "jcb", _("JCB requirement updated: %s")),
                ]
                for field, key, template in toggle_fields:
                    if field in vals and bool(prev[key]) != bool(order[field]):
                        messages.append(template % (order[field] and _("Enabled") or _("Disabled")))

                area_fields = [
                    ("gear_material_area_id", "material_area", _("Material area changed from %s to %s")),
                    ("gear_cement_area_id", "cement_area", _("Cement source changed from %s to %s")),
                    ("gear_agg_10mm_area_id", "agg10_area", _("10mm aggregate source changed from %s to %s")),
                    ("gear_agg_20mm_area_id", "agg20_area", _("20mm aggregate source changed from %s to %s")),
                    ("gear_admixture_area_id", "admixture_area", _("Admixture source changed from %s to %s")),
                ]
                for field, key, template in area_fields:
                    if field in vals and prev[key].id != order[field].id:
                        messages.append(template % (_name(prev[key]), _name(order[field])))

                if "gear_dead_cost_amount" in vals and (prev["dead_cost"] or 0.0) != (order.gear_dead_cost_amount or 0.0):
                    messages.append(
                        _("Dead-cost amount changed from %(old)s to %(new)s")
                        % {"old": prev["dead_cost"] or 0.0, "new": order.gear_dead_cost_amount or 0.0}
                    )
                if "gear_dead_cost_months" in vals and (prev["dead_cost_months"] or 0) != (order.gear_dead_cost_months or 0):
                    messages.append(
                        _("Dead-cost term changed from %(old)d months to %(new)d months")
                        % {
                            "old": int(prev["dead_cost_months"] or 0),
                            "new": int(order.gear_dead_cost_months or 0),
                        }
                    )

                if "gear_design_mix_id" in vals and prev["design_mix"].id != order.gear_design_mix_id.id:
                    messages.append(
                        _("Grade mix changed from %s to %s") % (_name(prev["design_mix"]), _name(order.gear_design_mix_id))
                    )

                if messages:
                    order.message_post(body="<br/>".join(messages), subtype_xmlid="mail.mt_note")

        if "order_line" in vals:
            self._gear_sync_billing_category()
        return res

    def _gear_validate_inventory_mode_change(self, new_mode=None):
        for order in self:
            target_mode = new_mode or order.x_inventory_mode
            if order.state != "draft":
                has_monthly_orders = bool(
                    self.env["gear.rmc.monthly.order"].search_count([("so_id", "=", order.id)])
                )
                has_productions = bool(
                    self.env["mrp.production"].search_count([("x_sale_order_id", "=", order.id)])
                )
                has_dockets = bool(
                    self.env["gear.rmc.docket"].search_count([("so_id", "=", order.id)])
                )
                if has_monthly_orders or has_productions or has_dockets:
                    raise ValidationError(
                        _(
                            "Inventory Mode cannot be changed once monthly orders, manufacturing orders, or dockets exist for this contract."
                        )
                    )
            if target_mode == "with_inventory" and not (order.x_real_warehouse_id or new_mode):
                # Will be enforced by constraints, but surface early in onchange/write flows.
                _logger.debug("Inventory mode requires a real warehouse on SO %s", order.display_name)

    def action_confirm(self):
        res = super().action_confirm()
        rmc_orders = self.filtered(lambda o: o.x_billing_category == "rmc")
        if rmc_orders:
            rmc_orders._gear_sync_production_defaults()
            rmc_orders.gear_generate_monthly_orders(limit=1)
        return res

    @api.onchange("order_line")
    def _onchange_order_line_update_category(self):
        self._gear_sync_billing_category()

    def _gear_get_primary_product(self):
        self.ensure_one()
        line = self.order_line.filtered(
            lambda l: not l.display_type and l.product_id and l.product_id.gear_is_production
        )[:1]
        if not line:
            line = self.order_line.filtered(lambda l: not l.display_type)[:1]
        return line.product_id

    @api.constrains("x_inventory_mode", "x_real_warehouse_id")
    def _check_inventory_mode_real_warehouse(self):
        silent_wh_model = self.env["gear.rmc.monthly.order"]
        for order in self:
            silent_wh = silent_wh_model._gear_get_silent_warehouse(order.company_id)
            if order.x_inventory_mode == "with_inventory" and not order.x_real_warehouse_id:
                raise ValidationError(_("Please choose a real warehouse when using Inventory Mode: With Inventory."))
            # if silent_wh and order.x_real_warehouse_id and order.x_real_warehouse_id == silent_wh:
            #     raise ValidationError(_("The silent warehouse cannot be selected as the real warehouse."))

    def _gear_get_timezone(self):
        self.ensure_one()
        tz_name = self.env.context.get("tz") or self.env.user.tz or "UTC"
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.utc

    def _gear_localize_day(self, day, is_end=False, tz=None):
        tz = tz or self._gear_get_timezone()
        boundary = time(23, 59, 59) if is_end else time.min
        return tz.localize(datetime.combine(day, boundary))

    def _gear_db_to_local(self, dt, tz=None):
        tz = tz or self._gear_get_timezone()
        if not dt:
            return False
        if dt.tzinfo:
            return dt.astimezone(tz)
        return pytz.utc.localize(dt).astimezone(tz)

    @staticmethod
    def _gear_local_to_utc(dt):
        if not dt:
            return False
        return dt.astimezone(pytz.utc).replace(tzinfo=None)

    def gear_generate_monthly_orders(self, date_start=None, date_end=None, limit=None):
        """Ensure monthly orders and daily MOs exist for the contract window."""
        MonthlyOrder = self.env["gear.rmc.monthly.order"]
        try:
            limit = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            limit = None
        if limit is not None and limit <= 0:
            limit = None

        date_start = fields.Date.to_date(date_start) if date_start else None
        date_end = fields.Date.to_date(date_end) if date_end else None

        for order in self.filtered(lambda s: s.x_billing_category == "rmc"):
            if not order.x_contract_start or not order.x_contract_end:
                continue
            product = order._gear_get_primary_product()
            if not product:
                continue
            if not order.x_monthly_mgq or order.x_monthly_mgq <= 0:
                order.message_post(
                    body=_("Monthly MGQ is required to generate daily orders. Please set a positive value."),
                    subtype_xmlid="mail.mt_note",
                )
                continue
            windows = order._gear_iter_monthly_windows(order.x_contract_start, order.x_contract_end)
            if date_start or date_end:
                filtered_windows = [
                    window
                    for window in windows
                    if not (date_end and window["date_start"] > date_end)
                    and not (date_start and window["date_end"] < date_start)
                ]
            else:
                filtered_windows = list(windows)

            if not filtered_windows:
                continue
            if limit is not None:
                filtered_windows = filtered_windows[:limit]
            managed_orders = self.env["gear.rmc.monthly.order"]
            for window in filtered_windows:
                monthly = MonthlyOrder.search(
                    [
                        ("so_id", "=", order.id),
                        ("date_start", "=", window["date_start"]),
                    ],
                    limit=1,
                )
                mgq_total = order.x_monthly_mgq or 0.0
                month_hours = window.get("month_hours") or 0.0
                window_hours = window.get("window_hours") or 0.0
                if month_hours:
                    ratio = window_hours / month_hours
                else:
                    span_days = window["span_days"]
                    month_days = window["month_days"]
                    ratio = span_days / month_days if month_days else 1.0
                snapshot = mgq_total * ratio if mgq_total else 0.0
                vals = {
                    "so_id": order.id,
                    "product_id": product.id,
                    "workcenter_id": order.x_workcenter_id.id or product.gear_workcenter_id.id,
                    "date_start": window["date_start"],
                    "date_end": window["date_end"],
                    "x_window_start": window["window_start"],
                    "x_window_end": window["window_end"],
                    "x_is_cooling_period": window["is_cooling"],
                    "x_monthly_mgq_snapshot": snapshot,
                    "x_inventory_mode": order.x_inventory_mode,
                    "x_real_warehouse_id": order.x_real_warehouse_id.id,
                    "standard_loading_minutes": order.standard_loading_minutes,
                    "diesel_burn_rate_per_hour": order.diesel_burn_rate_per_hour,
                    "diesel_rate_per_litre": order.diesel_rate_per_litre,
                    "wastage_allowed_percent": order.wastage_allowed_percent,
                    "wastage_penalty_rate": order.wastage_penalty_rate,
                }
                if monthly:
                    monthly.write(vals)
                else:
                    monthly = MonthlyOrder.create(vals)
                managed_orders |= monthly
            all_orders = MonthlyOrder.search([("so_id", "=", order.id)])
            all_orders._gear_reassign_productions_to_windows()
            today = fields.Date.context_today(order)
            current_orders = managed_orders.filtered(
                lambda m: m.state != "done"
                and m.date_start
                and m.date_end
                and m.date_start <= today <= m.date_end
            )
            if not current_orders:
                past_orders = managed_orders.filtered(
                    lambda m: m.state != "done"
                    and m.date_end
                    and m.date_end < today
                )
                current_orders = past_orders.sorted(key=lambda m: m.date_end or fields.Date.today(), reverse=True)[:1]
            for monthly in current_orders:
                has_locked_mo = monthly.production_ids.filtered(lambda p: p.state in ("done", "cancel"))
                has_locked_wo = monthly.production_ids.mapped("workorder_ids").filtered(lambda wo: wo.state in ("done", "cancel"))
                if monthly.state != "done" and not has_locked_mo and not has_locked_wo:
                    monthly.action_schedule_orders(until_date=today)

    def gear_generate_next_monthly_order(self, horizon_days=1):
        """Create the next missing monthly order when the window is imminent or previous is done."""
        MonthlyOrder = self.env["gear.rmc.monthly.order"]
        today = fields.Date.context_today(self)
        try:
            horizon_days = int(horizon_days)
        except (TypeError, ValueError):
            horizon_days = 0
        if horizon_days < 0:
            horizon_days = 0
        horizon_date = today + timedelta(days=horizon_days)

        for order in self.filtered(lambda s: s.x_billing_category == "rmc"):
            if not order.x_contract_start or not order.x_contract_end:
                continue

            windows = order._gear_iter_monthly_windows(order.x_contract_start, order.x_contract_end)
            if not windows:
                continue

            existing_orders = MonthlyOrder.search([("so_id", "=", order.id)])
            existing_by_start = {monthly.date_start: monthly for monthly in existing_orders}

            for idx, window in enumerate(windows):
                start_date = window["date_start"]
                if start_date in existing_by_start:
                    continue

                prev_window = windows[idx - 1] if idx > 0 else None
                prev_order = existing_by_start.get(prev_window["date_start"]) if prev_window else None

                should_create = False
                if prev_order and prev_order.state == "done":
                    should_create = True
                if start_date and start_date <= today:
                    should_create = True
                if start_date and start_date <= horizon_date:
                    should_create = True

                if should_create:
                    order.gear_generate_monthly_orders(
                        date_start=start_date,
                        date_end=window["date_end"],
                        limit=1,
                    )
                    new_monthly = MonthlyOrder.search(
                        [
                            ("so_id", "=", order.id),
                            ("date_start", "=", start_date),
                        ],
                        limit=1,
                    )
                    if new_monthly:
                        existing_by_start[start_date] = new_monthly

    @api.model
    def _cron_generate_next_monthly_orders(self):
        """Nightly job to ensure the upcoming monthly WMO exists."""
        domain = [
            ("state", "in", ["sale", "done"]),
            ("x_billing_category", "=", "rmc"),
            ("x_contract_start", "!=", False),
            ("x_contract_end", "!=", False),
        ]
        orders = self.search(domain)
        if orders:
            orders.gear_generate_next_monthly_order()

    def _gear_iter_monthly_windows(self, start_date, end_date):
        """Return dictionaries describing each monthly window, splitting on cooling transitions."""
        self.ensure_one()
        if not start_date or not end_date:
            return []

        contract_start_dt = self._gear_get_contract_start_datetime()
        cooling_end_dt = self.x_cooling_end
        tz = self._gear_get_timezone()
        contract_start_local = self._gear_db_to_local(contract_start_dt, tz)
        cooling_end_local = self._gear_db_to_local(cooling_end_dt, tz)
        current = start_date.replace(day=1)
        limit = end_date
        windows = []

        def compute_hours(start_dt, end_dt):
            if not start_dt or not end_dt or end_dt < start_dt:
                return 0.0
            delta_seconds = (end_dt - start_dt).total_seconds() + 1.0
            return max(delta_seconds / 3600.0, 0.0)

        while current <= limit:
            month_days = monthrange(current.year, current.month)[1]
            month_start = current
            month_end = current.replace(day=month_days)
            window_start = month_start if month_start >= start_date else start_date
            window_end = month_end if month_end <= end_date else end_date
            if window_start > window_end:
                current = (current + relativedelta(months=1)).replace(day=1)
                continue

            month_start_local = self._gear_localize_day(month_start, tz=tz)
            month_end_local = self._gear_localize_day(month_end, is_end=True, tz=tz)
            month_hours = compute_hours(month_start_local, month_end_local)

            midnight_start_local = self._gear_localize_day(window_start, tz=tz)
            if contract_start_local and contract_start_local.date() == window_start:
                start_local = min(midnight_start_local, contract_start_local)
            else:
                start_local = midnight_start_local
            end_local = self._gear_localize_day(window_end, is_end=True, tz=tz)
            default_span_days = (window_end - window_start).days + 1

            if cooling_end_local and start_local <= cooling_end_local <= end_local:
                first_end_local = min(cooling_end_local, end_local)
                first_end_date = min(window_end, first_end_local.date())
                if first_end_date >= window_start:
                    first_span_days = (first_end_date - window_start).days + 1
                    windows.append(
                        {
                            "date_start": window_start,
                            "date_end": first_end_date,
                            "window_start": self._gear_local_to_utc(start_local),
                            "window_end": self._gear_local_to_utc(first_end_local),
                            "is_cooling": True,
                            "month_days": month_days,
                            "span_days": first_span_days,
                            "month_hours": month_hours,
                            "window_hours": compute_hours(start_local, first_end_local),
                        }
                    )
                after_cooling_date = first_end_date + timedelta(days=1)
                if after_cooling_date <= window_end:
                    second_start_local = max(
                        cooling_end_local + timedelta(seconds=1),
                        self._gear_localize_day(after_cooling_date, tz=tz),
                    )
                    second_span_days = (window_end - after_cooling_date).days + 1
                    if second_span_days > 0:
                        windows.append(
                            {
                                "date_start": after_cooling_date,
                                "date_end": window_end,
                                "window_start": self._gear_local_to_utc(second_start_local),
                                "window_end": self._gear_local_to_utc(end_local),
                                "is_cooling": False,
                                "month_days": month_days,
                                "span_days": second_span_days,
                                "month_hours": month_hours,
                                "window_hours": compute_hours(second_start_local, end_local),
                            }
                        )
            else:
                is_cooling = bool(cooling_end_local and end_local <= cooling_end_local)
                windows.append(
                    {
                        "date_start": window_start,
                        "date_end": window_end,
                        "window_start": self._gear_local_to_utc(start_local),
                        "window_end": self._gear_local_to_utc(end_local),
                        "is_cooling": is_cooling,
                        "month_days": month_days,
                        "span_days": default_span_days,
                        "month_hours": month_hours,
                        "window_hours": compute_hours(start_local, end_local),
                    }
                )

            current = (current + relativedelta(months=1)).replace(day=1)

        return windows

    def _gear_has_production_products(self):
        self.ensure_one()
        return any(
            line.product_id.gear_is_production
            for line in self.order_line
            if not line.display_type and line.product_id
        )

    def _gear_sync_billing_category(self):
        for order in self:
            has_production = order._gear_has_production_products()
            if has_production:
                if order.x_billing_category != "rmc":
                    order.x_billing_category = "rmc"
                order._gear_sync_production_defaults()
            elif order.x_billing_category == "rmc":
                order.x_billing_category = "rental"

    def _gear_sync_production_defaults(self):
        for order in self.filtered(lambda o: o.x_billing_category == "rmc"):
            production_lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id and l.product_id.gear_is_production
            )
            if not production_lines:
                continue

            total_qty = sum(production_lines.mapped("product_uom_qty"))
            if total_qty > 0 and (not order.x_monthly_mgq or order.x_monthly_mgq <= 0):
                order.x_monthly_mgq = total_qty

            if not order.x_workcenter_id:
                workcenters = production_lines.mapped("product_id.gear_workcenter_id")
                if workcenters:
                    order.x_workcenter_id = workcenters[0]

            start_dates = [fields.Date.to_date(dt) for dt in production_lines.mapped("start_date") if dt]
            end_dates = [fields.Date.to_date(dt) for dt in production_lines.mapped("return_date") if dt]

            if start_dates:
                min_start = min(start_dates)
                if not order.x_contract_start or order.x_contract_start > min_start:
                    order.x_contract_start = min_start
            if end_dates:
                max_end = max(end_dates)
                if not order.x_contract_end or order.x_contract_end < max_end:
                    order.x_contract_end = max_end

    @api.depends(
        "date_order",
        "x_cooling_period_months",
        "order_line.is_rental",
        "order_line.start_date",
        "order_line.reservation_begin",
        "rental_start_date",
    )
    def _compute_x_cooling_end(self):
        for order in self:
            contract_start = order._gear_get_contract_start_datetime()
            months = order.x_cooling_period_months
            if not contract_start or months is None:
                order.x_cooling_end = False
                continue
            order.x_cooling_end = contract_start + relativedelta(months=months, days=-1)

    def _gear_get_contract_start_datetime(self):
        self.ensure_one()
        rental_start = getattr(self, "rental_start_date", False)
        contract_start = rental_start
        renting_lines = self.order_line.filtered(lambda line: getattr(line, "is_rental", False))
        if not contract_start and renting_lines:
            line_fields = renting_lines._fields
            for field_name in ("start_date", "reservation_begin"):
                if field_name in line_fields:
                    values = [dt for dt in renting_lines.mapped(field_name) if dt]
                    if values:
                        contract_start = min(values)
                        break
        return contract_start or self.date_order

    def gear_register_ngt(self, request):
        """Distribute NGT relief across the impacted daily manufacturing orders."""
        self.ensure_one()
        productions = self._gear_get_productions_between(request.date_start, request.date_end)
        for production in productions:
            hours = self._gear_overlap_hours(production, request.date_start, request.date_end)
            if hours:
                production.gear_allocate_relief_hours(hours, "ngt")

    def gear_register_loto(self, request):
        """Apply LOTO relief and compute the wave-off utilisation."""
        self.ensure_one()
        productions = self._gear_get_productions_between(request.date_start, request.date_end)
        grouped = defaultdict(list)
        for production in productions:
            grouped[production.x_monthly_order_id].append(production)

        total_waveoff = 0.0
        total_chargeable = 0.0

        for monthly_order, items in grouped.items():
            if not monthly_order:
                continue
            allowance = self.x_loto_waveoff_hours or 0.0
            used = monthly_order.waveoff_hours_applied or 0.0
            remaining_waveoff = max(allowance - used, 0.0)
            for production in sorted(items, key=lambda p: p.date_start or datetime.min):
                hours = self._gear_overlap_hours(production, request.date_start, request.date_end)
                if not hours:
                    continue
                waveoff_applied = min(remaining_waveoff, hours)
                chargeable = hours - waveoff_applied
                production.gear_allocate_relief_hours(hours, "loto")
                production.gear_apply_loto_waveoff(waveoff_applied, chargeable)
                total_waveoff += waveoff_applied
                total_chargeable += chargeable
                remaining_waveoff -= waveoff_applied
        remainder = round(request.hours_total - (total_waveoff + total_chargeable), 2)
        if remainder > 0:
            total_chargeable += remainder
        return total_waveoff, total_chargeable

    def _gear_get_productions_between(self, start_dt, end_dt):
        Production = self.env["mrp.production"]
        range_domain = AND(
            [
                [("x_sale_order_id", "in", self.ids)],
                OR(
                    [
                        [("date_finished", "=", False)],
                        [("date_finished", ">=", start_dt)],
                    ]
                ),
                OR(
                    [
                        [("date_start", "=", False)],
                        [("date_start", "<=", end_dt)],
                    ]
                ),
            ]
        )
        productions = Production.search(range_domain, order="date_start asc, id asc")
        # Filter out any productions that still do not overlap once their window is inferred.
        return productions.filtered(
            lambda production: self._gear_overlap_hours(production, start_dt, end_dt) > 0.0
        )

    @staticmethod
    def _gear_infer_production_window(production):
        """Return a best-effort (start, end) tuple for the production window."""
        tz_name = production.env.context.get("tz") or production.env.user.tz or "UTC"
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.utc

        def to_local(dt):
            if not dt:
                return None
            if dt.tzinfo:
                dt_utc = dt.astimezone(pytz.utc)
            else:
                dt_utc = pytz.utc.localize(dt)
            return dt_utc.astimezone(user_tz)

        def to_utc(local_dt):
            return local_dt.astimezone(pytz.utc).replace(tzinfo=None)

        start = production.date_start or getattr(production, "date_planned_start", False)
        end = production.date_finished or getattr(production, "date_planned_finished", False)

        inferred_date = False
        local_start = to_local(start)
        local_end = to_local(end)
        if local_start:
            inferred_date = local_start.date()
        elif local_end:
            inferred_date = local_end.date()
        elif production.name and "-" in production.name:
            suffix = production.name.rsplit("-", 1)[-1]
            try:
                inferred_date = datetime.strptime(suffix, "%Y%m%d").date()
            except ValueError:
                inferred_date = False

        if inferred_date:
            day_start = user_tz.localize(datetime.combine(inferred_date, time.min))
            day_end = user_tz.localize(datetime.combine(inferred_date, time(23, 59, 59)))
            if not start:
                start = to_utc(day_start)
            else:
                start = min(start, to_utc(day_start))
            if not end:
                end = to_utc(day_end)
            else:
                end = max(end, to_utc(day_end))

        return start, end

    @staticmethod
    def _gear_overlap_hours(production, start_dt, end_dt):
        start, end = SaleOrder._gear_infer_production_window(production)
        start = start or start_dt
        end = end or end_dt
        window_start = max(start_dt, start)
        window_end = min(end_dt, end)
        if window_end <= window_start:
            return 0.0
        delta = window_end - window_start
        return round(delta.total_seconds() / 3600.0, 2)

    # ------------------------------------------------------------------
    # Batching-plant quotation acceptance → SO auto-creation
    # ------------------------------------------------------------------
    def _gear_optional_service_rate(self, code):
        self.ensure_one()
        services = self.gear_optional_service_ids.filtered(lambda s: s.code == code)
        if services:
            return services[:1]
        return self.env["gear.optional.service.master"].search([("code", "=", code)], limit=1)

    def _gear_snapshot_optional_rates(self, final_rates=None):
        """Compute per-CUM optional service surcharges based on selected masters."""

        self.ensure_one()
        mgq = self.mgq_monthly or self.x_monthly_mgq or 0.0
        result = {
            "gear_transport_per_cum": 0.0,
            "gear_pump_per_cum": 0.0,
            "gear_manpower_per_cum": 0.0,
            "gear_diesel_per_cum": 0.0,
            "gear_jcb_monthly": 0.0,
        }

        def add_optional(target_key, code, enabled):
            if not enabled:
                return
            service = self._gear_optional_service_rate(code)
            if not service:
                return
            rate = service.rate or 0.0
            if service.charge_type == "per_cum":
                result[target_key] = rate
            elif service.charge_type in ("per_month", "fixed") and mgq:
                result[target_key] = rate / mgq
            if code == "jcb":
                result["gear_jcb_monthly"] = rate

        add_optional("gear_transport_per_cum", "transport", self.gear_transport_opt_in)
        add_optional("gear_pump_per_cum", "pump", self.gear_pumping_opt_in)
        add_optional("gear_manpower_per_cum", "manpower", self.gear_manpower_opt_in)
        add_optional("gear_diesel_per_cum", "diesel", self.gear_diesel_opt_in)
        add_optional("gear_jcb_monthly", "jcb", self.gear_jcb_opt_in)

        if final_rates:
            result["gear_optional_services_cost"] = final_rates.get("optional_cost", 0.0)

        return result

    def _gear_prepare_batching_so_vals(self, final_rates, optional_rates):
        """Prepare Sales Order values using the quotation snapshot plus calculator output."""

        self.ensure_one()
        optional_rates = optional_rates or {}

        base_vals = {
            "partner_id": self.partner_id.id,
            "partner_invoice_id": self.partner_invoice_id.id,
            "partner_shipping_id": self.partner_shipping_id.id,
            "pricelist_id": self.pricelist_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "origin": self.name,
            "x_billing_category": "plant",
            "gear_quote_source_id": self.id,
            "gear_service_id": self.gear_service_id.id,
            "gear_service_type": self.gear_service_type,
            "gear_capacity_id": self.gear_capacity_id.id,
            "gear_mgq_rate_id": self.gear_mgq_rate_id.id,
            "gear_design_mix_id": self.gear_design_mix_id.id,
            "gear_material_area_id": self.gear_material_area_id.id,
            "gear_cement_area_id": self.gear_cement_area_id.id,
            "gear_agg_10mm_area_id": self.gear_agg_10mm_area_id.id,
            "gear_agg_20mm_area_id": self.gear_agg_20mm_area_id.id,
            "gear_admixture_area_id": self.gear_admixture_area_id.id,
            "gear_project_duration_years": self.gear_project_duration_years,
            "gear_project_duration_months": self.gear_project_duration_months,
            "gear_civil_scope": self.gear_civil_scope,
            "mgq_monthly": self.mgq_monthly,
            "x_monthly_mgq": self.x_monthly_mgq,
            "prime_rate": self.prime_rate,
            "optimize_rate": self.optimize_rate,
            "excess_rate": self.excess_rate,
            "gear_expected_production_qty": self.gear_expected_production_qty,
            "gear_dead_cost_amount": self.gear_dead_cost_amount,
            "gear_dead_cost_months": self.gear_dead_cost_months,
            "x_inventory_mode": self.x_inventory_mode,
            "gear_optional_service_ids": [(6, 0, self.gear_optional_service_ids.ids)],
            "gear_transport_opt_in": self.gear_transport_opt_in,
            "gear_pumping_opt_in": self.gear_pumping_opt_in,
            "gear_manpower_opt_in": self.gear_manpower_opt_in,
            "gear_diesel_opt_in": self.gear_diesel_opt_in,
            "gear_jcb_opt_in": self.gear_jcb_opt_in,
            "gear_optional_services_cost": final_rates.get("optional_cost", 0.0),
            "gear_dead_cost_per_cum": final_rates.get("dead_cost", 0.0),
            "gear_transport_per_cum": optional_rates.get("gear_transport_per_cum", 0.0),
            "gear_pump_per_cum": optional_rates.get("gear_pump_per_cum", 0.0),
            "gear_manpower_per_cum": optional_rates.get("gear_manpower_per_cum", 0.0),
            "gear_diesel_per_cum": optional_rates.get("gear_diesel_per_cum", 0.0),
            "gear_jcb_monthly": optional_rates.get("gear_jcb_monthly", 0.0),
        }

        if self.x_inventory_mode == "with_inventory":
            base_vals.update(
                {
                    "gear_base_plant_rate": final_rates.get("base_plant_rate", 0.0),
                    "gear_material_cost_total": final_rates.get("material_cost", 0.0),
                    "gear_total_per_cum_rate": final_rates.get("total_per_cum", 0.0),
                }
            )
        else:
            base_vals.update(
                {
                    "gear_prime_rate_final": final_rates.get("final_prime_rate", 0.0),
                    "gear_optimize_rate_final": final_rates.get("final_optimize_rate", 0.0),
                    "gear_after_mgq_rate_final": final_rates.get("final_after_mgq_rate", 0.0),
                }
            )

        return base_vals

    def _gear_resolve_line_product(self):
        """Pick a product for generated SO lines to ensure UoM/valuation works."""

        self.ensure_one()
        primary = self._gear_get_primary_product()
        if primary:
            return primary
        fallback = self.env.ref("product.product_product_1", raise_if_not_found=False)
        return fallback

    def _gear_build_inventory_line_note(self, final_rates):
        parts = []
        if self.gear_design_mix_id:
            parts.append(f"Design Mix: {self.gear_design_mix_id.display_name}")
        if self.gear_material_area_id:
            parts.append(f"Material Area: {self.gear_material_area_id.display_name}")
        if final_rates.get("material_cost"):
            parts.append(f"Material Cost/CUM: {final_rates.get('material_cost'):.2f}")
        if final_rates.get("optional_cost"):
            parts.append(f"Optional Services/CUM: {final_rates.get('optional_cost'):.2f}")
        if final_rates.get("dead_cost"):
            parts.append(f"Dead Cost/CUM: {final_rates.get('dead_cost'):.2f}")
        enabled_optional = self.gear_optional_service_ids.filtered(
            lambda s: (
                (s.code == "transport" and self.gear_transport_opt_in)
                or (s.code == "pump" and self.gear_pumping_opt_in)
                or (s.code == "manpower" and self.gear_manpower_opt_in)
                or (s.code == "diesel" and self.gear_diesel_opt_in)
                or (s.code == "jcb" and self.gear_jcb_opt_in)
            )
        )
        if enabled_optional:
            parts.append(
                "Optional Services: "
                + ", ".join(enabled_optional.mapped("display_name"))
            )
        return "\n".join(parts)

    def _gear_prepare_batching_so_lines(self, final_rates):
        self.ensure_one()
        product = self._gear_resolve_line_product()
        line_commands = []

        if self.x_inventory_mode == "with_inventory":
            name = "Concrete Supply"
            if self.gear_design_mix_id:
                name = f"Concrete Supply — Grade {self.gear_design_mix_id.grade.upper()}"
            note = self._gear_build_inventory_line_note(final_rates)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": product.id if product else False,
                        "product_uom_qty": 1.0,
                        "price_unit": final_rates.get("total_per_cum", 0.0),
                        "name": note or name,
                    },
                )
            )
        else:
            tiers = [
                ("Prime Output Rate — MGQ Billing", final_rates.get("final_prime_rate", 0.0)),
                ("Optimize Shortfall Rate — MGQ Billing", final_rates.get("final_optimize_rate", 0.0)),
                ("After-MGQ Excess Rate — MGQ Billing", final_rates.get("final_after_mgq_rate", 0.0)),
            ]
            for name, price in tiers:
                line_commands.append(
                    (
                        0,
                        0,
                        {
                            "product_id": product.id if product else False,
                            "product_uom_qty": 1.0,
                            "price_unit": price or 0.0,
                            "name": name,
                        },
                    )
                )
        return line_commands

    def action_accept_and_create_so(self):
        """Accept batching-plant quotation and generate a Sales Order snapshot."""

        self.ensure_one()
        if self.gear_generated_so_id:
            return self.gear_generated_so_id

        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        final_rates = calculator.generate_final_rates(self)
        optional_rates = self._gear_snapshot_optional_rates(final_rates)

        write_vals = {
            "gear_quote_state": "accepted",
            "gear_optional_services_cost": final_rates.get("optional_cost", 0.0),
            "gear_dead_cost_per_cum": final_rates.get("dead_cost", 0.0),
            "x_billing_category": self.x_billing_category or "plant",
        }
        write_vals.update(optional_rates)

        if self.x_inventory_mode == "with_inventory":
            write_vals.update(
                {
                    "gear_base_plant_rate": final_rates.get("base_plant_rate", 0.0),
                    "gear_material_cost_total": final_rates.get("material_cost", 0.0),
                    "gear_total_per_cum_rate": final_rates.get("total_per_cum", 0.0),
                }
            )
        else:
            write_vals.update(
                {
                    "gear_prime_rate_final": final_rates.get("final_prime_rate", 0.0),
                    "gear_optimize_rate_final": final_rates.get("final_optimize_rate", 0.0),
                    "gear_after_mgq_rate_final": final_rates.get("final_after_mgq_rate", 0.0),
                }
            )

        self.sudo().write(write_vals)

        so_vals = self._gear_prepare_batching_so_vals(final_rates, optional_rates)
        line_commands = self._gear_prepare_batching_so_lines(final_rates)
        so_vals["order_line"] = line_commands

        so = self.env["sale.order"].sudo().create(so_vals)

        self.sudo().write({"gear_generated_so_id": so.id})

        message = "Batching-plant quotation accepted and Sales Order %s created." % so.name
        self.message_post(body=message, subtype_xmlid="mail.mt_note")
        so.message_post(body="Generated from batching-plant quotation %s." % self.name, subtype_xmlid="mail.mt_note")

        template = self.env.ref("gear_on_rent.mail_template_batching_quote_accept", raise_if_not_found=False)
        if template:
            template.sudo().send_mail(self.id, force_send=True)

        return so


    def _find_mail_template(self):
        self.ensure_one()
        if self.x_billing_category == 'plant':
            template = self.env.ref('gear_on_rent.mail_template_batching_quote_send', raise_if_not_found=False)
            if template:
                return template
        return super()._find_mail_template()

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        orders = lines.mapped("order_id")
        orders._gear_sync_billing_category()
        orders._gear_sync_production_defaults()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(field in vals for field in ["product_id", "product_template_id", "display_type", "product_uom_qty", "start_date", "return_date"]):
            orders = self.mapped("order_id")
            orders._gear_sync_billing_category()
            orders._gear_sync_production_defaults()
        return res

    def unlink(self):
        orders = self.mapped("order_id")
        res = super().unlink()
        orders._gear_sync_billing_category()
        orders._gear_sync_production_defaults()
        return res
