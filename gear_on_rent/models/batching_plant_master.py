from odoo import api, fields, models


class GearServiceMaster(models.Model):
    _name = "gear.service.master"
    _description = "Batching Service Category"

    name = fields.Char(required=True)
    category = fields.Selection(selection=[("dedicated", "Dedicated Plant"), ("turnkey", "Full Factory (Turnkey)")], required=True)
    inventory_mode = fields.Selection(selection=[("without_inventory", "Without Inventory"), ("with_inventory", "With Inventory")], required=True)
    active = fields.Boolean(default=True)


class GearPlantCapacityMaster(models.Model):
    _name = "gear.plant.capacity.master"
    _description = "Batching Plant Capacity"

    CAPACITY_COMPONENT_FIELDS = [
        "component_batching_plant",
        "component_cement_silos",
        "component_fly_ash_silos",
        "component_aggregate_belt",
        "component_screw_pump",
        "component_ground_dust_filter",
        "component_batch_cabin",
        "component_unloading_commissioning",
        "component_transportation",
        "component_dg_set",
        "component_power_board",
        "component_electrical_system",
        "component_transformer",
        "component_electrical_panel",
        "component_workshop_equipment",
        "component_weighbridge",
        "component_overhead_ht_line",
        "component_auxiliary_dg_set",
        "component_mechanical_broom",
        "component_misc",
        "component_ci_weights",
        "component_high_pressure_water",
        "component_fogging_system",
    ]

    name = fields.Char(required=True)
    capacity_cum_hour = fields.Float(string="Capacity (CUM/Hr)", digits=(16, 2), compute="_compute_component_totals", store=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)
    component_batching_plant = fields.Float(string="Batching Plant", digits=(16, 2))
    component_cement_silos = fields.Float(string="Cement (2 Nos) Silos", digits=(16, 2))
    component_fly_ash_silos = fields.Float(string="Fly Ash (1 No) Silos", digits=(16, 2))
    component_aggregate_belt = fields.Float(string="Aggregate Belt Conveyor", digits=(16, 2))
    component_screw_pump = fields.Float(string="Screw Pump & Blower System / Compressor", digits=(16, 2))
    component_ground_dust_filter = fields.Float(string="Ground Dust Filter with Air Compressor", digits=(16, 2))
    component_batch_cabin = fields.Float(string="Batch Cabin", digits=(16, 2))
    component_unloading_commissioning = fields.Float(string="Unloading, Erection and Commissioning", digits=(16, 2))
    component_transportation = fields.Float(string="Transportation", digits=(16, 2))
    component_dg_set = fields.Float(string="D G Set", digits=(16, 2))
    component_power_board = fields.Float(string="Power from Electricity Board", digits=(16, 2))
    component_electrical_system = fields.Float(string="Electrical System", digits=(16, 2))
    component_transformer = fields.Float(string="Transformer", digits=(16, 2))
    component_electrical_panel = fields.Float(string="Electrical Panel - with APFC", digits=(16, 2))
    component_workshop_equipment = fields.Float(string="Workshop Equipment", digits=(16, 2))
    component_weighbridge = fields.Float(string="Weighbridge 16 x 3, 100 T", digits=(16, 2))
    component_overhead_ht_line = fields.Float(string="Overhead HT Line / SEB Charges", digits=(16, 2))
    component_auxiliary_dg_set = fields.Float(string="Auxiliary DG Set", digits=(16, 2))
    component_mechanical_broom = fields.Float(string="Mechanical Broom", digits=(16, 2))
    component_misc = fields.Float(string="Misc.", digits=(16, 2))
    component_ci_weights = fields.Float(string="C I Weights", digits=(16, 2))
    component_high_pressure_water = fields.Float(string="High Pressure Water Gun", digits=(16, 2))
    component_fogging_system = fields.Float(string="Fogging System for Dust Control", digits=(16, 2))
    component_total = fields.Float(string="Plant Investment Total", digits=(16, 2), compute="_compute_component_totals", store=True)
    depreciation_years = fields.Float(string="Depreciation Years", digits=(16, 2), default=10.0)
    depreciation_monthly = fields.Float(string="Monthly Depreciation", digits=(16, 2), compute="_compute_depreciation", store=True)

    @api.depends(*CAPACITY_COMPONENT_FIELDS)
    def _compute_component_totals(self):
        for record in self:
            record.component_total = sum(getattr(record, field) or 0.0 for field in self.CAPACITY_COMPONENT_FIELDS)
            record.capacity_cum_hour = record.component_total

    @api.depends("component_total", "depreciation_years")
    def _compute_depreciation(self):
        for record in self:
            months = (record.depreciation_years or 0.0) * 12.0
            record.depreciation_monthly = record.component_total / months if months else 0.0


