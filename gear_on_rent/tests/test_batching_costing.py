import pytest

try:  # pragma: no cover - skip when Odoo is unavailable
    from odoo.tests import SavepointCase
except ModuleNotFoundError:  # pragma: no cover
    pytest.skip("The Odoo framework is not available in this execution environment.", allow_module_level=True)


class TestBatchingCostingEngine(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("gear_on_rent.group_gear_on_rent_manager")

        cls.partner = cls.env["res.partner"].create({"name": "Costing Customer"})

        cls.running_master = cls.env["gear.running.cost.master"].create(
            {
                "power_monthly": 95000,
                "dg_monthly": 48000,
                "diesel_monthly": 0,
                "admin_monthly": 13000,
                "interest_monthly": 39000,
                "land_investment": 75000,
                "company_id": cls.env.company.id,
            }
        )

        cls.capex_master = cls.env["gear.capex.master"].create(
            {
                "plant_machinery_capex": 20000000,
                "furniture_capex": 500000,
                "equipment_fittings_capex": 250000,
                "computers_peripherals_capex": 150000,
                "useful_life_years": 10,
                "company_id": cls.env.company.id,
            }
        )

        cls.dead_master = cls.env["gear.dead.cost.master"].create(
            {
                "civil_factory_building": 400000,
                "civil_non_factory_building": 200000,
                "company_id": cls.env.company.id,
            }
        )

        order_vals = {
            "partner_id": cls.partner.id,
            "mgq_monthly": 3000,
            "gear_project_duration_months": 36,
            "gear_civil_scope": "vendor",
            "x_billing_category": "plant",
            "gear_manpower_opt_in": True,
            "gear_manpower_per_cum": 15.0,
        }
        cls.vendor_order = cls.env["sale.order"].create(order_vals)
        customer_vals = dict(order_vals, gear_civil_scope="customer")
        cls.customer_order = cls.env["sale.order"].create(customer_vals)

    def test_running_costs_roll_up(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.vendor_order)
        print("Batching calculator output:", rates)
        self.assertGreater(rates.get("running_per_cum"), 0)

    def test_depreciation_roll_up(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.vendor_order)
        self.assertGreater(rates.get("depr_per_cum"), 0)

    def test_dead_cost_roll_up(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.vendor_order)
        self.assertGreater(rates.get("dead_per_cum"), 0)

    def test_dead_cost_excluded_for_customer_scope(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.customer_order)
        self.assertEqual(rates.get("dead_per_cum", 0.0), 0.0)

    def test_final_prime_includes_surcharges(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.vendor_order)
        self.assertGreater(rates.get("final_prime_rate", 0.0), rates.get("prime_rate", 0.0))

    def test_source_map_contains_all_buckets(self):
        calculator = self.env["gear.batching.quotation.calculator"].sudo()
        rates = calculator.compute_batching_rates(self.vendor_order)
        source_map = rates.get("source_map", {})
        self.assertIn("running", source_map)
        self.assertIn("capex", source_map)
        self.assertIn("dead_cost", source_map)
        self.assertIn("intermediate_values", source_map)
        running_map = source_map.get("running", {})
        self.assertIn("land_investment", running_map)
        dead_map = source_map.get("dead_cost", {})
        self.assertIn("civil_factory_building", dead_map)
        self.assertIn("civil_non_factory_building", dead_map)

    def test_capacity_component_depreciation(self):
        capacity = self.env["gear.plant.capacity.master"].create(
            {
                "name": "Component Driven Plant",
                "capacity_cum_hour": 0.0,
                "component_batching_plant": 20.0,
                "component_cement_silos": 10.0,
                "component_fly_ash_silos": 5.0,
            }
        )
        self.assertEqual(capacity.component_total, 35.0)
        self.assertAlmostEqual(capacity.depreciation_monthly, 35.0 / (10 * 12))
        capacity.write({"component_dg_set": 5.0, "depreciation_years": 5.0})
        self.assertEqual(capacity.component_total, 40.0)
        self.assertAlmostEqual(capacity.depreciation_monthly, 40.0 / (5 * 12))

    def test_master_totals_present(self):
        self.assertGreater(self.running_master.total_monthly, 0.0)
        self.assertAlmostEqual(
            self.running_master.total_monthly,
            sum(
                [
                    self.running_master.power_monthly,
                    self.running_master.dg_monthly,
                    self.running_master.diesel_monthly,
                    self.running_master.admin_monthly,
                    self.running_master.interest_monthly,
                    self.running_master.land_investment,
                ]
            ),
        )
        self.assertGreater(self.capex_master.component_total, 0.0)
        self.assertAlmostEqual(
            self.capex_master.component_total,
            self.capex_master.plant_machinery_capex
            + self.capex_master.furniture_capex
            + self.capex_master.equipment_fittings_capex
            + self.capex_master.computers_peripherals_capex,
        )
        self.assertEqual(
            self.dead_master.construction_total,
            self.dead_master.civil_factory_building + self.dead_master.civil_non_factory_building,
        )

    def test_costing_overview_rollup(self):
        overview = self.env["gear.costing.overview"].create({"name": "Overview"})
        self.assertAlmostEqual(overview.running_power, self.running_master.power_monthly)
        self.assertAlmostEqual(overview.running_dg, self.running_master.dg_monthly)
        self.assertAlmostEqual(overview.running_diesel, self.running_master.diesel_monthly)
        self.assertAlmostEqual(overview.running_admin, self.running_master.admin_monthly)
        self.assertAlmostEqual(overview.running_interest, self.running_master.interest_monthly)
        self.assertAlmostEqual(overview.running_land, self.running_master.land_investment)
        self.assertAlmostEqual(overview.running_total, self.running_master.total_monthly)
        capex_totals = self.env["gear.capex.master"].compute_totals(self.env.company)
        self.assertAlmostEqual(overview.capex_plant_machinery, capex_totals.get("plant_machinery_capex", 0.0))
        self.assertAlmostEqual(overview.capex_furniture, capex_totals.get("furniture_capex", 0.0))
        self.assertAlmostEqual(overview.capex_equipment, capex_totals.get("equipment_fittings_capex", 0.0))
        self.assertAlmostEqual(overview.capex_computers, capex_totals.get("computers_peripherals_capex", 0.0))
        self.assertAlmostEqual(overview.capex_total, capex_totals.get("total_capex", 0.0))
        self.assertAlmostEqual(overview.capex_monthly_depr, capex_totals.get("monthly_depreciation", 0.0))
        dead_totals = self.env["gear.dead.cost.master"].compute_totals(self.env.company)
        self.assertAlmostEqual(overview.dead_factory, dead_totals.get("civil_factory_building", 0.0))
        self.assertAlmostEqual(overview.dead_non_factory, dead_totals.get("civil_non_factory_building", 0.0))
        self.assertAlmostEqual(overview.dead_total, dead_totals.get("dead_total", 0.0))
        self.assertAlmostEqual(
            overview.base_prime_monthly,
            overview.running_total + overview.capex_monthly_depr + overview.dead_total,
        )
        self.assertEqual(
            overview.base_prime_formula,
            "%0.2f + %0.2f + %0.2f"
            % (overview.running_total, overview.capex_monthly_depr, overview.dead_total),
        )
        expected_margin = overview.base_prime_monthly * (overview.margin_percent / 100.0)
        self.assertAlmostEqual(overview.margin_amount, expected_margin)
        self.assertAlmostEqual(overview.final_prime_rate, overview.base_prime_monthly + expected_margin)
        self.assertEqual(
            overview.final_prime_formula,
            "%0.2f + (%0.2f x %s%%)"
            % (overview.base_prime_monthly, overview.base_prime_monthly, overview.margin_percent),
        )
