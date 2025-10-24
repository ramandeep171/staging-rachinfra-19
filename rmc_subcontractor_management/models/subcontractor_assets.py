from odoo import api, fields, models


class RmcSubcontractorAsset(models.Model):
    _name = "rmc.subcontractor.asset"
    _description = "Subcontractor Generated Asset"

    name = fields.Char(required=True)
    subcontractor_id = fields.Many2one("rmc.subcontractor", required=True, ondelete="cascade")
    profile_id = fields.Many2one("rmc.subcontractor.profile", ondelete="cascade")
    asset_type = fields.Selection(
        [
            ("pdf", "PDF"),
            ("csv", "CSV"),
            ("report", "Report"),
            ("other", "Other"),
        ],
        default="pdf",
    )
    attachment_id = fields.Many2one("ir.attachment", ondelete="set null")
    availability = fields.Selection(
        [
            ("internal", "Internal"),
            ("portal", "Portal"),
        ],
        default="internal",
    )
    sequence = fields.Integer(default=10)
    portal_published = fields.Boolean(default=True)

    @api.model
    def create_or_link(self, subcontractor, name, attachment, **kwargs):
        existing = self.search(
            [
                ("subcontractor_id", "=", subcontractor.id),
                ("name", "=", name),
            ],
            limit=1,
        )
        if existing:
            existing.write({"attachment_id": attachment.id})
            return existing
        return self.create(
            {
                "name": name,
                "subcontractor_id": subcontractor.id,
                "attachment_id": attachment.id,
                **kwargs,
            }
        )