class GearMgqRateMaster(models.Model):
    _name = "gear.mgq.rate.master"
    _description = "MGQ Rate Tier"

    name = fields.Char(required=True)
    service_id = fields.Many2one("gear.service.master", string="Service", required=True)
    capacity_id = fields.Many2one("gear.plant.capacity.master", string="Plant Capacity", required=True)
    mgq_min = fields.Float(string="MGQ Min", digits=(16, 2))
    mgq_max = fields.Float(string="MGQ Max", digits=(16, 2))
    prime_rate = fields.Monetary(currency_field="currency_id", string="Prime Rate", digits=(16, 2))
    optimize_rate = fields.Monetary(currency_field="currency_id", string="Optimize Rate", digits=(16, 2))
    after_mgq_rate = fields.Monetary(currency_field="currency_id", string="After MGQ Rate", digits=(16, 2))
    ngt_rate = fields.Monetary(
        currency_field="currency_id",
        string="NGT Rate",
        help="Optional rate used to convert approved NGT hours into billable relief.",
    )
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean(default=True)


class GearCostComponentMaster(models.Model):
    _name = "gear.cost.component.master"
    _description = "Cost Component"

    name = fields.Char(required=True)
    component_type = fields.Selection(
        selection=[("base", "Base Plant"), ("material", "Material"), ("optional", "Optional Service"), ("dead_cost", "Dead Cost")],
        required=True,
    )
    uom_id = fields.Many2one("uom.uom", string="UoM")
    active = fields.Boolean(default=True)


class GearMaterialAreaMaster(models.Model):
    _name = "gear.material.area.master"
    _description = "Area-wise Material Pricing"

    name = fields.Char(required=True)
    area = fields.Char(required=True)
    cement_rate = fields.Monetary(currency_field="currency_id", string="Cement Rate")
    agg_10mm_rate = fields.Monetary(currency_field="currency_id", string="10mm Aggregate Rate")
    agg_20mm_rate = fields.Monetary(currency_field="currency_id", string="20mm Aggregate Rate")
    admixture_rate = fields.Monetary(currency_field="currency_id", string="Admixture Rate")
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean(default=True)


class GearDesignMixMaster(models.Model):
    _name = "gear.design.mix.master"
    _description = "Design Mix"

    name = fields.Char(required=True)
    grade = fields.Selection(selection=[("m10", "M10"), ("m20", "M20"), ("m25", "M25"), ("m30", "M30")], required=True)
    cement_qty = fields.Float(string="Cement (kg)", digits=(16, 2))
    agg_10mm_qty = fields.Float(string="10mm Aggregate (kg)", digits=(16, 2))
    agg_20mm_qty = fields.Float(string="20mm Aggregate (kg)", digits=(16, 2))
    admixture_qty = fields.Float(string="Admixture (ml)", digits=(16, 2))
    active = fields.Boolean(default=True)


class GearOptionalServiceMaster(models.Model):
    _name = "gear.optional.service.master"
    _description = "Optional Service Charge"

    name = fields.Char(required=True)
    code = fields.Char(string="Code")
    charge_type = fields.Selection(selection=[("per_cum", "Per CUM"), ("per_month", "Per Month"), ("fixed", "Fixed")], required=True)
    rate = fields.Monetary(currency_field="currency_id", digits=(16, 2))
    default_enabled = fields.Boolean(string="Enabled by Default", default=False)
    product_id = fields.Many2one(
        "product.product",
        string="Linked Product",
        domain="[('sale_ok', '=', True)]",
        help="Product that will be used on Sales Orders when this optional service is billed.",
    )
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean(default=True)

    def _ensure_product_id(self):
        ProductTemplate = self.env["product.template"]
        for service in self.filtered(lambda s: not s.product_id):
            template_vals = {
                "name": service.name,
                "type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "invoice_policy": "order",
                "list_price": service.rate or 0.0,
            }
            template = ProductTemplate.create(template_vals)
            service.product_id = template.product_variant_id

    @api.model_create_multi
    def create(self, vals_list):
        services = super().create(vals_list)
        services._ensure_product_id()
        return services

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals:
            for service in self.filtered("product_id"):
                service.product_id.name = service.name
        if "rate" in vals:
            for service in self.filtered("product_id"):
                service.product_id.list_price = service.rate or 0.0
        return res
