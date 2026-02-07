from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GearNgTMeterLog(models.Model):
    """Monthly meter log for office electricity readings used in NGT expense."""

    _name = "gear.ngt.meter.log"
    _description = "NGT Meter Log"
    _order = "month desc, id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True)
    so_id = fields.Many2one(
        comodel_name="sale.order",
        string="Contract / SO",
        required=True,
        domain=[("state", "in", ["sale", "done"])],
    )
    month = fields.Date(
        string="Month",
        required=True,
        help="Any date in the month; stored as first day of that month.",
    )
    start_meter = fields.Float(string="Start Meter Reading", digits=(16, 2))
    end_meter = fields.Float(string="End Meter Reading", digits=(16, 2))
    meter_units = fields.Float(
        string="Metered Units",
        compute="_compute_units",
        store=True,
        digits=(16, 2),
    )
    electricity_unit_rate = fields.Monetary(
        string="Unit Rate",
        currency_field="currency_id",
        help="Rate per unit/kVAh for this month.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        for vals in vals_list:
            if vals.get("month"):
                vals["month"] = fields.Date.to_date(vals["month"]).replace(day=1)
            if not vals.get("name") or vals.get("name") == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("gear.ngt.meter.log") or _("New")
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("month"):
            vals["month"] = fields.Date.to_date(vals["month"]).replace(day=1)
        return super().write(vals)

    @api.constrains("start_meter", "end_meter")
    def _check_meter_order(self):
        for rec in self:
            if rec.start_meter and rec.end_meter and rec.end_meter < rec.start_meter:
                raise UserError(_("End meter reading must be greater than or equal to start meter reading."))

    @api.depends("start_meter", "end_meter")
    def _compute_units(self):
        for rec in self:
            if rec.start_meter and rec.end_meter:
                rec.meter_units = round(max(rec.end_meter - rec.start_meter, 0.0), 2)
            else:
                rec.meter_units = 0.0
