from odoo import api, fields, models


class GearVariableCostMaster(models.Model):
    _name = "gear.variable.cost.master"
    _description = "Variable Cost Master"
    _rec_name = "company_id"

    power_monthly = fields.Float(string="Power (per CUM)")
    diesel_monthly = fields.Float(string="Diesel (per CUM)")
    jcb_diesel_per_cum = fields.Float(string="JCB Diesel (per CUM)")
    total_monthly = fields.Float(string="Total (per CUM)", compute="_compute_total", store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company
    )

    @api.depends("power_monthly", "diesel_monthly", "jcb_diesel_per_cum")
    def _compute_total(self):
        for rec in self:
            rec.total_monthly = (
                (rec.power_monthly or 0.0)
                + (rec.diesel_monthly or 0.0)
                + (rec.jcb_diesel_per_cum or 0.0)
            )
