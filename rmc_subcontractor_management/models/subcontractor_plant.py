from odoo import api, fields, models


class RmcSubcontractorPlant(models.Model):
    _inherit = "rmc.subcontractor.plant"

    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "In Review"),
            ("ready", "Ready"),
        ],
        default="draft",
    )
    brand_id = fields.Many2one("rmc.product.brand")
    capacity_m3ph = fields.Float(string="Capacity (m³/hr)")
    compliance_attachment_ids = fields.Many2many("ir.attachment", string="Compliance Documents")
    plant_sequence_locked = fields.Boolean(default=False)
    mixer_ids = fields.One2many("rmc.mixer", "plant_id", string="Transit Mixers")
    pump_ids = fields.One2many("rmc.pump.code", "plant_id", string="Pumps")

    def ensure_plant_code(self):
        for plant in self:
            if plant.plant_code:
                continue
            plant_code = self.env["ir.sequence"].next_by_code("rmc.plant.code")
            plant.write({"plant_code": plant_code})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for plant in records:
            plant.ensure_plant_code()
        return records
