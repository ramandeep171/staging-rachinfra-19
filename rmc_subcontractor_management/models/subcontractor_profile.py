from odoo import api, fields, models, _


class RmcSubcontractorProfile(models.Model):
    _name = "rmc.subcontractor.profile"
    _description = "Subcontractor Profile"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True, tracking=True)
    lead_id = fields.Many2one("crm.lead", string="Lead", ondelete="set null")
    subcontractor_id = fields.Many2one("rmc.subcontractor", string="Subcontractor", ondelete="set null")
    legal_name = fields.Char(tracking=True)
    brand_trade_name = fields.Char(tracking=True)
    gstin = fields.Char(string="GSTIN", tracking=True)
    pan = fields.Char(string="PAN", tracking=True)
    msme_udyam = fields.Char(string="MSME/Udyam", tracking=True)
    city = fields.Char()
    established_year = fields.Integer()
    contact_person = fields.Char()
    mobile = fields.Char()
    email = fields.Char()
    whatsapp = fields.Char()
    bank_name = fields.Char()
    bank_account_no = fields.Char()
    ifsc = fields.Char()
    upi_id = fields.Char()
    service_radius_km = fields.Float()
    preferred_geo_area_ids = fields.Many2many("rmc.subcontractor.geo.area", string="Preferred Geo Areas")
    brand_ids = fields.Many2many("rmc.product.brand", string="Supported Brands")
    plants_total = fields.Integer(default=0)
    mixers_total = fields.Integer(default=0)
    pumps_total = fields.Integer(default=0)
    plant_details = fields.Text(string="Plant Details")
    mixer_details = fields.Text(string="Mixer Details")
    pump_details = fields.Text(string="Pump Details")
    portal_totals_locked = fields.Boolean(string="Portal Totals Locked", default=False)
    base_pricing_note = fields.Text(string="Base Rate Matrix")
    cut_percent = fields.Float()
    mgq_per_month_m3 = fields.Float(string="Minimum Guaranteed Qty (m³)")
    rental_amount = fields.Monetary()
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id.id)
    pricing_terms = fields.Text()
    document_ids = fields.Many2many("ir.attachment", string="Company Documents")
    completion_percent = fields.Float(compute="_compute_completion")
    checklist_line_ids = fields.One2many(
        "rmc.subcontractor.profile.checklist",
        "profile_id",
        string="Checklist",
    )
    plant_placeholder_ids = fields.One2many(
        "rmc.subcontractor.plant.placeholder",
        "profile_id",
        string="Plant Placeholders",
    )
    hot_zone_id = fields.Many2one("rmc.subcontractor.hot.zone")
    geo_primary = fields.Char(string="Primary GEO", compute="_compute_primary_geo", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_default_checklist()
        return records

    @api.depends(
        "legal_name",
        "gstin",
        "contact_person",
        "mobile",
        "plants_total",
        "mixers_total",
        "pumps_total",
        "document_ids",
    )
    def _compute_completion(self):
        required = 6.0
        for record in self:
            score = 0.0
            if record.legal_name:
                score += 1
            if record.gstin:
                score += 1
            if record.contact_person and record.mobile:
                score += 1
            if record.plants_total:
                score += 1
            if record.mixers_total or record.pumps_total:
                score += 1
            if record.document_ids:
                score += 1
            record.completion_percent = 100.0 * (score / required) if required else 0.0

    @api.depends("preferred_geo_area_ids", "preferred_geo_area_ids.is_primary")
    def _compute_primary_geo(self):
        for record in self:
            primary = record.preferred_geo_area_ids.filtered("is_primary")[:1]
            record.geo_primary = primary.code if primary else False

    def _prepare_subcontractor_values(self):
        self.ensure_one()
        stage = self.env.ref("rmc_subcontractor_management.stage_subc_new", raise_if_not_found=False)
        partner = self.lead_id.partner_id
        if not partner:
            partner_vals = {
                "name": self.legal_name or self.name,
                "phone": self.mobile,
                "email": self.email,
                "supplier_rank": 1,
            }
            if "mobile" in self.env["res.partner"]._fields:
                partner_vals["mobile"] = self.mobile
            partner = self.env["res.partner"].create(partner_vals)
        values = {
            "name": self.legal_name or self.name,
            "lead_id": self.lead_id.id,
            "profile_id": self.id,
            "hot_zone_id": self.hot_zone_id.id,
            "geo_primary": self.geo_primary,
            "contact_person": self.contact_person,
            "contact_mobile": self.mobile,
            "contact_email": self.email,
            "stage_id": stage.id if stage else False,
            "partner_id": partner.id,
            "vendor_partner_id": partner.id,
        }
        if self.env.context.get("vendor_partner_id"):
            values["vendor_partner_id"] = self.env.context["vendor_partner_id"]
        return values

    def _ensure_default_checklist(self):
        templates = self.env["rmc.subcontractor.checklist.template"].search([])
        for profile in self:
            for template in templates:
                existing = profile.checklist_line_ids.filtered(lambda line: line.name == template.name)
                if existing:
                    continue
                self.env["rmc.subcontractor.profile.checklist"].create(
                    {
                        "profile_id": profile.id,
                        "name": template.name,
                        "required": template.required,
                        "weight": template.weight,
                    }
                )


class RmcSubcontractorProfileChecklist(models.Model):
    _name = "rmc.subcontractor.profile.checklist"
    _description = "Profile Checklist Item"

    profile_id = fields.Many2one("rmc.subcontractor.profile", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    completed = fields.Boolean()
    required = fields.Boolean(default=True)
    weight = fields.Float(default=1.0)


class RmcSubcontractorChecklistTemplate(models.Model):
    _name = "rmc.subcontractor.checklist.template"
    _description = "Subcontractor Checklist Template"

    name = fields.Char(required=True)
    required = fields.Boolean(default=True)
    weight = fields.Float(default=1.0)


class RmcSubcontractorPlantPlaceholder(models.Model):
    _name = "rmc.subcontractor.plant.placeholder"
    _description = "Onboarding Plant Placeholder"

    profile_id = fields.Many2one("rmc.subcontractor.profile", required=True, ondelete="cascade")
    name = fields.Char(required=True, default=lambda self: _("Plant"))
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
        ],
        default="draft",
    )
    plant_id = fields.Many2one("rmc.subcontractor.plant")


class RmcSubcontractorGeoArea(models.Model):
    _name = "rmc.subcontractor.geo.area"
    _description = "Subcontractor Geo Area"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    is_primary = fields.Boolean()
    hot_zone_id = fields.Many2one("rmc.subcontractor.hot.zone")


class RmcSubcontractorHotZone(models.Model):
    _name = "rmc.subcontractor.hot.zone"
    _description = "Hot Zone"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    auto_priority = fields.Boolean(default=True)
    color = fields.Integer()
