from odoo import api, fields, models


def _recompute_prime_logs_for_companies(env, companies):
    """Refresh batching plant prime logs for the provided companies."""
    Company = env["res.company"]
    SaleOrder = env["sale.order"].sudo()
    companies = (companies or Company.browse()).filtered("id")
    if not companies:
        companies = Company.browse(env.company.id)
    if not companies:
        return
    domain = [
        ("company_id", "in", companies.ids),
        ("x_billing_category", "=", "plant"),
    ]
    orders = SaleOrder.search(domain)
    if orders:
        orders._gear_refresh_prime_rate_log()


class GearRunningCostMaster(models.Model):
    _name = "gear.running.cost.master"
    _description = "Running Cost Master"

    manpower_monthly = fields.Float(string="Manpower (Monthly)")
    power_monthly = fields.Float(string="Power (Monthly)")
    dg_monthly = fields.Float(string="DG (Monthly)")
    jcb_monthly = fields.Float(string="JCB (Monthly)")
    admin_monthly = fields.Float(string="Admin (Monthly)")
    interest_monthly = fields.Float(string="Interest (Monthly)")
    total_monthly = fields.Float(string="Total Monthly", compute="_compute_total_monthly", store=True)
    land_investment = fields.Float(string="Land / Site Development")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company.id
    )

    @api.model
    def _active_records(self, company=None):
        company = company or self.env.company
        domain = [("active", "=", True), ("company_id", "=", company.id)]
        records = self.search(domain)
        if records:
            return records
        # Fallback: return any active records so breakdown widgets do not stay blank.
        return self.search([("active", "=", True)])

    @api.model
    def compute_totals(self, company=None):
        records = self._active_records(company)

        def _sum(field):
            return sum(records.mapped(field) or [])

        totals = {
            "manpower_monthly": _sum("manpower_monthly"),
            "power_monthly": _sum("power_monthly"),
            "dg_monthly": _sum("dg_monthly"),
            "jcb_monthly": _sum("jcb_monthly"),
            "admin_monthly": _sum("admin_monthly"),
            "interest_monthly": _sum("interest_monthly"),
            "land_investment": _sum("land_investment"),
        }
        totals["running_total"] = sum(totals.values())
        return totals

    @api.depends(
        "manpower_monthly",
        "power_monthly",
        "dg_monthly",
        "jcb_monthly",
        "admin_monthly",
        "interest_monthly",
        "land_investment",
    )
    def _compute_total_monthly(self):
        for record in self:
            record.total_monthly = (
                (record.manpower_monthly or 0.0)
                + (record.power_monthly or 0.0)
                + (record.dg_monthly or 0.0)
                + (record.jcb_monthly or 0.0)
                + (record.admin_monthly or 0.0)
                + (record.interest_monthly or 0.0)
                + (record.land_investment or 0.0)
            )

    @api.model
    def compute_total(self, company=None):
        totals = self.compute_totals(company)
        return totals.get("running_total", 0.0)

    def _refresh_prime_logs(self, companies=None):
        companies = (companies or self.env["res.company"].browse()) | self.mapped("company_id")
        _recompute_prime_logs_for_companies(self.env, companies)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_prime_logs()
        return records

    def write(self, vals):
        companies_before = self.mapped("company_id")
        res = super().write(vals)
        companies_after = self.mapped("company_id")
        companies = companies_before | companies_after
        _recompute_prime_logs_for_companies(self.env, companies)
        return res

    def unlink(self):
        companies = self.mapped("company_id")
        res = super().unlink()
        _recompute_prime_logs_for_companies(self.env, companies)
        return res


