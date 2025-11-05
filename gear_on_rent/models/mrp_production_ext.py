from datetime import timedelta

from odoo import api, fields, models


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
            production.x_prime_output_qty = sum(production.x_docket_ids.mapped("qty_m3"))

    @api.depends("x_adjusted_target_qty", "x_prime_output_qty")
    def _compute_optimized_standby_qty(self):
        for production in self:
            adjusted = production.x_adjusted_target_qty or 0.0
            prime = production.x_prime_output_qty or 0.0
            production.x_optimized_standby_qty = max(adjusted - prime, 0.0)

    @api.depends("x_docket_ids.runtime_minutes", "x_docket_ids.idle_minutes")
    def _compute_runtime_idle_minutes(self):
        for production in self:
            production.x_runtime_minutes = sum(production.x_docket_ids.mapped("runtime_minutes"))
            production.x_idle_minutes = sum(production.x_docket_ids.mapped("idle_minutes"))

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

    def _gear_hours_to_qty(self, hours):
        self.ensure_one()
        target = self.x_daily_target_qty or 0.0
        if not target:
            return 0.0
        # Assume uniform production across the day; convert hours to MGQ relief.
        return target * (hours / 24.0)

    @api.model
    def gear_find_mo_for_datetime(self, workcenter, timestamp):
        """Locate the MO whose work order is active at the given timestamp."""
        Workorder = self.env["mrp.workorder"]
        workorder = Workorder.gear_find_workorder(workcenter, timestamp)
        return workorder.production_id if workorder else self.browse()


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
    gear_recipe_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Recipe Product",
        help="Concrete product whose recipe should be followed for this work order.",
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

    @api.depends("gear_docket_ids.qty_m3")
    def _compute_prime_output_qty(self):
        for workorder in self:
            workorder.gear_prime_output_qty = sum(workorder.gear_docket_ids.mapped("qty_m3"))

    @api.depends("gear_docket_ids.runtime_minutes", "gear_docket_ids.idle_minutes")
    def _compute_runtime_idle_minutes(self):
        for workorder in self:
            workorder.gear_runtime_minutes = sum(workorder.gear_docket_ids.mapped("runtime_minutes"))
            workorder.gear_idle_minutes = sum(workorder.gear_docket_ids.mapped("idle_minutes"))

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

    def button_start(self, raise_on_invalid_state=False):
        res = super().button_start(raise_on_invalid_state=raise_on_invalid_state)
        self._gear_update_docket_states(target_state="in_production")
        return res

    def button_finish(self):
        res = super().button_finish()
        self._gear_finalize_dockets()
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
            date_value = fields.Date.to_date(workorder.date_start) if workorder.date_start else fields.Date.context_today(workorder)
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
                "quantity_ordered": workorder.qty_production or production.product_qty,
            }
            docket_model.create(docket_vals)

    def _gear_update_docket_states(self, target_state):
        valid_states = {"draft", "in_production", "ready", "dispatched"}
        for workorder in self:
            dockets = workorder.gear_docket_ids.filtered(lambda d: d.state in valid_states)
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
            dockets = workorder.gear_docket_ids
            if not dockets:
                continue
            produced_qty = workorder.qty_produced or workorder.qty_production or 0.0
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
