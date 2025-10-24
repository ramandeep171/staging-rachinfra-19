from odoo import api, fields, models


class RmcPump(models.Model):
    _name = "rmc.pump.code"
    _description = "Concrete Pump"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(string="Pump Code", readonly=True, copy=False)
    plant_id = fields.Many2one("rmc.subcontractor.plant", required=True, ondelete="cascade")
    subcontractor_id = fields.Many2one(related="plant_id.subcontractor_id", store=True)
    pump_type = fields.Selection(
        [
            ("line", "Line Pump"),
            ("boom", "Boom Pump"),
        ],
        default="line",
    )
    reach_m = fields.Float(string="Reach (m)")
    ownership = fields.Selection(
        [
            ("owned", "Owned"),
            ("leased", "Leased"),
            ("third_party", "Third Party"),
        ],
        default="owned",
    )
    fitness_expiry = fields.Date()
    insurance_expiry = fields.Date()
    document_ids = fields.Many2many("ir.attachment", string="Documents")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.name:
                record._assign_pump_code()
        return records

    def _assign_pump_code(self):
        self.ensure_one()
        code = self.env["ir.sequence"].next_by_code("rmc.pump.code")
        self.write({"name": code})
