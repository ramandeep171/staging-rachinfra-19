from odoo import fields, models


class GearScrapLog(models.Model):
    _name = "gear.scrap.log"
    _description = "Gear Scrap Log"
    _order = "create_date desc"

    workorder_id = fields.Many2one("mrp.workorder", string="Work Order", required=True, ondelete="cascade")
    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", related="workorder_id.production_id", store=True)
    monthly_order_id = fields.Many2one("gear.rmc.monthly.order", string="Monthly Work Order", related="production_id.x_monthly_order_id", store=True)
    quantity = fields.Float(string="Scrap Quantity (m³)", digits=(16, 2), required=True)
    reason_id = fields.Many2one("gear.cycle.reason", string="Reason")
    note = fields.Text(string="Notes")
    user_id = fields.Many2one("res.users", string="Logged By", default=lambda self: self.env.user, readonly=True)
