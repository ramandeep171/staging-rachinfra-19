from odoo import http, _
from odoo.http import request


class SubcontractorWebsite(http.Controller):
    @http.route("/subcontractor", type="http", auth="public", website=True, sitemap=True)
    def subcontractor_landing(self, **kwargs):
        calculator_defaults = {
            "city": kwargs.get("city", ""),
            "capacity": kwargs.get("capacity", 60),
            "mixers": kwargs.get("mixers", 3),
        }
        values = {
            "calculator_defaults": calculator_defaults,
        }
        return request.render("rmc_subcontractor_management.website_subcontractor_landing", values)

    @http.route("/subcontractor/lead", type="http", auth="public", website=True, csrf=True, methods=["POST"])
    def subcontractor_lead_submit(self, **post):
        name = post.get("name")
        mobile = post.get("mobile")
        city = post.get("city")
        if not (name and mobile and city):
            return request.redirect("/subcontractor?error=missing")
        lead_vals = {
            "name": _("Subcontractor Inquiry - %s") % name,
            "contact_name": name,
            "phone": mobile,
            "subcontractor_city": city,
            "description": _("Captured from subcontractor landing page."),
            "type": "lead",
            "is_subcontractor_lead": True,
        }
        lead = request.env["crm.lead"].sudo().create(lead_vals)
        token = lead.subcontractor_token_id
        thankyou_values = {
            "lead": lead,
            "token_url": token and token.access_url or "",
        }
        return request.render("rmc_subcontractor_management.website_subcontractor_thankyou", thankyou_values)

    @http.route(
        "/subcontractor/more-info/<string:token>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET", "POST"],
    )
    def subcontractor_more_info(self, token, **post):
        token_rec = request.env["rmc.subcontractor.portal.token"].sudo().search([("name", "=", token)], limit=1)
        if not token_rec or not token_rec.is_valid():
            return request.render("rmc_subcontractor_management.website_subcontractor_token_invalid")
        token_rec.mark_accessed()
        lead = token_rec.lead_id.sudo()
        if request.httprequest.method == "POST":
            cleaned = self._extract_profile_values(post)
            profile = lead.subcontractor_profile_id or request.env["rmc.subcontractor.profile"].sudo().create(
                {"lead_id": lead.id, "name": cleaned["legal_name"] or lead.contact_name or lead.name}
            )
            totals_fields = ["plants_total", "mixers_total", "pumps_total"]
            totals_submitted = {field: cleaned.get(field, 0) for field in totals_fields}
            if profile.portal_totals_locked:
                for field in totals_fields:
                    cleaned.pop(field, None)
            profile.sudo().write(cleaned)
            if (
                not profile.portal_totals_locked
                and any(totals_submitted.get(field) for field in totals_fields)
            ):
                profile.sudo().write({"portal_totals_locked": True})
            token_rec.write({"profile_id": profile.id, "state": "profile"})
            if lead.type != "opportunity":
                lead = lead.sudo()
                lead.write({"type": "lead"})
                convert_result = lead.convert_opportunity(lead.partner_id.id if lead.partner_id else False)
                lead_ids = []
                if isinstance(convert_result, dict):
                    lead_ids = convert_result.get("lead_ids") or []
                new_opp = request.env["crm.lead"].sudo().browse(lead_ids)
                if new_opp:
                    new_opp.write({"team_id": lead.team_id.id, "is_subcontractor_lead": True})
                    token_rec.write({"state": "lead"})
                    lead = new_opp[0]
                    token_rec.write({"lead_id": lead.id})
                    profile.sudo().write({"lead_id": lead.id})
                    lead.sudo().write({"subcontractor_profile_id": profile.id})
            lead.action_create_subcontractor()
            return request.render(
                "rmc_subcontractor_management.website_subcontractor_moreinfo_success",
                {"lead": lead, "profile": lead.subcontractor_profile_id},
            )
        values = {
            "lead": lead,
            "token": token_rec,
            "profile": lead.subcontractor_profile_id,
        }
        return request.render("rmc_subcontractor_management.website_subcontractor_moreinfo", values)

    def _extract_profile_values(self, data):
        fields_map = [
            "legal_name",
            "brand_trade_name",
            "gstin",
            "pan",
            "msme_udyam",
            "city",
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
            "plant_details",
            "mixer_details",
            "pump_details",
            "base_pricing_note",
            "cut_percent",
            "mgq_per_month_m3",
            "rental_amount",
            "pricing_terms",
        ]
        result = {}
        for field in fields_map:
            if field in ("plants_total", "mixers_total", "pumps_total"):
                result[field] = int(data.get(field, 0) or 0)
            elif field in ("service_radius_km", "cut_percent", "mgq_per_month_m3"):
                result[field] = float(data.get(field, 0.0) or 0.0)
            elif field == "established_year":
                year = data.get(field)
                result[field] = int(year) if year else False
            else:
                result[field] = data.get(field)
        return result