class GearCapexMaster(models.Model):
    _name = "gear.capex.master"
    _description = "CAPEX Master"

    plant_machinery_capex = fields.Float(string="Plant & Machinery")
    furniture_capex = fields.Float(string="Furniture")
    equipment_fittings_capex = fields.Float(string="Equipment & Fittings")
    computers_peripherals_capex = fields.Float(string="Computers & Peripherals")
    component_total = fields.Float(string="Component Total", compute="_compute_component_total", store=True)
    component_total = fields.Float(string="Component Total", compute="_compute_component_total", store=True)
    useful_life_years = fields.Float(string="Useful Life (Years)", default=10.0)
    monthly_depreciation = fields.Float(string="Monthly Depreciation", compute="_compute_component_total", store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company.id
    )

    @api.model
    def _active_records(self, company=None):
        company = company or self.env.company
        domain = [("active", "=", True), ("company_id", "=", company.id)]
        records = self.search(domain)
        if records:
            return records
        return self.search([("active", "=", True)])

    @api.model
    def compute_totals(self, company=None):
        records = self._active_records(company)

        def _sum(field):
            return sum(records.mapped(field) or [])

        totals = {
            "plant_machinery_capex": _sum("plant_machinery_capex"),
            "furniture_capex": _sum("furniture_capex"),
            "equipment_fittings_capex": _sum("equipment_fittings_capex"),
            "computers_peripherals_capex": _sum("computers_peripherals_capex"),
        }
        totals["total_capex"] = sum(totals.values())

        useful_months_total = 0.0
        for rec in records:
            months = rec.useful_life_years * 12.0 if rec.useful_life_years else 0.0
            if months:
                rec_total = (
                    (rec.plant_machinery_capex or 0.0)
                    + (rec.furniture_capex or 0.0)
                    + (rec.equipment_fittings_capex or 0.0)
                    + (rec.computers_peripherals_capex or 0.0)
                )
                useful_months_total += rec_total / months
        totals["monthly_depreciation"] = useful_months_total or (
            totals["total_capex"] / (records[:1].useful_life_years * 12.0)
            if records and records[:1].useful_life_years
            else 0.0
        )
        totals["useful_life_years"] = records[:1].useful_life_years if records else 0.0
        return totals

    @api.model
    def compute_total(self, company=None):
        totals = self.compute_totals(company)
        return totals.get("total_capex", 0.0)

    def _refresh_prime_logs(self, companies=None):
        companies = (companies or self.env["res.company"].browse()) | self.mapped("company_id")
        _recompute_prime_logs_for_companies(self.env, companies)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_prime_logs()
        return records

    def write(self, vals):
        companies_before = self.mapped("company_id")
        res = super().write(vals)
        companies_after = self.mapped("company_id")
        companies = companies_before | companies_after
        _recompute_prime_logs_for_companies(self.env, companies)
        return res

    def unlink(self):
        companies = self.mapped("company_id")
        res = super().unlink()
        _recompute_prime_logs_for_companies(self.env, companies)
        return res

    @api.depends(
        "plant_machinery_capex",
        "furniture_capex",
        "equipment_fittings_capex",
        "computers_peripherals_capex",
        "useful_life_years",
    )
    def _compute_component_total(self):
        for record in self:
            record.component_total = (
                (record.plant_machinery_capex or 0.0)
                + (record.furniture_capex or 0.0)
                + (record.equipment_fittings_capex or 0.0)
                + (record.computers_peripherals_capex or 0.0)
            )
            months = (record.useful_life_years or 0.0) * 12.0
            record.monthly_depreciation = record.component_total / months if months else 0.0


class GearDeadCostMaster(models.Model):
    _name = "gear.dead.cost.master"
    _description = "Dead Cost Master"

    civil_factory_building = fields.Float(string="Factory Building")
    civil_non_factory_building = fields.Float(string="Non-Factory Building")
    construction_total = fields.Float(string="Construction Total", compute="_compute_construction_total", store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company.id
    )

    @api.model
    def _active_records(self, company=None):
        company = company or self.env.company
        domain = [("active", "=", True), ("company_id", "=", company.id)]
        records = self.search(domain)
        if records:
            return records
        return self.search([("active", "=", True)])

    @api.model
    def compute_totals(self, company=None):
        records = self._active_records(company)

        def _sum(field):
            return sum(records.mapped(field) or [])

        totals = {
            "civil_factory_building": _sum("civil_factory_building"),
            "civil_non_factory_building": _sum("civil_non_factory_building"),
        }
        totals["dead_total"] = sum(totals.values())
        return totals

    @api.model
    def compute_total(self, company=None):
        totals = self.compute_totals(company)
        return totals.get("dead_total", 0.0)

    def _refresh_prime_logs(self, companies=None):
        companies = (companies or self.env["res.company"].browse()) | self.mapped("company_id")
        _recompute_prime_logs_for_companies(self.env, companies)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_prime_logs()
        return records

    def write(self, vals):
        companies_before = self.mapped("company_id")
        res = super().write(vals)
        companies_after = self.mapped("company_id")
        companies = companies_before | companies_after
        _recompute_prime_logs_for_companies(self.env, companies)
        return res

    def unlink(self):
        companies = self.mapped("company_id")
        res = super().unlink()
        _recompute_prime_logs_for_companies(self.env, companies)
        return res

    @api.depends("civil_factory_building", "civil_non_factory_building")
    def _compute_construction_total(self):
        for record in self:
            record.construction_total = (record.civil_factory_building or 0.0) + (record.civil_non_factory_building or 0.0)


