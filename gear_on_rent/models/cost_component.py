from odoo import api, fields, models


class GearCostComponent(models.Model):
    """Cost component entries linked to batching-plant quotations.

    These records capture the granular running costs, CAPEX depreciation, dead
    cost amortization, material surcharges, and optional service surcharges
    referenced by the upgraded costing engine.
    """

    _name = "gear.cost.component"
    _description = "Batching Plant Cost Component"

    name = fields.Char(required=True)
    component_type = fields.Selection(
        selection=[
            ("base", "Base Plant Cost"),
            ("material", "Material Cost"),
            ("optional", "Optional Service"),
            ("dead_cost", "Dead Cost"),
            ("capex", "CAPEX / Depreciation"),
        ],
        required=True,
    )
    amount = fields.Monetary(currency_field="currency_id", string="Amount")
    quantity = fields.Float(string="Quantity", digits=(16, 2))
    grade = fields.Selection(selection=[("m10", "M10"), ("m20", "M20"), ("m25", "M25"), ("m30", "M30")])
    area = fields.Char(string="Area")
    order_id = fields.Many2one("sale.order", string="Quotation")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id.id)

    @api.model
    def _sum_amounts(self, recordset):
        return sum(recordset.mapped("amount"))

    def get_running_cost(self):
        """Return the monthly running cost total."""

        return self._sum_amounts(self.filtered(lambda c: c.component_type == "base"))

    def get_monthly_depreciation(self, project_months):
        """Return monthly depreciation derived from CAPEX components."""

        capex_total = self._sum_amounts(self.filtered(lambda c: c.component_type == "capex"))
        if not project_months:
            return 0.0
        return capex_total / float(project_months)

    def get_dead_cost(self):
        return self._sum_amounts(self.filtered(lambda c: c.component_type == "dead_cost"))

    def get_material_cost_per_cum(self, grade=None, area=None):
        material_components = self.filtered(lambda c: c.component_type == "material")
        if grade:
            material_components = material_components.filtered(lambda c: not c.grade or c.grade == grade)
        if area:
            material_components = material_components.filtered(lambda c: not c.area or c.area == area)
        return self._sum_amounts(material_components)

    def get_optional_cost_per_cum(self, quotation):
        optional_components = self.filtered(lambda c: c.component_type == "optional")
        per_cum_total = self._sum_amounts(optional_components)
        if per_cum_total:
            return per_cum_total
        # Fallback to optional services already enabled on the quotation
        return quotation.env["gear.batching.quotation.calculator"].sudo().calculate_optional_services(quotation)
