import json

from odoo import api, fields, models


class GearBatchingMasterCalculator(models.TransientModel):
    _name = "gear.batching.master.calculator"
    _description = "Batching Master Calculator"

    order_id = fields.Many2one("sale.order", string="Quotation / Order", required=True)
    production_qty = fields.Float(string="Production Qty Override (CUM)")

    mgq = fields.Float(string="MGQ", readonly=True)
    project_months = fields.Float(string="Project Months", readonly=True)

    running_per_cum = fields.Float(string="Running / CUM", readonly=True)
    depr_per_cum = fields.Float(string="Depreciation / CUM", readonly=True)
    dead_per_cum = fields.Float(string="Dead Cost / CUM", readonly=True)
    margin_per_cum = fields.Float(string="Margin / CUM", readonly=True)
    material_per_cum = fields.Float(string="Material / CUM", readonly=True)
    optional_per_cum = fields.Float(string="Optional / CUM", readonly=True)

    prime_rate = fields.Float(string="Prime Rate", readonly=True)
    optimize_rate = fields.Float(string="Optimize Rate", readonly=True)
    after_mgq_rate = fields.Float(string="After MGQ Rate", readonly=True)
    ngt_rate = fields.Float(string="NGT Rate", readonly=True)

    final_prime_rate = fields.Float(string="Final Prime Rate", readonly=True)
    final_optimize_rate = fields.Float(string="Final Optimize Rate", readonly=True)
    final_after_mgq_rate = fields.Float(string="Final After MGQ Rate", readonly=True)

    prime_bill = fields.Float(string="Prime Bill", readonly=True)
    optimize_bill = fields.Float(string="Optimize Bill", readonly=True)
    after_mgq_bill = fields.Float(string="After MGQ Bill", readonly=True)
    base_rate_per_cum = fields.Float(string="Base Rate / CUM", readonly=True)
    total_rate_per_cum = fields.Float(string="Effective Total Rate / CUM", readonly=True)

    optional_line_ids = fields.One2many(
        "gear.batching.master.calculator.service",
        "wizard_id",
        string="Optional Services",
        readonly=True,
    )
    prime_rate_log_json = fields.Text(string="Prime Rate Log", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get("order_id") or self.env.context.get("default_order_id")
        production_qty = res.get("production_qty") or self.env.context.get("default_production_qty")
        if order_id:
            wizard = self.new({
                "order_id": order_id,
                "production_qty": production_qty,
            })
            snapshot = wizard._compute_engine_snapshot()
            optional_commands = snapshot.pop("optional_line_ids", None)
            res.update(snapshot)
            if optional_commands is not None:
                res["optional_line_ids"] = optional_commands
        return res

    @api.onchange("order_id", "production_qty")
    def _onchange_recalculate(self):
        for wizard in self:
            wizard._refresh_from_engine()

    def _refresh_from_engine(self, skip_reset=False):
        self.ensure_one()
        if not skip_reset:
            self._reset_snapshot()

        if not self.order_id:
            return

        snapshot = self._compute_engine_snapshot()
        optional_commands = snapshot.pop("optional_line_ids", None)
        if optional_commands is not None:
            self.optional_line_ids = optional_commands
        if snapshot:
            self.update(snapshot)

    def _reset_snapshot(self):
        self.optional_line_ids = [(5, 0, 0)]
        self.update({
            "mgq": 0.0,
            "project_months": 0.0,
            "running_per_cum": 0.0,
            "depr_per_cum": 0.0,
            "dead_per_cum": 0.0,
            "margin_per_cum": 0.0,
            "material_per_cum": 0.0,
            "optional_per_cum": 0.0,
            "prime_rate": 0.0,
            "optimize_rate": 0.0,
            "after_mgq_rate": 0.0,
            "ngt_rate": 0.0,
            "final_prime_rate": 0.0,
            "final_optimize_rate": 0.0,
            "final_after_mgq_rate": 0.0,
            "prime_bill": 0.0,
            "optimize_bill": 0.0,
            "after_mgq_bill": 0.0,
            "base_rate_per_cum": 0.0,
            "total_rate_per_cum": 0.0,
            "prime_rate_log_json": False,
        })

    def _compute_engine_snapshot(self):
        self.ensure_one()
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.generate_final_rates(self.order_id, self.production_qty) or {}
        return self._prepare_rate_values(rates)

    def _prepare_rate_values(self, rates):
        self.ensure_one()
        prime_rate_log = rates.get("prime_rate_log") or {}
        components = prime_rate_log.get("components") or {}
        optional_services = components.get("optional", {}).get("services") or []

        optional_commands = [(5, 0, 0)]
        for service in optional_services:
            optional_commands.append((0, 0, {
                "name": service.get("name") or service.get("code"),
                "code": service.get("code"),
                "charge_type": service.get("charge_type"),
                "rate_value": service.get("rate_value", 0.0),
                "per_cum": service.get("per_cum", 0.0),
            }))

        return {
            "optional_line_ids": optional_commands,
            "mgq": rates.get("mgq", 0.0),
            "production_qty": rates.get("production_qty", self.production_qty),
            "project_months": prime_rate_log.get("project_months", 0.0),
            "running_per_cum": rates.get("running_per_cum", 0.0),
            "depr_per_cum": rates.get("depr_per_cum", 0.0),
            "dead_per_cum": rates.get("dead_per_cum", 0.0),
            "margin_per_cum": rates.get("margin_per_cum", 0.0),
            "material_per_cum": rates.get("material_per_cum", 0.0),
            "optional_per_cum": rates.get("optional_per_cum", 0.0),
            "prime_rate": rates.get("prime_rate", 0.0),
            "optimize_rate": rates.get("optimize_rate", 0.0),
            "after_mgq_rate": rates.get("after_mgq_rate", 0.0),
            "ngt_rate": rates.get("ngt_rate", 0.0),
            "final_prime_rate": rates.get("final_prime_rate", 0.0),
            "final_optimize_rate": rates.get("final_optimize_rate", 0.0),
            "final_after_mgq_rate": rates.get("final_after_mgq_rate", 0.0),
            "prime_bill": rates.get("prime_bill", 0.0),
            "optimize_bill": rates.get("optimize_bill", 0.0),
            "after_mgq_bill": rates.get("after_mgq_bill", 0.0),
            "base_rate_per_cum": rates.get("base_rate_per_cum", 0.0),
            "total_rate_per_cum": rates.get("total_rate_per_cum", 0.0),
            "prime_rate_log_json": json.dumps(prime_rate_log, indent=2, sort_keys=True)
            if prime_rate_log
            else False,
        }


class GearBatchingMasterCalculatorService(models.TransientModel):
    _name = "gear.batching.master.calculator.service"
    _description = "Batching Master Calculator Service"

    wizard_id = fields.Many2one("gear.batching.master.calculator", ondelete="cascade")
    name = fields.Char(string="Service")
    code = fields.Char(string="Code")
    charge_type = fields.Selection(
        [
            ("per_cum", "Per CUM"),
            ("per_month", "Per Month"),
            ("fixed", "Fixed"),
        ],
        string="Charge Type",
    )
    rate_value = fields.Float(string="Rate")
    per_cum = fields.Float(string="Per CUM")
