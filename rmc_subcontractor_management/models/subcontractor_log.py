from odoo import fields, models


class RmcProfileLog(models.Model):
    _name = "rmc.profile.log"
    _description = "Profile Audit Log"
    _order = "create_date desc"

    profile_id = fields.Many2one("rmc.subcontractor.profile", required=True, ondelete="cascade")
    subcontractor_id = fields.Many2one("rmc.subcontractor", ondelete="cascade")
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    activity = fields.Selection(
        [
            ("update", "Update"),
            ("stage", "Stage Change"),
            ("reminder", "Reminder"),
            ("portal", "Portal Access"),
        ],
        default="update",
    )
    message = fields.Text(required=True)
