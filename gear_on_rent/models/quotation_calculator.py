"""Quotation calculator engine for the batching plant landing page.

Branding Patch Stage-5 applied for SP Nexgen Automind Pvt Ltd — Tech Paras
© SP Nexgen Automind Pvt Ltd · www.smarterpeak.com

This engine is scoped to the new "/batching-plant" experience and should not be
invoked by the legacy "/gear-on-rent" estimator. It fetches MGQ tiers, optional
service pricing, material area rates, and design mixes through the ORM so the
output dictionaries can be consumed by the portal, PDF, and SO generation
workflows without adding any UI changes here.
"""

import json
import logging

from odoo import api, models


_logger = logging.getLogger(__name__)


class GearBatchingQuotationCalculator(models.AbstractModel):
    _name = "gear.batching.quotation.calculator"
    _description = "Batching Plant Quotation Calculator"

    def _get_mgq_context(self, order, production_qty=None):
        mgq_candidates = [
            order.mgq_monthly,
            order.x_monthly_mgq,
            order.qty_mgq,
            production_qty,
            order.gear_expected_production_qty,
        ]
        mgq = next((val for val in mgq_candidates if val), 0.0)

        production = production_qty if production_qty is not None else order.gear_expected_production_qty
        production = production or mgq

        if not mgq and production:
            mgq = production

        return mgq, production

    def _safe_divide(self, numerator, denominator):
        denominator = float(denominator or 0.0)
        if not denominator:
            return 0.0
        try:
            return float(numerator or 0.0) / denominator
        except Exception:
            return 0.0

    def _numeric_field(self, record, field_names):
        for fname in field_names:
            if hasattr(record, fname):
                try:
                    val = getattr(record, fname) or 0.0
                    if val:
                        return float(val)
                except Exception:
                    continue
        return 0.0

    def _project_duration_months(self, order):
        if order.gear_project_duration_years:
            try:
                return float(order.gear_project_duration_years) * 12.0
            except (TypeError, ValueError):
                return 0.0
        if order.gear_project_duration_months:
            try:
                return float(order.gear_project_duration_months)
            except (TypeError, ValueError):
                return 0.0
        if order.gear_dead_cost_months:
            try:
                return float(order.gear_dead_cost_months)
            except (TypeError, ValueError):
                return 0.0
        return 0.0

    # --------------------
    # Base rate resolution
    # --------------------
    def _find_rate_tier(self, order, mgq):
        """Resolve the MGQ rate slab. Falls back to the closest lower tier."""

        if order.gear_mgq_rate_id:
            return order.gear_mgq_rate_id

        Rate = self.env["gear.mgq.rate.master"].sudo()

        if not mgq:
            return Rate.browse()

        domain = [
            ("active", "=", True),
            ("service_id", "=", order.gear_service_id.id),
            ("capacity_id", "=", order.gear_capacity_id.id),
            "&",
            "|",
            ("mgq_min", "=", False),
            ("mgq_min", "<=", mgq),
            "|",
            ("mgq_max", "=", False),
            ("mgq_max", ">=", mgq),
        ]
        tier = Rate.search(domain, limit=1, order="mgq_min asc, mgq_max asc, id asc")
        if tier:
            return tier

        # Fallback: pick the highest tier below the requested MGQ so large projects get a rate.
        fallback_domain = [
            ("active", "=", True),
            ("service_id", "=", order.gear_service_id.id),
            ("capacity_id", "=", order.gear_capacity_id.id),
            ("mgq_min", "!=", False),
            ("mgq_min", "<=", mgq),
        ]
        return Rate.search(fallback_domain, limit=1, order="mgq_min desc, id desc")

    def _get_mgq_rates(self, order, mgq):
        tier = self._find_rate_tier(order, mgq)
        return {
            "prime_rate": tier.prime_rate if tier else order.prime_rate,
            "optimize_rate": tier.optimize_rate if tier else order.optimize_rate,
            "after_mgq_rate": tier.after_mgq_rate if tier else order.excess_rate,
            "ngt_rate": tier.ngt_rate if tier else order.ngt_rate,
        }

    def calculate_base_plant_rate(self, order, production_qty=None):
        mgq, production = self._get_mgq_context(order, production_qty)
        rates = self._get_mgq_rates(order, mgq)

        prime_rate = rates.get("prime_rate") or 0.0
        optimize_rate = rates.get("optimize_rate") or 0.0
        after_rate = rates.get("after_mgq_rate") or 0.0

        # MGQ-centric slab billing keeps MGQ as the anchor for prime/optimize/after calculations.
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

    def _iter_optional_services(self, order, mgq):
        """Yield optional services with effective per-CUM charges and context."""

        service_defs = [
            ("transport", order.gear_transport_opt_in, order.gear_transport_per_cum, "per_cum"),
            ("pump", order.gear_pumping_opt_in, order.gear_pump_per_cum, "per_cum"),
            ("manpower", order.gear_manpower_opt_in, order.gear_manpower_per_cum, "per_cum"),
            ("jcb", order.gear_jcb_opt_in, order.gear_jcb_monthly, "per_month"),
            # Keep diesel at the bottom of the optional table for readability.
            ("diesel", order.gear_diesel_opt_in, order.gear_diesel_per_cum, "per_cum"),
        ]

        resolved_services = {}
        enabled_definitions = []
        diesel_component_total = 0.0
        entries = []
        quantity_map = {
            "transport": order.gear_transport_qty,
            "pump": order.gear_pumping_qty,
            "manpower": order.gear_manpower_qty,
            "diesel": order.gear_diesel_qty,
            "jcb": order.gear_jcb_qty,
        }

        for code, enabled, custom_rate, custom_charge in service_defs:
            if not enabled:
                continue
            service = self._resolve_optional_service(order, code)
            resolved_services[code] = service
            enabled_definitions.append((code, custom_rate, custom_charge))
            if code != "diesel" and service:
                diesel_component_total += service.diesel_per_cum or 0.0

        for code, custom_rate, custom_charge in enabled_definitions:
            service = resolved_services.get(code)
            diesel_value = (service.diesel_per_cum if service else 0.0) or 0.0
            charge_type = "per_cum" if code == "diesel" else ((service.charge_type if service else None) or custom_charge)
            quantity = quantity_map.get(code, 0.0) or 0.0
            if code == "transport" and (not quantity or quantity <= 0.0) and mgq:
                try:
                    quantity = round(float(mgq) / 750.0, 2)
                except Exception:
                    quantity = 0.0
            if quantity <= 0.0:
                quantity = 1.0

            if code == "diesel":
                service_rate = service.rate if service else 0.0
                component_total = diesel_component_total
                # Prefer the computed diesel surcharge derived from enabled optional services.
                base_rate = custom_rate or component_total or diesel_value or service_rate or 0.0
            else:
                base_rate = custom_rate or (service.rate if service else 0.0) or 0.0

            amount_per_period = base_rate * quantity

            per_cum = 0.0
            if charge_type == "per_cum":
                per_cum = amount_per_period
            elif charge_type in {"per_month", "fixed"}:
                per_cum = self._safe_divide(amount_per_period, mgq)
            else:
                per_cum = amount_per_period

            # Diesel surcharge is expressed per CUM, so keep it unscaled by quantity for display.
            if code == "diesel":
                diesel_per_cum_value = base_rate
            else:
                diesel_per_cum_value = diesel_value
            entries.append({
                "code": code,
                "rate_value": base_rate,
                "charge_type": charge_type,
                "per_cum": per_cum,
                "diesel_per_cum": diesel_per_cum_value,
                "quantity": quantity,
                "total_amount": amount_per_period,
                "name": service.display_name if service else code,
            })

        for entry in entries:
            yield entry

    def calculate_optional_services(self, order):
        mgq, _production = self._get_mgq_context(order)
        if not any(
            [
                order.gear_transport_opt_in,
                order.gear_pumping_opt_in,
                order.gear_manpower_opt_in,
                order.gear_diesel_opt_in,
                order.gear_jcb_opt_in,
            ]
        ):
            return 0.0
        per_cum_total = 0.0

        for service in self._iter_optional_services(order, mgq):
            per_cum_total += service.get("per_cum", 0.0)

        return per_cum_total

    # --------------------
    # Material costing
    # --------------------
    def _convert_quantity(self, qty, from_uom, to_uom_xmlid):
        if not from_uom:
            return qty
        to_uom = self.env.ref(to_uom_xmlid, raise_if_not_found=False)
        if not to_uom:
            return qty
        try:
            return from_uom._compute_quantity(qty, to_uom)
        except Exception:
            return qty

    def _extract_bom_materials(self, design):
        bom = getattr(design, "bom_id", False)
        if not bom:
            return {}

        totals = {
            "cement_qty": 0.0,
            "agg_10mm_qty": 0.0,
            "agg_20mm_qty": 0.0,
            "admixture_qty": 0.0,
        }

        for line in bom.bom_line_ids:
            product = line.product_id
            descriptor = (product.default_code or product.name or "").lower()
            qty_kg = self._convert_quantity(line.product_qty, line.product_uom_id or product.uom_id, "uom.product_uom_kgm")
            qty_ml = self._convert_quantity(line.product_qty, line.product_uom_id or product.uom_id, "uom.product_uom_litre") * 1000

            if "cement" in descriptor:
                totals["cement_qty"] += qty_kg
            elif "10mm" in descriptor or "10 mm" in descriptor:
                totals["agg_10mm_qty"] += qty_kg
            elif "20mm" in descriptor or "20 mm" in descriptor:
                totals["agg_20mm_qty"] += qty_kg
            elif "admixture" in descriptor or "admix" in descriptor or "chemical" in descriptor:
                totals["admixture_qty"] += qty_ml

        return totals

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

        bom_quantities = self._extract_bom_materials(design)
        cement_qty_kg = bom_quantities.get("cement_qty", design.cement_qty or 0.0)
        agg10_qty_kg = bom_quantities.get("agg_10mm_qty", design.agg_10mm_qty or 0.0)
        agg20_qty_kg = bom_quantities.get("agg_20mm_qty", design.agg_20mm_qty or 0.0)
        admixture_qty_ml = bom_quantities.get("admixture_qty", design.admixture_qty or 0.0)

        cement_cost = (cement_qty_kg / 50.0) * _rate(cement_area, "cement_rate")
        agg10_cost = (agg10_qty_kg / 1000.0) * _rate(agg10_area, "agg_10mm_rate")
        agg20_cost = (agg20_qty_kg / 1000.0) * _rate(agg20_area, "agg_20mm_rate")
        admixture_cost = (admixture_qty_ml / 1000.0) * _rate(admixture_area, "admixture_rate")

        return cement_cost + agg10_cost + agg20_cost + admixture_cost

    # --------------------
    # Base economics
    # --------------------

    def _iter_cost_components(self, order):
        components = self._capex_component_records(order)
        for component in components:
            amount = self._capex_component_amount(component)
            if not amount:
                continue
            yield component, amount

    def _calculate_running_monthly_total(self, order):
        running_fields = [
            "gear_running_monthly_total",
            "gear_running_cost_total",
            "gear_base_running_cost",
            "gear_base_plant_total",
            "running_monthly_total",
            "base_running_cost",
            "x_total_a",
            "gear_total_a",
        ]
        total = self._numeric_field(order, running_fields)
        if total:
            return total

        component_total = 0.0
        for component, amount in self._iter_cost_components(order):
            if getattr(component, "component_type", False) == "base":
                component_total += amount
        return component_total

    def _calculate_margin_per_cum(self, order, mgq, base_prime_per_cum=0.0):
        per_cum_fields = [
            "margin_per_cum",
            "gear_margin_per_cum",
            "x_margin_per_cum",
            "gear_margin_rate",
        ]
        monthly_fields = [
            "margin_monthly",
            "gear_margin_monthly",
            "gear_margin_amount",
            "x_margin_monthly",
        ]

        per_cum = self._numeric_field(order, per_cum_fields)
        if per_cum:
            return per_cum

        monthly = self._numeric_field(order, monthly_fields)
        if monthly:
            return self._safe_divide(monthly, mgq)

        return self._calculate_master_margin_per_cum(order, mgq, base_prime_per_cum)

    def _calculate_master_margin_per_cum(self, order, mgq, base_prime_per_cum=0.0):
        """Fallback to the company costing overview when no order-specific margin is set."""

        overview = (
            self.env["gear.costing.overview"]
            .sudo()
            .search([("company_id", "=", order.company_id.id)], order="id desc", limit=1)
        )
        if not overview:
            return 0.0

        base_prime_monthly = overview.base_prime_monthly or (
            (overview.running_total or 0.0)
            + (overview.capex_monthly_depr or 0.0)
            + (overview.dead_total or 0.0)
        )

        effective_base_prime = base_prime_per_cum
        if not effective_base_prime:
            effective_base_prime = self._safe_divide(base_prime_monthly, mgq)

        if not effective_base_prime:
            return 0.0

        margin_percent = overview.margin_percent
        if not margin_percent:
            margin_percent = self._safe_divide(overview.margin_amount, base_prime_monthly) * 100.0 if base_prime_monthly else 0.0

        return effective_base_prime * (margin_percent or 0.0) / 100.0

    def _calculate_plant_capex_total(self, order):
        capex_fields = [
            "gear_plant_capex_total",
            "gear_capex_total",
            "gear_capex_amount",
            "gear_pm_capex_amount",
            "plant_capex_total",
            "x_plant_capex_total",
            "x_capex_total",
        ]
        capex_total = self._numeric_field(order, capex_fields)
        if capex_total:
            return capex_total

        total = 0.0
        for component, amount in self._iter_cost_components(order):
            classification = self._capex_classification(component)
            is_dead_flag = getattr(component, "include_in_dead", False) or getattr(component, "is_dead_cost", False)
            if classification == "civil" or is_dead_flag:
                continue
            total += amount
        return total

    def _calculate_dead_capex_total(self, order):
        dead_fields = [
            "gear_dead_cost_total",
            "gear_dead_cost_amount",
            "dead_cost_total",
            "x_dead_cost_amount",
        ]
        dead_total = self._numeric_field(order, dead_fields)
        if dead_total:
            return dead_total

        total = 0.0
        for component, amount in self._iter_cost_components(order):
            classification = self._capex_classification(component)
            include_in_dead = getattr(component, "include_in_dead", False) or getattr(component, "is_dead_cost", False)
            if classification == "civil" or include_in_dead or getattr(component, "component_type", False) == "dead_cost":
                total += amount
        return total

    def _should_include_dead_cost(self, order):
        civil_scope = (order.gear_civil_scope or "").lower()
        # Vendor scope should include dead/civil amortization; customer scope excludes.
        if civil_scope == "vendor":
            return True
        if civil_scope == "customer":
            return False
        return False

    # --------------------
    # CAPEX / dead-costing
    # --------------------
    def _capex_component_records(self, order):
        """Return a recordset of CAPEX components captured on the quotation.

        This intentionally probes multiple potential field names so Studio-driven
        installations can surface selected cost components without schema changes
        to this module.
        """

        candidate_fields = [
            "gear_cost_component_ids",
            "gear_capex_component_ids",
            "gear_dead_cost_component_ids",
            "x_capex_component_ids",
            "x_dead_cost_component_ids",
        ]

        for fname in candidate_fields:
            components = getattr(order, fname, False)
            if components:
                return components

        override_components = self.env.context.get("override_capex_components")
        if override_components:
            try:
                ids = [comp.id for comp in override_components if hasattr(comp, "id")]
                return self.env["gear.cost.component.master"].browse(ids)
            except Exception:
                return self.env["gear.cost.component.master"].browse()

        return self.env["gear.cost.component.master"].browse()

    def _capex_component_amount(self, component):
        amount_fields = [
            "amount",
            "cost",
            "value",
            "rate",
            "price",
            "total",
        ]
        for field in amount_fields:
            if field in component._fields:
                try:
                    val = getattr(component, field) or 0.0
                    return float(val)
                except Exception:
                    continue
        return 0.0

    def _capex_classification(self, component):
        descriptor = (component.name or "").lower()
        civil_keywords = ["civil", "foundation", "shed", "road", "drain", "pcc", "structure"]
        for word in civil_keywords:
            if word in descriptor:
                return "civil"
        utility_keywords = ["dg", "utility", "power", "compressor", "electrical"]
        for word in utility_keywords:
            if word in descriptor:
                return "utility"
        safety_keywords = ["safety", "fire", "ppe", "guard"]
        for word in safety_keywords:
            if word in descriptor:
                return "safety"
        admin_keywords = ["admin", "office", "it", "furniture"]
        for word in admin_keywords:
            if word in descriptor:
                return "admin"
        return "infra"

    def calculate_capex_breakdown(self, order):
        mgq, _production = self._get_mgq_context(order)
        if not order.gear_dead_cost_amount or not mgq:
            return 0.0

        # Civil scope "customer" maps to client-side responsibility; exclude amortization.
        if order.gear_civil_scope and order.gear_civil_scope == "customer":
            return 0.0

        duration_months = 0.0
        if order.gear_project_duration_years:
            try:
                duration_months = float(order.gear_project_duration_years) * 12.0
            except (TypeError, ValueError):
                duration_months = 0.0

        if not duration_months:
            duration_months = order.gear_dead_cost_months or order.gear_project_duration_months or 0.0

        if not duration_months:
            duration_months = order.gear_dead_cost_months or order.gear_project_duration_months or 0.0

        components = []
        component_records = self._capex_component_records(order)
        for component in component_records:
            amount = self._capex_component_amount(component)
            if not amount:
                continue
            components.append(
                {
                    "component": component.name,
                    "amount": amount,
                    "classification": self._capex_classification(component),
                }
            )

        total_amount = sum(comp["amount"] for comp in components)
        if not components and order.gear_dead_cost_amount:
            total_amount = order.gear_dead_cost_amount
            components = [
                {
                    "component": "Total Investment",
                    "amount": order.gear_dead_cost_amount,
                    "classification": "infra",
                }
            ]

        civil_scope = order.gear_civil_scope or ""
        if civil_scope == "customer":
            filtered_components = [c for c in components if c.get("classification") != "civil"]
        else:
            filtered_components = list(components)

        filtered_total = sum(comp["amount"] for comp in filtered_components)

        total_components = self._calculate_dead_capex_total(order) or order.gear_dead_cost_amount
        return self._safe_divide(total_components, duration_months * mgq)

    def calculate_dead_cost(self, order, production_qty=None):
        """Return amortized dead-cost per CUM for vendor-scope engagements."""

        if not order:
            return 0.0

        if not self._should_include_dead_cost(order):
            return 0.0

        mgq, production = self._get_mgq_context(order, production_qty)
        anchor_qty = mgq or production or 0.0
        if not anchor_qty:
            return 0.0

        months = self._project_duration_months(order)
        if not months:
            return 0.0

        monthly_total = self._numeric_field(
            order,
            [
                "gear_dead_cost_monthly_total",
                "dead_cost_monthly_total",
                "gear_dead_cost_monthly",
                "dead_cost_monthly",
            ],
        )

        if not monthly_total:
            total_capex = self._calculate_dead_capex_total(order)
            monthly_total = self._safe_divide(total_capex, months)

        return self._safe_divide(monthly_total, anchor_qty)

    def compute_batching_rates(self, order, production_qty=None):
        mgq, production = self._get_mgq_context(order, production_qty)
        project_months = self._project_duration_months(order)

        cost_components = order.gear_cost_component_ids

        running_totals = (
            self.env["gear.running.cost.master"].sudo().compute_totals(order.company_id)
            if hasattr(self.env, "registry")
            else {}
        )
        if running_totals:
            # Exclude DG cost from running computations per latest requirement.
            running_totals["dg_monthly"] = 0.0
            if order.gear_plant_running == "power":
                running_totals["diesel_monthly"] = 0.0
            elif order.gear_plant_running == "diesel":
                running_totals["power_monthly"] = 0.0
        if running_totals and order.gear_service_type != "turnkey":
            running_totals["land_investment"] = 0.0
        if running_totals:
            running_totals["running_total"] = sum(
                [
                    running_totals.get("power_monthly", 0.0) or 0.0,
                    running_totals.get("dg_monthly", 0.0) or 0.0,
                    running_totals.get("diesel_monthly", 0.0) or 0.0,
                    running_totals.get("admin_monthly", 0.0) or 0.0,
                    running_totals.get("interest_monthly", 0.0) or 0.0,
                    running_totals.get("land_investment", 0.0) or 0.0,
                ]
            )
        running_monthly_master = running_totals.get("running_total", 0.0)
        running_monthly_component = cost_components.get_running_cost()
        running_fallback = self._calculate_running_monthly_total(order)
        running_monthly = running_monthly_master or running_monthly_component or running_fallback
        if running_monthly_master:
            running_source = "master"
        elif running_monthly_component:
            running_source = "cost_component"
        else:
            running_source = "fallback"

        capacity_rec = order.gear_capacity_id
        capacity_total = capacity_rec.component_total if capacity_rec else 0.0

        capex_totals = (
            self.env["gear.capex.master"].sudo().compute_totals(order.company_id)
            if hasattr(self.env, "registry")
            else {}
        )
        # Build CAPEX totals: plant machinery comes from capacity if selected, others from master.
        plant_machinery_capex = capacity_total if capacity_rec else capex_totals.get("plant_machinery_capex", 0.0)
        furniture_capex = capex_totals.get("furniture_capex", 0.0)
        equipment_capex = capex_totals.get("equipment_fittings_capex", 0.0)
        computers_capex = capex_totals.get("computers_peripherals_capex", 0.0)
        capex_total = plant_machinery_capex + furniture_capex + equipment_capex + computers_capex
        capex_totals.update(
            {
                "plant_machinery_capex": plant_machinery_capex,
                "furniture_capex": furniture_capex,
                "equipment_fittings_capex": equipment_capex,
                "computers_peripherals_capex": computers_capex,
                "total_capex": capex_total,
            }
        )
        if capacity_rec:
            # Combine capacity-specific depreciation with master assets.
            other_total = capex_total - plant_machinery_capex
            other_useful_months = (capex_totals.get("useful_life_years") or 0.0) * 12.0
            other_depr = self._safe_divide(other_total, other_useful_months) if other_useful_months else 0.0
            capacity_depr = capacity_rec.depreciation_monthly or self._safe_divide(
                plant_machinery_capex, (capacity_rec.depreciation_years or 0.0) * 12.0
            )
            capex_totals["monthly_depreciation"] = capacity_depr + other_depr
        depreciation_component = cost_components.get_monthly_depreciation(project_months)
        depreciation_monthly = 0.0
        depreciation_source = "fallback"
        master_monthly_depr = capex_totals.get("monthly_depreciation", 0.0)
        if capacity_rec and master_monthly_depr:
            depreciation_monthly = master_monthly_depr
            depreciation_source = "capacity"
        elif master_monthly_depr:
            depreciation_monthly = master_monthly_depr
            depreciation_source = "master"
        elif capex_total and capex_totals.get("useful_life_years"):
            useful_months = (capex_totals.get("useful_life_years") or 0.0) * 12.0
            if useful_months:
                depreciation_monthly = self._safe_divide(capex_total, useful_months)
                depreciation_source = "master"
        elif capex_total and project_months:
            depreciation_monthly = self._safe_divide(capex_total, project_months)
            depreciation_source = "master"
        elif depreciation_component:
            depreciation_monthly = depreciation_component
            depreciation_source = "cost_component"
        else:
            depreciation_monthly = self._safe_divide(self._calculate_plant_capex_total(order), project_months)
        depr_per_cum = self._safe_divide(depreciation_monthly, mgq)

        dead_totals = (
            self.env["gear.dead.cost.master"].sudo().compute_totals(order.company_id)
            if hasattr(self.env, "registry")
            else {}
        )
        dead_per_cum = 0.0
        dead_cost_total = 0.0
        dead_source = "excluded"
        if self._should_include_dead_cost(order):
            dead_cost_total = dead_totals.get("dead_total", 0.0)
            dead_source = "master" if dead_cost_total else "calculator"
            if dead_cost_total and project_months:
                dead_monthly = self._safe_divide(dead_cost_total, project_months)
                dead_per_cum = self._safe_divide(dead_monthly, mgq)
            else:
                dead_cost_total = cost_components.get_dead_cost()
                if dead_cost_total:
                    dead_source = "cost_component"
                    dead_per_cum = self._safe_divide(dead_cost_total, mgq)
                else:
                    dead_per_cum = self.calculate_dead_cost(order, production_qty)
        else:
            dead_per_cum = 0.0

        # Interest: derive from Component Total + Dead Cost Total using master-set percentage when available.
        interest_percent = running_totals.get("interest_percent", 0.0) or 0.0
        interest_monthly = running_totals.get("interest_monthly", 0.0) or 0.0
        interest_source = running_source
        if interest_percent:
            interest_base = (capex_totals.get("total_capex", 0.0) or 0.0) + (dead_cost_total or 0.0)
            interest_monthly = (interest_base * interest_percent / 100.0) 
            interest_source = "percent"
            running_totals["interest_monthly"] = interest_monthly

        # Recompose running monthly with the latest interest value.
        running_monthly = sum(
            [
                running_totals.get("power_monthly", 0.0) or 0.0,
                running_totals.get("dg_monthly", 0.0) or 0.0,
                running_totals.get("diesel_monthly", 0.0) or 0.0,
                running_totals.get("admin_monthly", 0.0) or 0.0,
                running_totals.get("interest_monthly", 0.0) or 0.0,
                running_totals.get("land_investment", 0.0) or 0.0,
            ]
        )
        running_totals["running_total"] = running_monthly
        running_per_cum = self._safe_divide(running_monthly, mgq)
        interest_per_cum = self._safe_divide(interest_monthly, mgq)

        base_prime_rate = running_per_cum + depr_per_cum + dead_per_cum
        raw_prime_rate = base_prime_rate
        prime_rate = base_prime_rate

        margin_per_cum = self._calculate_margin_per_cum(order, mgq, base_prime_rate)

        material_per_cum = 0.0
        material_source = "not_applicable"
        if order.x_inventory_mode == "with_inventory":
            component_material = cost_components.get_material_cost_per_cum(
                grade=order.gear_design_mix_id.grade if order.gear_design_mix_id else None,
                area=order.gear_material_area_id.area if hasattr(order.gear_material_area_id, "area") else None,
            )
            if component_material:
                material_source = "cost_component"
                material_per_cum = component_material
            else:
                material_source = "calculator"
                material_per_cum = self.calculate_material_cost(order)

        optional_services_breakdown = list(self._iter_optional_services(order, mgq))
        optional_per_cum = cost_components.get_optional_cost_per_cum(order)

        rates = self._get_mgq_rates(order, mgq)
        mgq_prime_rate = rates.get("prime_rate") or 0.0
        optimize_rate = rates.get("optimize_rate") or prime_rate
        after_mgq_rate = rates.get("after_mgq_rate") or prime_rate
        ngt_rate = 0.0  # NGT not used

        prime_rate_source = "cost_engine"
        if prime_rate <= 0.0 and mgq_prime_rate:
            prime_rate = mgq_prime_rate
            prime_rate_source = "mgq_rate"

        if prime_rate_source == "mgq_rate":
            prime_with_margin = prime_rate
        else:
            prime_with_margin = prime_rate + margin_per_cum

        final_prime_rate = prime_with_margin + material_per_cum + optional_per_cum

        # Diesel adjustments: reuse optional breakdown to derive optimize/after rates.
        diesel_optional_per_cum = sum(
            (entry.get("per_cum") or 0.0)
            for entry in optional_services_breakdown
            if entry.get("code") == "diesel"
        )
        diesel_running_per_cum = self._safe_divide(running_totals.get("diesel_monthly", 0.0), mgq)

        # Optimize rate derived from Final Prime less diesel surcharge per CUM plus diesel running per CUM.
        derived_optimize_rate = final_prime_rate
        if diesel_optional_per_cum:
            derived_optimize_rate = final_prime_rate - (diesel_optional_per_cum + diesel_running_per_cum)
            if derived_optimize_rate < 0.0:
                derived_optimize_rate = 0.0
        optimize_rate = derived_optimize_rate
        final_optimize_rate = derived_optimize_rate

        # After MGQ rate derived from diesel optional + diesel running + margin per CUM.
        after_mgq_rate = diesel_optional_per_cum + diesel_running_per_cum + margin_per_cum
        final_after_mgq_rate = after_mgq_rate

        display_plant_machinery = capacity_total or capex_totals.get("plant_machinery_capex", 0.0)
        display_total_capex = capex_totals.get("total_capex", capex_total) or capacity_total

        source_map = {
            "running": {
                "power": running_totals.get("power_monthly", 0.0),
                "dg": running_totals.get("dg_monthly", 0.0),
                "diesel": running_totals.get("diesel_monthly", 0.0),
                "admin": running_totals.get("admin_monthly", 0.0),
                "interest": running_totals.get("interest_monthly", 0.0),
                "land_investment": running_totals.get("land_investment", 0.0),
                "running_total": running_totals.get("running_total", running_monthly),
            },
            "capex": {
                "plant_machinery": display_plant_machinery,
                "furniture": capex_totals.get("furniture_capex", 0.0),
                "equipment_fittings": capex_totals.get("equipment_fittings_capex", 0.0),
                "computers_peripherals": capex_totals.get("computers_peripherals_capex", 0.0),
                "total_capex": display_total_capex,
                "monthly_depr": depreciation_monthly,
            },
            "dead_cost": {
                "civil_factory_building": dead_totals.get("civil_factory_building", 0.0),
                "civil_non_factory_building": dead_totals.get("civil_non_factory_building", 0.0),
                "dead_total": dead_totals.get("dead_total", dead_cost_total),
            },
            "intermediate_values": {
                "duration_months": project_months,
                "MGQ": mgq,
            },
        }

        prime_rate_log = {
            "order": order.display_name or order.name or order.id,
            "mgq": mgq,
            "production_qty": production,
            "project_months": project_months,
            "mgq_prime_rate": mgq_prime_rate,
            "raw_prime_rate": raw_prime_rate,
            "prime_rate_source": prime_rate_source,
            "components": {
                "running": {
                    "monthly_total": running_monthly,
                    "per_cum": running_per_cum,
                    "source": running_source,
                },
                "depreciation": {
                    "monthly_total": depreciation_monthly,
                    "per_cum": depr_per_cum,
                    "project_months": project_months,
                    "source": depreciation_source,
                },
                "interest": {
                    "monthly_total": interest_monthly,
                    "per_cum": interest_per_cum,
                    "source": interest_source,
                },
                "dead_cost": {
                    "total": dead_cost_total,
                    "per_cum": dead_per_cum,
                    "source": dead_source,
                },
                "margin": {"per_cum": margin_per_cum},
                "material": {
                    "per_cum": material_per_cum,
                    "source": material_source,
                    "inventory_mode": order.x_inventory_mode,
                },
                "optional": {
                    "per_cum": optional_per_cum,
                    "services": optional_services_breakdown,
                },
            },
            "prime_rate": prime_rate,
            "final_prime_rate": final_prime_rate,
            "final_optimize_rate": final_optimize_rate,
            "final_after_mgq_rate": final_after_mgq_rate,
            "optimize_rate": optimize_rate,
            "after_mgq_rate": after_mgq_rate,
            "ngt_rate": ngt_rate,
            "optional_per_cum": optional_per_cum,
            "source_map": source_map,
        }
        try:
            _logger.info(
                "Prime rate computation trace for order %s\n%s",
                order.display_name or order.name or order.id,
                json.dumps(prime_rate_log, indent=2),
            )
        except Exception:
            _logger.info(
                "Prime rate computation trace for order %s (serialization skipped)",
                order.display_name or order.name or order.id,
            )

        return {
            "mgq": mgq,
            "production_qty": production,
            "running_per_cum": running_per_cum,
            "depr_per_cum": depr_per_cum,
            "dead_per_cum": dead_per_cum,
            "margin_per_cum": margin_per_cum,
            "material_per_cum": material_per_cum,
            "optional_per_cum": optional_per_cum,
            "prime_rate": prime_rate,
            "optimize_rate": optimize_rate,
            "after_mgq_rate": after_mgq_rate,
            "ngt_rate": ngt_rate,
            "final_prime_rate": final_prime_rate,
            "final_optimize_rate": final_optimize_rate,
            "final_after_mgq_rate": final_after_mgq_rate,
            "prime_rate_log": prime_rate_log,
            "source_map": source_map,
        }

    @api.model
    def generate_final_rates(self, order, production_qty=None):
        if not order:
            return {}

        rate_map = self.compute_batching_rates(order, production_qty)
        mgq = rate_map.get("mgq")
        production = rate_map.get("production_qty")

        if mgq and production and production < mgq:
            prime_bill = production * rate_map.get("prime_rate", 0.0)
            optimize_bill = (mgq - production) * rate_map.get("optimize_rate", 0.0)
            after_bill = 0.0
        elif mgq and production and production > mgq:
            prime_bill = mgq * rate_map.get("prime_rate", 0.0)
            optimize_bill = 0.0
            after_bill = (production - mgq) * rate_map.get("after_mgq_rate", 0.0)
        else:
            prime_bill = (production or mgq) * rate_map.get("prime_rate", 0.0)
            optimize_bill = 0.0
            after_bill = 0.0

        denominator = production or mgq or 1.0
        base_rate_per_cum = (prime_bill + optimize_bill + after_bill) / denominator

        optional_breakdown = list(self._iter_optional_services(order, mgq))
        rate_map.update(
            {
                "prime_bill": prime_bill,
                "optimize_bill": optimize_bill,
                "after_mgq_bill": after_bill,
                "base_rate_per_cum": base_rate_per_cum,
                "total_rate_per_cum": rate_map.get("final_prime_rate"),
                "material_cost": rate_map.get("material_per_cum", 0.0),
                "optional_cost": rate_map.get("optional_per_cum", 0.0),
                "dead_cost": rate_map.get("dead_per_cum", 0.0),
                "full_rate_breakdown": {
                    "inventory_mode": order.x_inventory_mode,
                    "base_rate_per_cum": base_rate_per_cum,
                    "prime_rate": rate_map.get("prime_rate"),
                    "optimize_rate": rate_map.get("optimize_rate"),
                    "after_mgq_rate": rate_map.get("after_mgq_rate"),
                    "material_cost": rate_map.get("material_per_cum", 0.0),
                    "optional_cost": rate_map.get("optional_per_cum", 0.0),
                    "dead_cost": rate_map.get("dead_per_cum", 0.0),
                    "running_per_cum": rate_map.get("running_per_cum", 0.0),
                    "depr_per_cum": rate_map.get("depr_per_cum", 0.0),
                    "margin_per_cum": rate_map.get("margin_per_cum", 0.0),
                    "optional_services": optional_breakdown,
                    "mgq": mgq,
                    "production_qty": production,
                },
            }
        )

        if order.x_inventory_mode == "with_inventory":
            rate_map.update(
                {
                    "grade": order.gear_design_mix_id.grade if order.gear_design_mix_id else False,
                    "total_per_cum": rate_map.get("final_prime_rate"),
                }
            )

        return rate_map
