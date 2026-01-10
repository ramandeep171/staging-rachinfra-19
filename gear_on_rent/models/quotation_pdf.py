"""PDF and chart planning helpers for batching-plant quotations.

Branding Patch Stage-5 applied for SP Nexgen Automind Pvt Ltd — Tech Paras
© SP Nexgen Automind Pvt Ltd · www.smarterpeak.com

This helper is scoped to the new "/batching-plant" landing page and consumes the
output of the quotation calculator to prepare chart images and a skeleton PDF
context. It does not generate or style the final PDF; it only prepares data and
image assets for downstream QWeb rendering.
"""

import base64
import logging
import math
import tempfile
from types import ModuleType
from typing import Dict, Iterable, List, Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - optional pillow fallback
    Image = ImageDraw = ImageFont = None

from odoo import api, models

_logger = logging.getLogger(__name__)


class GearBatchingQuotationPdf(models.AbstractModel):
    _name = "gear.batching.quotation.pdf"
    _description = "Batching Plant Quotation PDF Helper"

    _COLOR_MAP = {
        "base": "#2E86AB",
        "material": "#F18F01",
        "optional": "#A23B72",
        "dead_cost": "#6A994E",
        "penalty": "#C73E1D",
        "margin": "#BC4B51",
    }
    _CAPEX_COMPONENTS = [
        ("foundations", "Foundations & PCC"),
        ("structures", "Structure & Sheds"),
        ("electrical", "Electrical & Panels"),
        ("water_supply", "Water Supply & Plumbing"),
        ("dg_bays", "DG/Compressor Bays"),
        ("roads", "Roads & Drainage"),
    ]

    def _calculator(self):
        return self.env["gear.batching.quotation.calculator"]

    # --------------------
    # Data preparation
    # --------------------
    def _build_cost_breakdown(self, order, production_qty=None):
        calculator = self._calculator()
        final_rates = calculator.generate_final_rates(order, production_qty)

        return {
            "base": (final_rates.get("running_per_cum", 0.0) + final_rates.get("depr_per_cum", 0.0)),
            "material": final_rates.get("material_per_cum", 0.0),
            "optional": final_rates.get("optional_per_cum", 0.0),
            "dead_cost": final_rates.get("dead_per_cum", 0.0),
            "margin": final_rates.get("margin_per_cum", 0.0),
        }

    def _build_mgq_scenarios(self, order):
        calculator = self._calculator()
        mgq, _production = calculator._get_mgq_context(order)
        if not mgq:
            return []

        below_qty = max(mgq * 0.83, mgq - 500)
        above_qty = mgq * 1.4
        scenario_qty = [
            ("below", below_qty),
            ("at", mgq),
            ("above", above_qty),
        ]

        scenarios = []
        for code, qty in scenario_qty:
            base = calculator.generate_final_rates(order, qty)
            scenarios.append(
                {
                    "code": code,
                    "label": "Below MGQ" if code == "below" else ("At MGQ" if code == "at" else "Above MGQ"),
                    "qty": qty,
                    "prime_bill": base.get("prime_bill", 0.0),
                    "optimize_bill": base.get("optimize_bill", 0.0),
                    "after_bill": base.get("after_mgq_bill", 0.0),
                }
            )
        return scenarios

    def _build_grade_comparison(self, order):
        calculator = self._calculator()
        final_rates = calculator.generate_final_rates(order)
        optional_cost = final_rates.get("optional_per_cum", calculator.calculate_optional_services(order))
        dead_cost = final_rates.get("dead_per_cum", calculator.calculate_dead_cost(order))
        material_area = order.gear_material_area_id
        base_rate = final_rates.get("base_plant_rate") or calculator.calculate_base_plant_rate(order).get("base_rate_per_cum", 0.0)

        grade_rows = []
        design_mixes = self.env["gear.design.mix.master"].search([("active", "=", True)], order="grade")
        for design in design_mixes:
            material_cost = calculator.calculate_material_cost(
                order.with_context(
                    override_design_mix_id=design.id,
                    override_material_area_id=material_area.id if material_area else False,
                )
            )
            total = base_rate + material_cost + optional_cost + dead_cost
            grade_rows.append(
                {
                    "grade": design.grade,
                    "base": base_rate,
                    "material": material_cost,
                    "optional": optional_cost,
                    "dead_cost": dead_cost,
                    "total": total,
                }
            )
        return grade_rows

    def _build_capex_breakdown(self, order, final_rates):
        scope = (order.gear_civil_scope or "").lower()
        service_type = (order.gear_service_type or "").lower()
        # Vendor scope should include CAPEX; customer scope skips unless turnkey.
        if scope != "vendor" and service_type != "turnkey":
            return {}

        per_cum = final_rates.get("dead_cost", 0.0) or 0.0
        calculator = self._calculator()
        total_amount = (
            calculator._calculate_dead_capex_total(order)
            if hasattr(calculator, "_calculate_dead_capex_total")
            else 0.0
        )
        total_amount = total_amount or order.gear_dead_cost_amount or 0.0
        component_records = calculator._capex_component_records(order)
        capex_items = []
        allowed_types = {"capex", "dead_cost"}
        for component in component_records:
            component_type = getattr(component, "component_type", False)
            if component_type and component_type not in allowed_types:
                continue

            amount = calculator._capex_component_amount(component)
            label = (
                getattr(component, "display_name", False)
                or getattr(component, "name", False)
                or getattr(component, "code", False)
            )
            capex_items.append(
                {
                    "code": getattr(component, "code", False) or component.id,
                    "label": label or "Component",
                    "amount": amount if amount not in (None, False) else False,
                }
            )

        if not capex_items:
            capex_items = [
                {"code": code, "label": label, "amount": False}
                for code, label in self._CAPEX_COMPONENTS
            ]

        computed_total = sum(item.get("amount") or 0.0 for item in capex_items)
        if computed_total:
            total_amount = computed_total

        breakdown = {
            "items": capex_items,
            "total_amount": total_amount,
            "dead_cost_per_cum": per_cum,
        }
        if not total_amount and not per_cum:
            breakdown["note"] = (
                "Vendor scope CAPEX will be finalized after the detailed site survey. "
                "The listed civil & infra components are included in the turnkey scope."
            )
        return breakdown

    def _resolve_production_expectation(self, order, base_rates, final_rates):
        """Return the most relevant production expectation value."""

        candidates = [
            getattr(order, "gear_expected_production_qty", False),
            getattr(order, "gear_project_quantity", False),
            getattr(order, "production_qty", False),
            final_rates.get("production_qty"),
            base_rates.get("production_qty"),
        ]
        for value in candidates:
            try:
                numeric = float(value or 0.0)
            except (TypeError, ValueError):
                continue
            if numeric:
                return numeric
        return 0.0

    def _material_breakdown(self, order):
        calculator = self._calculator()
        if order.x_inventory_mode != "with_inventory":
            return {}

        design = order.gear_design_mix_id
        if not design:
            return {}

        bom_quantities = calculator._extract_bom_materials(design) if hasattr(calculator, "_extract_bom_materials") else {}

        def _qty(key, fallback):
            return bom_quantities.get(key, fallback or 0.0)

        cement_qty = _qty("cement_qty", getattr(design, "cement_qty", 0.0))
        agg10_qty = _qty("agg_10mm_qty", getattr(design, "agg_10mm_qty", 0.0))
        agg20_qty = _qty("agg_20mm_qty", getattr(design, "agg_20mm_qty", 0.0))
        admixture_qty = _qty("admixture_qty", getattr(design, "admixture_qty", 0.0))

        def _rate(area, field):
            return getattr(area, field, 0.0) if area else 0.0

        area_override = order.gear_material_area_id
        cement_area = order.gear_cement_area_id or area_override
        agg10_area = order.gear_agg_10mm_area_id or area_override
        agg20_area = order.gear_agg_20mm_area_id or area_override
        admixture_area = order.gear_admixture_area_id or area_override

        cement_rate = _rate(cement_area, "cement_rate")
        agg10_rate = _rate(agg10_area, "agg_10mm_rate")
        agg20_rate = _rate(agg20_area, "agg_20mm_rate")
        admixture_rate = _rate(admixture_area, "admixture_rate")

        cement_total = (cement_qty / 50.0) * cement_rate if cement_qty else 0.0
        agg10_total = (agg10_qty / 1000.0) * agg10_rate if agg10_qty else 0.0
        agg20_total = (agg20_qty / 1000.0) * agg20_rate if agg20_qty else 0.0
        admixture_total = (admixture_qty / 1000.0) * admixture_rate if admixture_qty else 0.0

        return {
            "grade": design.grade,
            "area": area_override or False,
            "lines": [
                {
                    "label": "Cement",
                    "qty": cement_qty,
                    "unit": "kg",
                    "rate": cement_rate,
                    "total": cement_total,
                },
                {
                    "label": "10mm Aggregate",
                    "qty": agg10_qty,
                    "unit": "kg",
                    "rate": agg10_rate,
                    "total": agg10_total,
                },
                {
                    "label": "20mm Aggregate",
                    "qty": agg20_qty,
                    "unit": "kg",
                    "rate": agg20_rate,
                    "total": agg20_total,
                },
                {
                    "label": "Admixture",
                    "qty": admixture_qty,
                    "unit": "ml",
                    "rate": admixture_rate,
                    "total": admixture_total,
                },
            ],
            "total": cement_total + agg10_total + agg20_total + admixture_total,
        }

    # --------------------
    # Chart generators
    # --------------------
    def _create_temp_image(self, name):
        temp = tempfile.NamedTemporaryFile(prefix=f"{name}_", suffix=".png", delete=False)
        path = temp.name
        temp.close()
        return path

    def _pillow_canvas(self, width: int, height: int):
        """Return a Pillow canvas tuple when matplotlib is unavailable."""
        if not Image or not ImageDraw:
            return None, None, None
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default() if ImageFont else None
        return image, draw, font

    def _save_pillow_image(self, image, name: str):
        if not image:
            return None
        path = self._create_temp_image(name)
        image.save(path, format="PNG")
        return path

    def _import_matplotlib(self, chart_name: str) -> Optional[ModuleType]:
        """Try importing matplotlib and log a single warning per call if missing."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # force headless backend so wkhtml/pdf threads don't try to spawn GUI
            import matplotlib.pyplot as plt  # type: ignore[import]
        except ModuleNotFoundError:
            _logger.warning(
                "Matplotlib is not installed; skipping %s chart generation. "
                "Install `matplotlib` in the Odoo environment to enable charts.",
                chart_name,
            )
            return None
        return plt

    def _fallback_cost_breakdown_pie(self, breakdown: Dict[str, float]):
        image, draw, font = self._pillow_canvas(640, 360)
        if not image:
            return None

        segments = []
        for key in ["base", "material", "optional", "dead_cost", "margin"]:
            amount = breakdown.get(key, 0.0) or 0.0
            if amount <= 0:
                continue
            segments.append((key.replace("_", " ").title(), amount, self._COLOR_MAP.get(key, "#cccccc")))

        total = sum(amount for _label, amount, _color in segments)
        if total <= 0:
            return None

        draw.text((40, 15), "Cost Breakdown", fill="black", font=font)
        bbox = (40, 60, 320, 340)
        start_angle = 0.0
        for _label, amount, color in segments:
            extent = 360.0 * (amount / total)
            draw.pieslice(bbox, start=start_angle, end=start_angle + extent, fill=color, outline="white")
            start_angle += extent

        legend_x = 360
        legend_y = 80
        for label, amount, color in segments:
            draw.rectangle((legend_x, legend_y, legend_x + 20, legend_y + 20), fill=color)
            draw.text((legend_x + 26, legend_y), f"{label}: {amount:.1f}", fill="black", font=font)
            legend_y += 26

        return self._save_pillow_image(image, "bp_cost_breakdown")

    def _generate_cost_breakdown_pie(self, breakdown: Dict[str, float]):
        plt = self._import_matplotlib("cost breakdown")
        if not plt:
            return self._fallback_cost_breakdown_pie(breakdown)

        labels = []
        values = []
        colors = []
        for key in ["base", "material", "optional", "dead_cost", "margin"]:
            amount = breakdown.get(key, 0.0)
            if amount <= 0:
                continue
            labels.append(key.replace("_", " ").title())
            values.append(amount)
            colors.append(self._COLOR_MAP.get(key, "#cccccc"))

        if not values:
            return None

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(values, labels=labels, colors=colors, autopct="%1.1f%%")
        ax.set_title("Cost Breakdown")

        path = self._create_temp_image("bp_cost_breakdown")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    def _fallback_mgq_bar_chart(self, scenarios: Iterable[Dict[str, float]]):
        scenario_list = list(scenarios)
        image, draw, font = self._pillow_canvas(700, 420)
        if not image:
            return None

        totals = [(s.get("prime_bill", 0.0) + s.get("optimize_bill", 0.0) + s.get("after_bill", 0.0)) for s in scenario_list]
        max_total = max(totals) if totals else 0.0
        if max_total <= 0:
            max_total = 1.0

        left_margin = 80
        base_line = 340
        bar_width = 60
        spacing = 40
        chart_height = 240

        draw.text((left_margin, 20), "MGQ Billing Scenarios", fill="black", font=font)
        draw.line((left_margin, base_line, left_margin, base_line - chart_height - 10), fill="#333333", width=2)
        draw.line((left_margin, base_line, left_margin + len(totals) * (bar_width + spacing), base_line), fill="#333333", width=2)

        for idx, scenario in enumerate(scenario_list):
            x = left_margin + idx * (bar_width + spacing)
            cursor = base_line
            stacks = [
                (scenario.get("prime_bill", 0.0), self._COLOR_MAP["base"]),
                (scenario.get("optimize_bill", 0.0), self._COLOR_MAP["penalty"]),
                (scenario.get("after_bill", 0.0), self._COLOR_MAP["optional"]),
            ]
            for amount, color in stacks:
                if amount <= 0:
                    continue
                height = int((amount / max_total) * chart_height)
                draw.rectangle((x, cursor - height, x + bar_width, cursor), fill=color, outline="white")
                cursor -= height
            draw.text((x, base_line + 8), scenario.get("label", ""), fill="black", font=font)

        return self._save_pillow_image(image, "bp_mgq_bar")

    def _generate_mgq_bar_chart(self, scenarios: Iterable[Dict[str, float]]):
        scenario_list = list(scenarios)
        plt = self._import_matplotlib("MGQ bar")
        if not plt:
            return self._fallback_mgq_bar_chart(scenario_list)

        labels = [s.get("label", "") for s in scenario_list]
        prime = [s.get("prime_bill", 0.0) for s in scenario_list]
        optimize = [s.get("optimize_bill", 0.0) for s in scenario_list]
        after = [s.get("after_bill", 0.0) for s in scenario_list]

        x = range(len(labels))
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(x, prime, label="Prime", color=self._COLOR_MAP["base"])
        ax.bar(x, optimize, bottom=prime, label="Optimize", color=self._COLOR_MAP["penalty"])
        stacked_after = [p + o for p, o in zip(prime, optimize)]
        ax.bar(x, after, bottom=stacked_after, label="After MGQ", color=self._COLOR_MAP["optional"])
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Billing")
        ax.set_title("MGQ Billing Scenarios")
        ax.legend()

        path = self._create_temp_image("bp_mgq_bar")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    def _fallback_diesel_escalation_chart(self, order):
        image, draw, font = self._pillow_canvas(720, 380)
        if not image:
            return None

        baseline = order.diesel_rate_per_litre or 90.0
        prices = list(range(85, 101))
        impacts = [(price - baseline) * 0.3 for price in prices]
        min_impact = min(impacts)
        max_impact = max(impacts)
        spread = max(max_impact - min_impact, 1.0)
        left = 70
        bottom = 320
        width = 560
        height = 240

        draw.text((left, 25), "Diesel Escalation Impact", fill="black", font=font)
        draw.text((left, bottom + 20), f"Baseline price: {baseline:.1f}", fill="black", font=font)

        prev_point = None
        for idx, price in enumerate(prices):
            x = left + (idx / (len(prices) - 1)) * width
            y = bottom - ((impacts[idx] - min_impact) / spread) * height
            if prev_point:
                draw.line((*prev_point, x, y), fill=self._COLOR_MAP["optional"], width=3)
            prev_point = (x, y)
        draw.line((left, bottom, left + width, bottom), fill="#333333", width=2)
        draw.line((left, bottom - height, left, bottom), fill="#333333", width=2)

        return self._save_pillow_image(image, "bp_diesel_line")

    def _generate_diesel_escalation_chart(self, order):
        plt = self._import_matplotlib("diesel escalation")
        if not plt:
            return self._fallback_diesel_escalation_chart(order)

        baseline = order.diesel_rate_per_litre or 90.0
        prices = list(range(85, 101))
        impacts = [(price - baseline) * 0.3 for price in prices]

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(prices, impacts, color=self._COLOR_MAP["optional"], marker="o")
        tolerance = [impact * 0 + baseline * 0.05 for impact in impacts]
        ax.fill_between(prices, [-t for t in tolerance], tolerance, color="#e5e5e5", alpha=0.4)
        ax.axhline(0, color="#333333", linewidth=1)
        ax.set_title("Diesel Escalation Impact")
        ax.set_xlabel("Diesel Price (₹)")
        ax.set_ylabel("Rate Impact (per CUM)")

        path = self._create_temp_image("bp_diesel_line")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    def _fallback_grade_comparison_chart(self, grade_rows: List[Dict[str, float]]):
        image, draw, font = self._pillow_canvas(760, 460)
        if not image or not grade_rows:
            return None

        max_total = max((row.get("total", 0.0) for row in grade_rows), default=0.0)
        if max_total <= 0:
            max_total = 1.0

        left = 160
        top = 70
        bar_height = 20
        spacing = 18
        span = 460

        draw.text((left, 25), "Grade-Wise Rate Comparison", fill="black", font=font)
        for idx, row in enumerate(grade_rows):
            y = top + idx * (bar_height + spacing)
            x = left
            base_width = int((row.get("base", 0.0) / max_total) * span)
            material_width = int((row.get("material", 0.0) / max_total) * span)
            optional_width = int((row.get("optional", 0.0) / max_total) * span)

            if base_width > 0:
                draw.rectangle((x, y, x + base_width, y + bar_height), fill=self._COLOR_MAP["base"], outline="white")
            x += base_width
            if material_width > 0:
                draw.rectangle((x, y, x + material_width, y + bar_height), fill=self._COLOR_MAP["material"], outline="white")
            x += material_width
            if optional_width > 0:
                draw.rectangle((x, y, x + optional_width, y + bar_height), fill=self._COLOR_MAP["optional"], outline="white")
            draw.text((20, y), row.get("grade", ""), fill="black", font=font)
            draw.text((x + 10, y), f"{row.get('total', 0.0):.0f}", fill="black", font=font)

        return self._save_pillow_image(image, "bp_grade_comparison")

    def _generate_grade_comparison_chart(self, grade_rows: List[Dict[str, float]]):
        plt = self._import_matplotlib("grade comparison")
        if not plt:
            return self._fallback_grade_comparison_chart(grade_rows)

        if not grade_rows:
            return None

        grades = [row["grade"] for row in grade_rows]
        base = [row["base"] for row in grade_rows]
        material = [row["material"] for row in grade_rows]
        optional = [row["optional"] for row in grade_rows]
        totals = [row["total"] for row in grade_rows]

        y_pos = range(len(grades))
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(y_pos, base, color=self._COLOR_MAP["base"], label="Base")
        ax.barh(y_pos, material, left=base, color=self._COLOR_MAP["material"], label="Material")
        stacked_opt = [b + m for b, m in zip(base, material)]
        ax.barh(y_pos, optional, left=stacked_opt, color=self._COLOR_MAP["optional"], label="Optional")
        for idx, total in enumerate(totals):
            ax.text(total + 5, idx, f"{total:.0f}")
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(grades)
        ax.set_xlabel("Rate per CUM")
        ax.set_title("Grade-Wise Rate Comparison")
        ax.legend()

        path = self._create_temp_image("bp_grade_comparison")
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return path

    def _encode_chart(self, path):
        if not path:
            return None
        if isinstance(path, str) and path.startswith("data:image"):
            return path
        try:
            with open(path, "rb") as handle:
                encoded = base64.b64encode(handle.read()).decode("ascii")
                return f"data:image/png;base64,{encoded}"
        except FileNotFoundError:
            return None

    # --------------------
    # Public API
    # --------------------
    @api.model
    def prepare_pdf_assets(self, order, production_qty=None):
        """Return a dictionary of chart paths and structured data for QWeb."""
        calculator = self._calculator()
        base_rates = calculator.calculate_base_plant_rate(order, production_qty)
        final_rates = calculator.generate_final_rates(order, production_qty)
        source_map = final_rates.get("source_map", {})
        capex_breakdown = calculator.calculate_capex_breakdown(order)

        base_rates.update(
            {
                "prime_rate": final_rates.get("prime_rate", base_rates.get("prime_rate")),
                "optimize_rate": final_rates.get("optimize_rate", base_rates.get("optimize_rate")),
                "after_mgq_rate": final_rates.get("after_mgq_rate", base_rates.get("after_mgq_rate")),
                "ngt_rate": final_rates.get("ngt_rate", base_rates.get("ngt_rate")),
                "base_rate_per_cum": final_rates.get("base_rate_per_cum", base_rates.get("base_rate_per_cum")),
                "mgq": final_rates.get("mgq", base_rates.get("mgq")),
                "production_qty": final_rates.get("production_qty", base_rates.get("production_qty")),
                "prime_bill": final_rates.get("prime_bill", base_rates.get("prime_bill")),
                "optimize_bill": final_rates.get("optimize_bill", base_rates.get("optimize_bill")),
                "after_mgq_bill": final_rates.get("after_mgq_bill", base_rates.get("after_mgq_bill")),
            }
        )

        breakdown = self._build_cost_breakdown(order, production_qty)
        mgq_scenarios = self._build_mgq_scenarios(order)
        grade_rows = self._build_grade_comparison(order) if order.x_inventory_mode == "with_inventory" else []
        capex_breakdown = self._build_capex_breakdown(order, final_rates)
        material_breakdown = self._material_breakdown(order)

        cost_pie_path = self._generate_cost_breakdown_pie(breakdown)
        mgq_chart_path = self._generate_mgq_bar_chart(mgq_scenarios) if mgq_scenarios else None
        diesel_chart_path = self._generate_diesel_escalation_chart(order)
        grade_chart_path = self._generate_grade_comparison_chart(grade_rows) if grade_rows else None

        chart_urls = {
            "cost_pie": self._encode_chart(cost_pie_path),
            "mgq_bars": self._encode_chart(mgq_chart_path),
            "diesel_line": self._encode_chart(diesel_chart_path),
            "grade_comparison": self._encode_chart(grade_chart_path),
        }

        plant_slabs = {
            "mgq": base_rates.get("mgq", 0.0),
            "prime_rate": final_rates.get("final_prime_rate") or final_rates.get("prime_rate") or 0.0,
            "optimize_rate": final_rates.get("final_optimize_rate") or final_rates.get("optimize_rate") or 0.0,
            "after_mgq_rate": final_rates.get("final_after_mgq_rate") or final_rates.get("after_mgq_rate") or 0.0,
            "ngt_rate": final_rates.get("final_ngt_rate")
            or order.ngt_rate
            or (order.gear_mgq_rate_id.ngt_rate if order.gear_mgq_rate_id else 0.0)
            or 0.0,
        }

        optional_services = final_rates.get("full_rate_breakdown", {}).get("optional_services", [])
        project_duration = order.gear_project_duration_years or order.gear_project_duration_months or False
        production_expectation = self._resolve_production_expectation(order, base_rates, final_rates)

        summary_cards = [
            {"label": "Total Investment", "value": order.gear_dead_cost_amount or 0.0},
            {"label": "MGQ", "value": base_rates.get("mgq", 0.0)},
            {"label": "Break-even MGQ", "value": base_rates.get("mgq", 0.0)},
            {
                "label": "Monthly Billing Window",
                "value": f"{math.floor(base_rates.get('prime_bill', 0.0))} - {math.ceil(base_rates.get('prime_bill', 0.0) + base_rates.get('optimize_bill', 0.0) + base_rates.get('after_mgq_bill', 0.0))}",
            },
        ]
        dead_cost_value = final_rates.get("dead_per_cum", final_rates.get("dead_cost", 0.0))
        dead_cost_total = capex_breakdown.get("total_amount") or order.gear_dead_cost_amount or 0.0
        dead_cost_context = {
            "per_cum": dead_cost_value,
            "total": dead_cost_total,
        }

        return {
            "order": order,
            "base_rates": base_rates,
            "final_rates": final_rates,
            "cost_breakdown": breakdown,
            "mgq_scenarios": mgq_scenarios,
            "grade_rows": grade_rows,
            "charts": chart_urls,
            "summary_cards": summary_cards,
            "capex_breakdown": capex_breakdown,
            "source_map": source_map,
            # Required PDF data contract
            "mgq": plant_slabs.get("mgq", 0.0),
            "production_expectation": production_expectation,
            "project_duration": project_duration,
            "plant_slabs": plant_slabs,
            "material_breakdown": material_breakdown,
            "optional_services": optional_services,
            "dead_cost": dead_cost_value,
            "dead_cost_context": dead_cost_context,
            "capex_items": capex_breakdown.get("items") or [],
            "final_rate": final_rates.get("final_prime_rate") or final_rates.get("total_rate_per_cum", 0.0),
            "grade_wise": grade_rows,
            "cost_pie_chart": chart_urls.get("cost_pie"),
            "mgq_billing_chart": chart_urls.get("mgq_bars"),
            "diesel_chart": chart_urls.get("diesel_line"),
            "grade_chart": chart_urls.get("grade_comparison"),
        }
