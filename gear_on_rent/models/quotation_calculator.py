"""Quotation calculator engine for the batching plant landing page.

Branding Patch Stage-5 applied for SP Nexgen Automind Pvt Ltd — Tech Paras
© SP Nexgen Automind Pvt Ltd · www.smarterpeak.com

This engine is scoped to the new "/batching-plant" experience and should not be
invoked by the legacy "/gear-on-rent" estimator. It fetches MGQ tiers, optional
service pricing, material area rates, and design mixes through the ORM so the
output dictionaries can be consumed by the portal, PDF, and SO generation
workflows without adding any UI changes here.
"""

from odoo import api, models


class GearBatchingQuotationCalculator(models.AbstractModel):
    _name = "gear.batching.quotation.calculator"
    _description = "Batching Plant Quotation Calculator"

    def _get_mgq_context(self, order, production_qty=None):
        mgq = order.mgq_monthly or order.x_monthly_mgq or 0.0
        production = production_qty if production_qty is not None else order.gear_expected_production_qty
        production = production or mgq
        return mgq, production

    def _get_mgq_rates(self, order):
        rate = order.gear_mgq_rate_id
        return {
            "prime_rate": rate.prime_rate if rate else order.prime_rate,
            "optimize_rate": rate.optimize_rate if rate else order.optimize_rate,
            "after_mgq_rate": rate.after_mgq_rate if rate else order.excess_rate,
        }

    def calculate_base_plant_rate(self, order, production_qty=None):
        mgq, production = self._get_mgq_context(order, production_qty)
        rates = self._get_mgq_rates(order)

        prime_rate = rates.get("prime_rate") or 0.0
        optimize_rate = rates.get("optimize_rate") or 0.0
        after_rate = rates.get("after_mgq_rate") or 0.0

        if mgq and production < mgq:
            prime_bill = production * prime_rate
            optimize_bill = (mgq - production) * optimize_rate
            after_bill = 0.0
        elif mgq and production > mgq:
            prime_bill = mgq * prime_rate
            optimize_bill = 0.0
            after_bill = (production - mgq) * after_rate
        else:
            prime_bill = production * prime_rate
            optimize_bill = 0.0
            after_bill = 0.0

        denominator = production or mgq or 1.0
        base_per_cum = (prime_bill + optimize_bill + after_bill) / denominator

        return {
            "mgq": mgq,
            "production_qty": production,
            "prime_rate": prime_rate,
            "optimize_rate": optimize_rate,
            "after_mgq_rate": after_rate,
            "prime_bill": prime_bill,
            "optimize_bill": optimize_bill,
            "after_mgq_bill": after_bill,
            "base_rate_per_cum": base_per_cum,
        }

    def _resolve_optional_service(self, order, code):
        if not code:
            return self.env["gear.optional.service.master"].browse()

        services = order.gear_optional_service_ids.filtered(lambda s: s.code == code)
        if services:
            return services[:1]
        return self.env["gear.optional.service.master"].search([("code", "=", code)], limit=1)

    def calculate_optional_services(self, order):
        mgq, _production = self._get_mgq_context(order)
        per_cum_total = 0.0

        def add_optional(code, enabled):
            nonlocal per_cum_total
            if not enabled:
                return
            service = self._resolve_optional_service(order, code)
            if not service:
                return
            if service.charge_type == "per_cum":
                per_cum_total += service.rate or 0.0
            elif service.charge_type == "per_month" and mgq:
                per_cum_total += (service.rate or 0.0) / mgq
            elif service.charge_type == "fixed" and mgq:
                per_cum_total += (service.rate or 0.0) / mgq

        add_optional("transport", order.gear_transport_opt_in)
        add_optional("pump", order.gear_pumping_opt_in)
        add_optional("manpower", order.gear_manpower_opt_in)
        add_optional("diesel", order.gear_diesel_opt_in)
        add_optional("jcb", order.gear_jcb_opt_in)

        return per_cum_total

    def calculate_material_cost(self, order):
        override_design_id = self.env.context.get("override_design_mix_id")
        override_material_area_id = self.env.context.get("override_material_area_id")

        design = self.env["gear.design.mix.master"].browse(override_design_id) if override_design_id else order.gear_design_mix_id
        if not design:
            return 0.0

        def _rate(area, field_name):
            return getattr(area, field_name, 0.0) if area else 0.0

        material_area_override = self.env["gear.material.area.master"].browse(override_material_area_id) if override_material_area_id else None

        cement_area = order.gear_cement_area_id or material_area_override or order.gear_material_area_id
        agg10_area = order.gear_agg_10mm_area_id or material_area_override or order.gear_material_area_id
        agg20_area = order.gear_agg_20mm_area_id or material_area_override or order.gear_material_area_id
        admixture_area = order.gear_admixture_area_id or material_area_override or order.gear_material_area_id

        cement_cost = (design.cement_qty / 50.0) * _rate(cement_area, "cement_rate")
        agg10_cost = (design.agg_10mm_qty / 1000.0) * _rate(agg10_area, "agg_10mm_rate")
        agg20_cost = (design.agg_20mm_qty / 1000.0) * _rate(agg20_area, "agg_20mm_rate")
        admixture_cost = (design.admixture_qty / 1000.0) * _rate(admixture_area, "admixture_rate")

        return cement_cost + agg10_cost + agg20_cost + admixture_cost

    def calculate_dead_cost(self, order):
        mgq, _production = self._get_mgq_context(order)
        if (
            order.gear_service_type != "turnkey"
            or order.gear_civil_scope != "vendor"
            or not order.gear_dead_cost_amount
            or not mgq
        ):
            return 0.0

        duration_months = order.gear_dead_cost_months or order.gear_project_duration_months
        if not duration_months and order.gear_project_duration_years:
            try:
                duration_months = int(order.gear_project_duration_years) * 12
            except (TypeError, ValueError):
                duration_months = 0

        if not duration_months:
            return 0.0

        monthly_amortization = order.gear_dead_cost_amount / duration_months
        return monthly_amortization / mgq if mgq else 0.0

    @api.model
    def generate_final_rates(self, order, production_qty=None):
        if not order:
            return {}

        base = self.calculate_base_plant_rate(order, production_qty)
        optional_cost = self.calculate_optional_services(order)
        dead_cost = self.calculate_dead_cost(order)

        if order.x_inventory_mode == "with_inventory":
            material_cost = self.calculate_material_cost(order)
            return {
                "grade": order.gear_design_mix_id.grade if order.gear_design_mix_id else False,
                "base_plant_rate": base.get("base_rate_per_cum", 0.0),
                "material_cost": material_cost,
                "optional_cost": optional_cost,
                "dead_cost": dead_cost,
                "total_per_cum": base.get("base_rate_per_cum", 0.0) + material_cost + optional_cost + dead_cost,
            }

        return {
            "prime_rate": base.get("prime_rate", 0.0),
            "optimize_rate": base.get("optimize_rate", 0.0),
            "after_mgq_rate": base.get("after_mgq_rate", 0.0),
            "optional_cost": optional_cost,
            "dead_cost": dead_cost,
            "final_prime_rate": base.get("prime_rate", 0.0) + optional_cost + dead_cost,
            "final_optimize_rate": base.get("optimize_rate", 0.0) + optional_cost + dead_cost,
            "final_after_mgq_rate": base.get("after_mgq_rate", 0.0) + optional_cost + dead_cost,
        }
