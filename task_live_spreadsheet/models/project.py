from odoo import fields, models


class Phase1Project(models.Model):
    _name = "phase1.project"
    _description = "Phase-1 Project"

    name = fields.Char(required=True)
    description = fields.Text()
    owner_id = fields.Many2one("res.users", string="Project Manager")
    start_date = fields.Date()
    expected_end_date = fields.Date()
    phase_ids = fields.One2many("phase1.phase", "project_id", string="Phases")


class Phase1Phase(models.Model):
    _name = "phase1.phase"
    _description = "Phase-1 Project Phase"
    _order = "sequence, id"

    name = fields.Selection(
        selection=[
            ("pre_order", "Pre-Order"),
            ("design", "Design"),
            ("procurement", "Procurement"),
            ("installation", "Installation"),
            ("testing", "Testing"),
            ("handover", "Handover"),
        ],
        required=True,
        string="Phase",
    )
    sequence = fields.Integer(default=10)
    status = fields.Selection(
        selection=[
            ("not_started", "Not Started"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
        ],
        required=True,
        default="not_started",
        string="Status",
        help="Manual status only; no automatic transitions.",
    )
    project_id = fields.Many2one(
        "phase1.project",
        required=True,
        ondelete="cascade",
        string="Project",
    )
    notes = fields.Text(
        string="Notes",
        help="Manual context or completion details; no automation triggered.",
    )
