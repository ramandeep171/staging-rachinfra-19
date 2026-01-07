from odoo import _, api, fields, models
from odoo.exceptions import UserError


class GearScrapLogWizard(models.TransientModel):
    _name = "gear.scrap.log.wizard"
    _description = "Log Scrap"

    workorder_id = fields.Many2one("mrp.workorder", string="Work Order", required=True)
    production_id = fields.Many2one("mrp.production", related="workorder_id.production_id", store=False, readonly=True)
    monthly_order_id = fields.Many2one("gear.rmc.monthly.order", related="production_id.x_monthly_order_id", store=False, readonly=True)
    quantity = fields.Float(string="Scrap Quantity (m³)", digits=(16, 2), required=True)
    reason_id = fields.Many2one("gear.cycle.reason", string="Reason")
    note = fields.Text(string="Notes")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        workorder = self.env["mrp.workorder"].browse(self.env.context.get("active_id"))
        if workorder:
            res.setdefault("workorder_id", workorder.id)
        return res

    def action_log_scrap(self):
        self.ensure_one()
        if self.quantity <= 0:
            raise UserError(_("Scrap quantity must be greater than zero."))
        raise UserError(_("Use the standard Log Scrap action from the work order."))
