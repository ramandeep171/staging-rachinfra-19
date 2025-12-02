"""PDF and chart planning helpers for batching-plant quotations.

Branding Patch Stage-5 applied for SP Nexgen Automind Pvt Ltd — Tech Paras
© SP Nexgen Automind Pvt Ltd · www.smarterpeak.com

This helper is scoped to the new "/batching-plant" landing page and consumes the
output of the quotation calculator to prepare chart images and a skeleton PDF
context. It does not generate or style the final PDF; it only prepares data and
image assets for downstream QWeb rendering.
"""

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

    def _calculator(self):
        return self.env["gear.batching.quotation.calculator"]

    # --------------------
    # Data preparation
    # --------------------
    def _build_cost_breakdown(self, order, production_qty=None):
        calculator = self._calculator()
        base = calculator.calculate_base_plant_rate(order, production_qty)
        optional_cost = calculator.calculate_optional_services(order)
        material_cost = calculator.calculate_material_cost(order)
        dead_cost = calculator.calculate_dead_cost(order)

        return {
            "base": base.get("base_rate_per_cum", 0.0),
            "material": material_cost,
            "optional": optional_cost,
            "dead_cost": dead_cost,
            "margin": 0.0,
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
            base = calculator.calculate_base_plant_rate(order, qty)
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
        optional_cost = calculator.calculate_optional_services(order)
        dead_cost = calculator.calculate_dead_cost(order)
        material_area = order.gear_material_area_id
        base = calculator.calculate_base_plant_rate(order)
        base_rate = base.get("base_rate_per_cum", 0.0)

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

    # --------------------
    # Public API
    # --------------------
    @api.model
    def prepare_pdf_assets(self, order, production_qty=None):
        """Return a dictionary of chart paths and structured data for QWeb."""
        calculator = self._calculator()
        base_rates = calculator.calculate_base_plant_rate(order, production_qty)
        final_rates = calculator.generate_final_rates(order, production_qty)

        breakdown = self._build_cost_breakdown(order, production_qty)
        mgq_scenarios = self._build_mgq_scenarios(order)
        grade_rows = self._build_grade_comparison(order) if order.x_inventory_mode == "with_inventory" else []

        cost_pie_path = self._generate_cost_breakdown_pie(breakdown)
        mgq_chart_path = self._generate_mgq_bar_chart(mgq_scenarios) if mgq_scenarios else None
        diesel_chart_path = self._generate_diesel_escalation_chart(order)
        grade_chart_path = self._generate_grade_comparison_chart(grade_rows) if grade_rows else None

        summary_cards = [
            {"label": "Total Investment", "value": order.gear_dead_cost_amount or 0.0},
            {"label": "MGQ", "value": base_rates.get("mgq", 0.0)},
            {"label": "Break-even MGQ", "value": base_rates.get("mgq", 0.0)},
            {
                "label": "Monthly Billing Window",
                "value": f"{math.floor(base_rates.get('prime_bill', 0.0))} - {math.ceil(base_rates.get('prime_bill', 0.0) + base_rates.get('optimize_bill', 0.0) + base_rates.get('after_mgq_bill', 0.0))}",
            },
        ]

        return {
            "order": order,
            "base_rates": base_rates,
            "final_rates": final_rates,
            "cost_breakdown": breakdown,
            "mgq_scenarios": mgq_scenarios,
            "grade_rows": grade_rows,
            "charts": {
                "cost_pie": cost_pie_path,
                "mgq_bars": mgq_chart_path,
                "diesel_line": diesel_chart_path,
                "grade_comparison": grade_chart_path,
            },
            "summary_cards": summary_cards,
        }

