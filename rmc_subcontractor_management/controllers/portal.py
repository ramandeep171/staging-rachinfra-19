from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.http import request


class SubcontractorPortal(CustomerPortal):
    @http.route(
        ["/subcontractor/status/<string:token>"],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def subcontractor_status_public(self, token, **kw):
        token_rec = request.env["rmc.subcontractor.portal.token"].sudo().search([("name", "=", token)], limit=1)
        if not token_rec or not token_rec.is_valid():
            return request.render("rmc_subcontractor_management.website_subcontractor_token_invalid")
        record = token_rec.subcontractor_id or (token_rec.profile_id and token_rec.profile_id.subcontractor_id)
        lead = token_rec.lead_id
        values = self._prepare_status_values(record, lead, token_rec)
        return request.render("rmc_subcontractor_management.portal_subcontractor_status", values)

    @http.route(
        ["/my/subcontractor/status"],
        type="http",
        auth="user",
        website=True,
    )
    def subcontractor_status_portal(self, **kw):
        user = request.env.user
        subcontractor = request.env["rmc.subcontractor"].sudo().search([("portal_user_id", "=", user.id)], limit=1)
        if not subcontractor:
            return request.redirect("/my")
        values = self._prepare_status_values(subcontractor, subcontractor.lead_id, None)
        return request.render("rmc_subcontractor_management.portal_subcontractor_status", values)

    def _prepare_status_values(self, subcontractor, lead, token):
        if subcontractor:
            plants = subcontractor.plant_ids
            mixers = subcontractor.mixer_count
            pumps = subcontractor.pump_count
            completion = subcontractor.checklist_progress
            stage = subcontractor.stage_id
        else:
            plants = request.env["rmc.subcontractor.plant"]
            mixers = 0
            pumps = 0
            completion = 0
            stage = False
        return {
            "subcontractor": subcontractor,
            "lead": lead,
            "token": token,
            "plants": plants,
            "mixers": mixers,
            "pumps": pumps,
            "completion": completion,
            "stage": stage,
            "assets": subcontractor.asset_ids if subcontractor else [],
        }
