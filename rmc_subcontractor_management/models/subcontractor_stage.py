import re

from odoo import api, fields, models


class RmcSubcontractorStage(models.Model):
    _name = "rmc.subcontractor.stage"
    _description = "Subcontractor Stage"
    _order = "sequence, id"

    name = fields.Char(required=True)
    code = fields.Char(required=True, help="Internal identifier used for automation.")
    sequence = fields.Integer(default=10)
    description = fields.Text()
    fold = fields.Boolean(help="Folded in kanban view when no record is in this stage.")
    is_docs_partial = fields.Boolean(string="Documents Partial")
    is_docs_complete = fields.Boolean(string="Documents Complete")
    category = fields.Selection(
        [
            ("qualification", "Qualification"),
            ("onboarding", "Onboarding"),
            ("active", "Active"),
            ("blocked", "Blocked"),
        ],
        default="qualification",
    )
    auto_lock_codes = fields.Boolean(
        help="Lock code regeneration for subcontractors that reach this stage or beyond."
    )
    mail_template_id = fields.Many2one(
        "mail.template",
        string="Auto Email Template",
        help="Email/WhatsApp template triggered when a subcontractor enters this stage.",
    )
    sla_to_hours = fields.Integer(
        string="SLA Reminder (Hours)",
        help="Optional SLA reminder for inactivity after entering this stage.",
    )
    active = fields.Boolean(default=True)

    def _generate_unique_code(self, name, used_codes=None):
        """Generate a deterministic code when users quick-create a stage."""
        base_code = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
        if not base_code:
            base_code = "stage"

        codes_in_batch = used_codes if used_codes is not None else set()
        sequence = 1
        candidate = base_code
        Stage = self.env["rmc.subcontractor.stage"].with_context(active_test=False)
        while candidate in codes_in_batch or Stage.search_count([("code", "=", candidate)]):
            sequence += 1
            candidate = f"{base_code}_{sequence}"
        codes_in_batch.add(candidate)
        return candidate

    @api.model_create_multi
    def create(self, vals_list):
        generated_codes = set()
        for vals in vals_list:
            if not vals.get("code") and vals.get("name"):
                vals["code"] = self._generate_unique_code(vals["name"], generated_codes)
        return super().create(vals_list)

    @api.model
    def stage_from_key(self, xml_id):
        try:
            return self.env.ref(xml_id)
        except ValueError:
            return self.env["rmc.subcontractor.stage"]
