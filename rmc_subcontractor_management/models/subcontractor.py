from datetime import timedelta
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class RmcSubcontractor(models.Model):
    _inherit = ["rmc.subcontractor", "mail.thread", "mail.activity.mixin"]

    subc_code = fields.Char(
        string="Subcontractor Code",
        related="subcontractor_code",
        store=True,
        readonly=True,
    )
    stage_id = fields.Many2one(
        "rmc.subcontractor.stage",
        string="Pipeline Stage",
        tracking=True,
        group_expand="_read_group_stage_ids",
        default=lambda self: self.env.ref(
            "rmc_subcontractor_management.stage_subc_new",
            raise_if_not_found=False,
        ),
    )
    lead_id = fields.Many2one("crm.lead", string="Lead", ondelete="set null")
    opportunity_id = fields.Many2one(
        "crm.lead",
        string="Opportunity",
        domain="[('type','=','opportunity')]",
        ondelete="set null",
    )
    profile_id = fields.Many2one("rmc.subcontractor.profile", ondelete="set null")
    vendor_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Vendor Partner",
        domain="[('supplier_rank','>=',0)]",
        tracking=True,
    )
    geo_primary = fields.Char()
    hot_zone_id = fields.Many2one("rmc.subcontractor.hot.zone", tracking=True)
    compliance_partial_percent = fields.Float(default=0.0)
    compliance_complete_percent = fields.Float(default=0.0)
    checklist_progress = fields.Float(compute="_compute_checklist_progress", store=True)
    auto_priority_score = fields.Float(
        compute="_compute_auto_priority",
        store=True,
        help="Automatically calculated score based on capacity and fleet size.",
    )
    has_high_capacity = fields.Boolean(compute="_compute_auto_priority", store=True)
    has_large_fleet = fields.Boolean(compute="_compute_auto_priority", store=True)
    code_locked = fields.Boolean(compute="_compute_code_locked", store=True)
    plant_count = fields.Integer(compute="_compute_related_counts")
    mixer_count = fields.Integer(compute="_compute_related_counts")
    pump_count = fields.Integer(compute="_compute_related_counts")
    purchase_agreement_id = fields.Many2one("purchase.requisition", string="Purchase Agreement", copy=False)
    more_info_token_id = fields.Many2one("rmc.subcontractor.portal.token", string="Portal Token")
    log_ids = fields.One2many("rmc.profile.log", "subcontractor_id")
    asset_ids = fields.One2many("rmc.subcontractor.asset", "subcontractor_id")
    portal_user_id = fields.Many2one("res.users", string="Portal User")
    profile_checklist_ids = fields.One2many(
        "rmc.subcontractor.profile.checklist",
        compute="_compute_profile_checklist",
        string="Checklist Items",
        readonly=True,
    )

    _sql_constraints = [
        ("unique_subcontractor_code_new", "unique(subcontractor_code)", "Subcontractor code must be unique."),
    ]

    @api.depends("plant_ids", "plant_ids.mixer_ids", "plant_ids.pump_ids")
    def _compute_related_counts(self):
        for record in self:
            record.plant_count = len(record.plant_ids)
            record.mixer_count = sum(len(plant.mixer_ids) for plant in record.plant_ids)
            record.pump_count = sum(len(plant.pump_ids) for plant in record.plant_ids)

    @api.depends("checklist_progress", "stage_id.auto_lock_codes")
    def _compute_code_locked(self):
        for record in self:
            record.code_locked = bool(record.stage_id and record.stage_id.auto_lock_codes)

    @api.depends("plant_ids.capacity", "plant_ids.capacity_m3ph", "plant_ids.mixer_ids", "plant_ids.pump_ids")
    def _compute_auto_priority(self):
        for record in self:
            total_capacity = sum(
                plant.capacity_m3ph or plant.capacity or 0.0 for plant in record.plant_ids
            )
            total_mixers = sum(len(plant.mixer_ids) for plant in record.plant_ids)
            record.has_high_capacity = total_capacity >= 60
            record.has_large_fleet = total_mixers >= 10
            record.auto_priority_score = (total_capacity / 10.0) + (total_mixers * 2)

    @api.depends("compliance_partial_percent", "compliance_complete_percent")
    def _compute_checklist_progress(self):
        for record in self:
            record.checklist_progress = max(record.compliance_partial_percent, record.compliance_complete_percent)

    @api.depends("profile_id", "profile_id.checklist_line_ids", "profile_id.checklist_line_ids.completed")
    def _compute_profile_checklist(self):
        for record in self:
            record.profile_checklist_ids = record.profile_id.checklist_line_ids

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for subcontractor, vals in zip(result, vals_list):
            geo = subcontractor.geo_primary or vals.get("geo_primary") or "GEN"
            code = subcontractor._next_subcontractor_code(geo)
            subcontractor.write({"subcontractor_code": code})
            subcontractor._sync_profile_links()
            if subcontractor.stage_id and subcontractor.stage_id.mail_template_id:
                subcontractor._send_stage_mail(subcontractor.stage_id.mail_template_id)
        return result

    def write(self, vals):
        stage_changed = "stage_id" in vals
        previous_stage = {rec.id: rec.stage_id for rec in self}
        res = super().write(vals)
        if "profile_id" in vals or "lead_id" in vals or "opportunity_id" in vals:
            for record in self:
                record._sync_profile_links()
        if stage_changed:
            for record in self:
                old_stage = previous_stage.get(record.id)
                if old_stage != record.stage_id:
                    record._handle_stage_transition(old_stage, record.stage_id)
        return res

    def _next_subcontractor_code(self, geo):
        ctx = dict(self.env.context, subc_geo=geo[:3].upper())
        return self.env["ir.sequence"].with_context(ctx).next_by_code("rmc.subcontractor.code") or "SUBC-%s-%s" % (
            ctx["subc_geo"],
            fields.Date.context_today(self).strftime("%y"),
        )

    def _sync_profile_links(self):
        for record in self:
            if record.profile_id:
                updates = {}
                if not record.lead_id and record.profile_id.lead_id:
                    updates["lead_id"] = record.profile_id.lead_id.id
                if record.profile_id.hot_zone_id and record.hot_zone_id != record.profile_id.hot_zone_id:
                    updates["hot_zone_id"] = record.profile_id.hot_zone_id.id
                if record.profile_id.geo_primary and record.geo_primary != record.profile_id.geo_primary:
                    updates["geo_primary"] = record.profile_id.geo_primary
                if updates:
                    record.write(updates)

    def _handle_stage_transition(self, old_stage, new_stage):
        for record in self:
            message = _("Stage changed from %(old)s to %(new)s by %(user)s") % {
                "old": old_stage.name if old_stage else _("Undefined"),
                "new": new_stage.name if new_stage else _("Undefined"),
                "user": self.env.user.display_name,
            }
            self.env["rmc.profile.log"].create(
                {
                    "subcontractor_id": record.id,
                    "profile_id": record.profile_id.id if record.profile_id else False,
                    "message": message,
                    "activity": "stage",
                }
            )
            if new_stage and new_stage.mail_template_id:
                record._send_stage_mail(new_stage.mail_template_id)
            if new_stage and new_stage.code == "approved":
                record._ensure_purchase_agreement()

    def _send_stage_mail(self, template):
        template.sudo().send_mail(self.id, force_send=False)

    def _ensure_purchase_agreement(self):
        for record in self:
            if record.purchase_agreement_id:
                continue
            if not record.vendor_partner_id:
                raise UserError(_("Please link a vendor partner before generating the Purchase Agreement."))
            requisition_type = self.env.ref("purchase_requisition.type_single", raise_if_not_found=False)
            if not requisition_type:
                _logger.warning(
                    "Skipping purchase agreement generation for subcontractor %s: requisition type not found.",
                    record.display_name,
                )
                continue
            requisition = self.env["purchase.requisition"].create(
                {
                    "name": "%s - Blanket Order" % record.subcontractor_code,
                    "type_id": requisition_type.id,
                    "schedule_date": fields.Date.today(),
                    "vendor_id": record.vendor_partner_id.id,
                    "origin": record.subcontractor_code,
                    "description": _("Auto-generated blanket order for subcontractor onboarding."),
                }
            )
            record.purchase_agreement_id = requisition.id

    @api.model
    def _read_group_stage_ids(self, stages, domain, orderby=None):
        ordering = orderby or "sequence, id"
        return stages.search([("active", "=", True)], order=ordering)

    def action_create_vendor_partner(self):
        self.ensure_one()
        if self.vendor_partner_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "res.partner",
                "res_id": self.vendor_partner_id.id,
                "view_mode": "form",
            }
        partner = self.env["res.partner"].create(
            {
                "name": self.name,
                "phone": self.contact_mobile,
                "mobile": self.contact_mobile,
                "email": self.contact_email,
                "type": "contact",
                "supplier_rank": 1,
                "company_type": "company",
            }
        )
        self.vendor_partner_id = partner.id
        self.partner_id = partner.id  # keep legacy link in sync
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": partner.id,
            "view_mode": "form",
        }

    def ensure_vendor_partner(self):
        self.ensure_one()
        if self.vendor_partner_id:
            return self.vendor_partner_id
        partner = self.env["res.partner"].create(
            {
                "name": self.name,
                "phone": self.contact_mobile,
                "mobile": self.contact_mobile,
                "email": self.contact_email,
                "type": "contact",
                "supplier_rank": 1,
                "company_type": "company",
            }
        )
        self.vendor_partner_id = partner.id
        self.partner_id = partner.id
        return partner

    def action_generate_plant_codes(self):
        self.ensure_one()
        for plant in self.plant_ids:
            plant.ensure_plant_code()
        return True

    def action_generate_purchase_agreement(self):
        self.ensure_one()
        self._ensure_purchase_agreement()
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.requisition",
            "res_id": self.purchase_agreement_id.id,
            "view_mode": "form",
        }

    def action_open_status_page(self):
        self.ensure_one()
        token = self.more_info_token_id or self.env["rmc.subcontractor.portal.token"].create(
            {
                "subcontractor_id": self.id,
                "profile_id": self.profile_id.id if self.profile_id else False,
                "expiration": fields.Datetime.now() + timedelta(days=2),
                "state": "portal",
            }
        )
        self.more_info_token_id = token.id
        url = "/subcontractor/status/%s" % token.name
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": url,
        }

    @api.model
    def cron_phase_two_reminder(self):
        cutoff = fields.Datetime.now() - timedelta(hours=48)
        stage_partial = self.env.ref(
            "rmc_subcontractor_management.stage_subc_docs_partial",
            raise_if_not_found=False,
        )
        if not stage_partial:
            return
        records = self.search(
            [
                ("stage_id", "=", stage_partial.id),
                ("write_date", "<", cutoff),
            ]
        )
        template = self.env.ref(
            "rmc_subcontractor_management.mail_template_subcontractor_docs_reminder",
            raise_if_not_found=False,
        )
        for subcontractor in records:
            if template:
                template.sudo().send_mail(subcontractor.id, force_send=False)
            self.env["rmc.profile.log"].create(
                {
                    "subcontractor_id": subcontractor.id,
                    "profile_id": subcontractor.profile_id.id if subcontractor.profile_id else False,
                    "message": _("48h reminder for pending Phase-2 requirements."),
                    "activity": "reminder",
                }
            )

    @api.model
    def cron_stage_idle_reminder(self):
        cutoff = fields.Datetime.now() - timedelta(days=5)
        stage_active = self.env.ref("rmc_subcontractor_management.stage_subc_active", raise_if_not_found=False)
        stage_ids = stage_active.ids if stage_active else []
        records = self.search(
            [
                ("stage_id", "not in", stage_ids),
                ("write_date", "<", cutoff),
            ]
        )
        for subcontractor in records:
            subcontractor.message_post(
                body=_("Reminder: Stage has not progressed in the last 5 days."),
            )
