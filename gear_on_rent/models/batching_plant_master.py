from odoo import fields, models


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

    name = fields.Char(required=True)
    capacity_cum_hour = fields.Float(string="Capacity (CUM/Hr)", digits=(16, 2), required=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)


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
    currency_id = fields.Many2one("res.currency", string="Currency", required=True, default=lambda self: self.env.company.currency_id.id)
    company_id = fields.Many2one("res.company", string="Company", required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean(default=True)
