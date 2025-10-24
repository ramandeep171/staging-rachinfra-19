from odoo import api, fields, models


class RmcMixer(models.Model):
    _name = "rmc.mixer"
    _description = "Transit Mixer"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "transport_code"

    name = fields.Char(compute="_compute_name", store=True)
    transport_code = fields.Char(readonly=True, copy=False)
    plant_id = fields.Many2one("rmc.subcontractor.plant", required=True, ondelete="cascade")
    subcontractor_id = fields.Many2one(related="plant_id.subcontractor_id", store=True)
    reg_no = fields.Char(required=True)
    capacity_m3 = fields.Float()
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

    _sql_constraints = [
        ("reg_no_unique", "unique(reg_no)", "Registration number must be unique."),
    ]

    @api.depends("transport_code", "reg_no")
    def _compute_name(self):
        for record in self:
            record.name = record.transport_code or record.reg_no

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if not record.transport_code:
                record._assign_transport_code(vals)
        return records

    def _assign_transport_code(self, vals):
        self.ensure_one()
        plant_code = self.plant_id.plant_code or "PLANT"
        ctx = dict(self.env.context, plant_code=plant_code.replace(" ", ""))
        code = self.env["ir.sequence"].with_context(ctx).next_by_code("rmc.transport.code")
        self.write({"transport_code": code})