class GearCostingOverview(models.Model):
    _name = "gear.costing.overview"
    _description = "Prime Costing Overview"

    name = fields.Char(string="Name", required=True, default="Costing Overview")
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company.id
    )
    currency_id = fields.Many2one(
        "res.currency", string="Currency", related="company_id.currency_id", store=True, readonly=True
    )
    running_total = fields.Monetary(string="Running Monthly", compute="_compute_overview", currency_field="currency_id")
    running_manpower = fields.Monetary(string="Manpower", compute="_compute_overview", currency_field="currency_id")
    running_power = fields.Monetary(string="Power", compute="_compute_overview", currency_field="currency_id")
    running_dg = fields.Monetary(string="DG", compute="_compute_overview", currency_field="currency_id")
    running_jcb = fields.Monetary(string="JCB", compute="_compute_overview", currency_field="currency_id")
    running_admin = fields.Monetary(string="Admin", compute="_compute_overview", currency_field="currency_id")
    running_interest = fields.Monetary(string="Interest", compute="_compute_overview", currency_field="currency_id")
    running_land = fields.Monetary(string="Land / Site Development", compute="_compute_overview", currency_field="currency_id")

    capex_total = fields.Monetary(string="CAPEX Total", compute="_compute_overview", currency_field="currency_id")
    capex_plant_machinery = fields.Monetary(string="Plant & Machinery", compute="_compute_overview", currency_field="currency_id")
    capex_furniture = fields.Monetary(string="Furniture", compute="_compute_overview", currency_field="currency_id")
    capex_equipment = fields.Monetary(string="Equipment & Fittings", compute="_compute_overview", currency_field="currency_id")
    capex_computers = fields.Monetary(string="Computers & Peripherals", compute="_compute_overview", currency_field="currency_id")
    capex_monthly_depr = fields.Monetary(
        string="Monthly Depreciation", compute="_compute_overview", currency_field="currency_id"
    )

    dead_total = fields.Monetary(string="Dead Cost Total", compute="_compute_overview", currency_field="currency_id")
    dead_factory = fields.Monetary(string="Factory Building", compute="_compute_overview", currency_field="currency_id")
    dead_non_factory = fields.Monetary(string="Non-Factory Building", compute="_compute_overview", currency_field="currency_id")

    base_prime_monthly = fields.Monetary(
        string="Base Prime Monthly", compute="_compute_overview", currency_field="currency_id"
    )
    base_prime_formula = fields.Char(string="Base Prime Formula", compute="_compute_overview")
    margin_percent = fields.Float(string="Margin %", default=15.0)
    margin_amount = fields.Monetary(string="Margin Amount", compute="_compute_overview", currency_field="currency_id")
    final_prime_rate = fields.Monetary(string="Final Prime Monthly", compute="_compute_overview", currency_field="currency_id")
    final_prime_formula = fields.Char(string="Final Prime Formula", compute="_compute_overview")

    def _compute_overview(self):
        Running = self.env["gear.running.cost.master"]
        Capex = self.env["gear.capex.master"]
        Dead = self.env["gear.dead.cost.master"]
        for record in self:
            company = record.company_id or self.env.company
            running_totals = Running.compute_totals(company)
            capex_totals = Capex.compute_totals(company)
            dead_totals = Dead.compute_totals(company)
            record.running_manpower = running_totals.get("manpower_monthly", 0.0)
            record.running_power = running_totals.get("power_monthly", 0.0)
            record.running_dg = running_totals.get("dg_monthly", 0.0)
            record.running_jcb = running_totals.get("jcb_monthly", 0.0)
            record.running_admin = running_totals.get("admin_monthly", 0.0)
            record.running_interest = running_totals.get("interest_monthly", 0.0)
            record.running_land = running_totals.get("land_investment", 0.0)
            record.running_total = running_totals.get("running_total", 0.0)

            record.capex_plant_machinery = capex_totals.get("plant_machinery_capex", 0.0)
            record.capex_furniture = capex_totals.get("furniture_capex", 0.0)
            record.capex_equipment = capex_totals.get("equipment_fittings_capex", 0.0)
            record.capex_computers = capex_totals.get("computers_peripherals_capex", 0.0)
            record.capex_total = capex_totals.get("total_capex", 0.0)
            record.capex_monthly_depr = capex_totals.get("monthly_depreciation", 0.0)

            record.dead_factory = dead_totals.get("civil_factory_building", 0.0)
            record.dead_non_factory = dead_totals.get("civil_non_factory_building", 0.0)
            record.dead_total = dead_totals.get("dead_total", 0.0)
            record.base_prime_monthly = (
                record.running_total + record.capex_monthly_depr + record.dead_total
            )
            record.base_prime_formula = "%s + %s + %s" % (
                f"{record.running_total:.2f}",
                f"{record.capex_monthly_depr:.2f}",
                f"{record.dead_total:.2f}",
            )
            record.margin_amount = (record.base_prime_monthly or 0.0) * (record.margin_percent or 0.0) / 100.0
            record.final_prime_rate = record.base_prime_monthly + record.margin_amount
            record.final_prime_formula = "%s + (%s x %s%%)" % (
                f"{record.base_prime_monthly:.2f}",
                f"{record.base_prime_monthly:.2f}",
                record.margin_percent,
            )
