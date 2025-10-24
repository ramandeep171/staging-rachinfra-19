from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RmcSubcontractorOnboardWizard(models.TransientModel):
    _name = "rmc.subcontractor.onboard.wizard"
    _description = "Subcontractor Onboarding Wizard"

    phase = fields.Selection(
        [
            ("phase1", "Company Summary"),
            ("phase2", "Plants & Fleet"),
        ],
        default="phase1",
    )
    subcontractor_id = fields.Many2one("rmc.subcontractor", required=True)
    profile_id = fields.Many2one("rmc.subcontractor.profile", required=True)
    stepper_state = fields.Selection(
        [
            ("phase1", "Company Summary"),
            ("phase2", "Plants & Fleet"),
            ("complete", "Complete"),
        ],
        default="phase1",
    )
    plant_ids = fields.One2many("rmc.subcontractor.plant", compute="_compute_phase_two_lines")
    mixer_ids = fields.One2many("rmc.mixer", compute="_compute_phase_two_lines")
    pump_ids = fields.One2many("rmc.pump.code", compute="_compute_phase_two_lines")
    phase1_completion = fields.Float(related="profile_id.completion_percent")
    legal_name = fields.Char(related="profile_id.legal_name", readonly=False)
    brand_trade_name = fields.Char(related="profile_id.brand_trade_name", readonly=False)
    gstin = fields.Char(related="profile_id.gstin", readonly=False)
    pan = fields.Char(related="profile_id.pan", readonly=False)
    msme_udyam = fields.Char(related="profile_id.msme_udyam", readonly=False)
    established_year = fields.Integer(related="profile_id.established_year", readonly=False)
    contact_person = fields.Char(related="profile_id.contact_person", readonly=False)
    mobile = fields.Char(related="profile_id.mobile", readonly=False)
    email = fields.Char(related="profile_id.email", readonly=False)
    whatsapp = fields.Char(related="profile_id.whatsapp", readonly=False)
    bank_name = fields.Char(related="profile_id.bank_name", readonly=False)
    bank_account_no = fields.Char(related="profile_id.bank_account_no", readonly=False)
    ifsc = fields.Char(related="profile_id.ifsc", readonly=False)
    upi_id = fields.Char(related="profile_id.upi_id", readonly=False)
    service_radius_km = fields.Float(related="profile_id.service_radius_km", readonly=False)
    plants_total = fields.Integer(related="profile_id.plants_total", readonly=False)
    mixers_total = fields.Integer(related="profile_id.mixers_total", readonly=False)
    pumps_total = fields.Integer(related="profile_id.pumps_total", readonly=False)
    base_pricing_note = fields.Text(related="profile_id.base_pricing_note", readonly=False)
    cut_percent = fields.Float(related="profile_id.cut_percent", readonly=False)
    mgq_per_month_m3 = fields.Float(related="profile_id.mgq_per_month_m3", readonly=False)
    rental_amount = fields.Monetary(related="profile_id.rental_amount", readonly=False)
    pricing_terms = fields.Text(related="profile_id.pricing_terms", readonly=False)
    currency_id = fields.Many2one(related="profile_id.currency_id", readonly=False)

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        subcontractor = self.env["rmc.subcontractor"].browse(result.get("subcontractor_id"))
        if subcontractor and not result.get("profile_id"):
            result["profile_id"] = subcontractor.profile_id.id
        return result

    def action_save_phase1(self):
        self.ensure_one()
        profile_fields = [
            "legal_name",
            "brand_trade_name",
            "gstin",
            "pan",
            "msme_udyam",
            "established_year",
            "contact_person",
            "mobile",
            "email",
            "whatsapp",
            "bank_name",
            "bank_account_no",
            "ifsc",
            "upi_id",
            "service_radius_km",
            "plants_total",
            "mixers_total",
            "pumps_total",
            "base_pricing_note",
            "cut_percent",
            "mgq_per_month_m3",
            "rental_amount",
            "pricing_terms",
        ]
        values = {field: getattr(self, field, False) for field in profile_fields if hasattr(self, field)}
        self.profile_id.write(values)
        self._ensure_plant_placeholders()
        if not self.subcontractor_id.more_info_token_id or not self.subcontractor_id.more_info_token_id.portal_user_id:
            self._create_portal_user()
        self.phase = "phase2"
        self.stepper_state = "phase2"
        return self._action_reload()

    def action_save_phase2(self):
        self.ensure_one()
        if not self.subcontractor_id.plant_ids:
            raise UserError(_("Please configure at least one plant before completing onboarding."))
        total_mixers = sum(len(plant.mixer_ids) for plant in self.subcontractor_id.plant_ids)
        total_pumps = sum(len(plant.pump_ids) for plant in self.subcontractor_id.plant_ids)
        if total_mixers == 0 and total_pumps == 0:
            raise UserError(_("Add at least one mixer or pump to continue."))
        self.stepper_state = "complete"
        return self._action_reload()

    def action_open_profile(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "rmc.subcontractor.profile",
            "view_mode": "form",
            "res_id": self.profile_id.id,
            "target": "current",
        }

    def _action_reload(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _ensure_plant_placeholders(self):
        placeholders = self.profile_id.plant_placeholder_ids
        missing = max(self.profile_id.plants_total - len(placeholders), 0)
        for _idx in range(missing):
            self.env["rmc.subcontractor.plant.placeholder"].create(
                {"profile_id": self.profile_id.id, "name": _("Plant %s") % (len(placeholders) + 1)}
            )
        return True

    def _create_portal_user(self):
        self.ensure_one()
        partner = self.subcontractor_id.ensure_vendor_partner()
        group = self.env.ref("base.group_portal")
        Users = self.env["res.users"].sudo()
        login = self.profile_id.email or self.subcontractor_id.contact_email
        if not login:
            raise UserError(_("Provide an email before creating the portal user."))
        existing_user = Users.search([("login", "=", login)], limit=1)
        if existing_user:
            user = existing_user
            if group.id not in user.groups_id.ids:
                user.write({"groups_id": [(4, group.id)]})
        else:
            user = Users.with_context(no_reset_password=True).create(
                {
                    "name": self.subcontractor_id.name,
                    "login": login,
                    "partner_id": partner.id if partner else False,
                    "groups_id": [(6, 0, [group.id])],
                }
            )
        self.subcontractor_id.more_info_token_id.write(
            {"portal_user_id": user.id, "is_portal_user_created": True, "state": "portal"}
        )
        self.subcontractor_id.write({"portal_user_id": user.id})

    @api.depends("subcontractor_id")
    def _compute_phase_two_lines(self):
        for wizard in self:
            wizard.plant_ids = wizard.subcontractor_id.plant_ids
            wizard.mixer_ids = wizard.subcontractor_id.plant_ids.mapped("mixer_ids")
            wizard.pump_ids = wizard.subcontractor_id.plant_ids.mapped("pump_ids")
