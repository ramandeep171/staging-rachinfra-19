try:  # pragma: no cover - allows running tests without optional deps
    from dateutil.relativedelta import relativedelta
except ModuleNotFoundError:  # pragma: no cover
    from odoo_shims.relativedelta import relativedelta

import base64
import io
import logging
import textwrap

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager

try:  # pragma: no cover - optional dependency in some test envs
    from reportlab.lib.pagesizes import letter as rl_letter
    from reportlab.pdfgen import canvas as rl_canvas
except ModuleNotFoundError:  # pragma: no cover
    rl_letter = None
    rl_canvas = None

_logger = logging.getLogger(__name__)


class GearOnRentPortal(http.Controller):
    """Portal routes for Gear On Rent clients."""

    @http.route("/my/gear-on-rent", type="http", auth="user", website=True)
    def my_gear_on_rent(self, **kwargs):
        partner = request.env.user.partner_id.commercial_partner_id
        SaleOrder = request.env["sale.order"].sudo()
        order_domain = [
            ("partner_id", "child_of", partner.id),
            ("x_billing_category", "in", ["rental", "rmc"]),
            ("state", "in", ["sale", "done"]),
        ]
        orders = SaleOrder.search(order_domain)
        Monthly = request.env["gear.rmc.monthly.order"].sudo()
        monthly_orders = Monthly.search(
            [("so_id.partner_id", "child_of", partner.id)],
            order="date_start desc",
            limit=12,
        )
        if not orders and not monthly_orders:
            return request.redirect("/my")
        monthly_summary = []
        for mwo in monthly_orders:
            monthly_summary.append(
                {
                    "name": mwo.display_name,
                    "start": mwo.date_start,
                    "end": mwo.date_end,
                    "prime_output": mwo.prime_output_qty,
                    "optimized_standby": mwo.optimized_standby_qty,
                    "ngt_relief": mwo.downtime_relief_qty,
                    "ngt_hours": mwo.ngt_hours,
                    "loto_hours": mwo.waveoff_hours_chargeable,
                    "excess_diesel": mwo.excess_diesel_litre_total,
                    "state": mwo.state,
                }
            )
        values = {
            "page_name": "gear_on_rent_dashboard",
            "orders": orders,
            "monthly_orders": monthly_summary,
        }
        return request.render("gear_on_rent.portal_gear_on_rent_dashboard", values)

    @http.route("/my/gear-on-rent/reconciliations", type="http", auth="user", website=True)
    def gear_on_rent_reconciliations(self, **kwargs):
        partner = request.env.user.partner_id.commercial_partner_id
        Recon = request.env["gear.rmc.annual.reconciliation"].sudo()
        domain = [("so_id.partner_id", "child_of", partner.id)]
        reconciliations = Recon.search(domain, order="fiscal_year_start desc")
        values = {
            "page_name": "gear_on_rent_reconciliation",
            "reconciliations": reconciliations,
        }
        return request.render("gear_on_rent.portal_gear_on_rent_reconciliation", values)

    @http.route("/my/gear-on-rent/reconciliations/<int:recon_id>/export", type="http", auth="user", website=True)
    def gear_on_rent_reconciliation_export(self, recon_id, **kwargs):
        partner = request.env.user.partner_id.commercial_partner_id
        recon = request.env["gear.rmc.annual.reconciliation"].sudo().browse(recon_id)
        if not recon or recon.so_id.partner_id not in (partner | partner.child_ids):
            return request.not_found()
        # XLSX export stub: return a simple response for now
        content = "FY grid export placeholder for %s" % (recon.name,)
        return request.make_response(
            content,
            headers={
                "Content-Type": "text/plain;charset=utf-8",
                "Content-Disposition": "attachment; filename=reconciliation_%s.txt" % recon.name,
            },
        )

    @http.route(
        "/gear_on_rent/quote_request",
        type="http",
        auth="user",
        website=True,
    )
    def gear_on_rent_quote_request(
        self,
        product_id=None,
        amount=None,
        equipment=None,
        details=None,
        **kwargs,
    ):
        if not product_id:
            return request.redirect("/gear-on-rent")

        try:
            product = request.env["product.product"].sudo().browse(int(product_id))
        except (TypeError, ValueError):
            product = request.env["product.product"].sudo()

        if not product or not product.exists():
            return request.redirect("/gear-on-rent")

        partner = request.env.user.partner_id.commercial_partner_id
        if not partner:
            return request.redirect("/gear-on-rent")

        amount_float = 0.0
        try:
            amount_float = float(amount)
        except (TypeError, ValueError):
            amount_float = 0.0
        if amount_float <= 0.0:
            amount_float = product.lst_price

        pricelist = partner.property_product_pricelist
        addresses = partner.address_get(["delivery", "invoice"])

        rental_type = kwargs.get("rental_type")
        duration_type = kwargs.get("duration_type")
        duration_value = kwargs.get("duration")
        project_duration = kwargs.get("project_duration")
        production_volume = kwargs.get("production_volume")

        start_date = fields.Datetime.now()
        delta = relativedelta(days=1)

        try:
            duration_float = float(duration_value or 0)
        except (TypeError, ValueError):
            duration_float = 0.0

        try:
            project_duration_float = float(project_duration or 0)
        except (TypeError, ValueError):
            project_duration_float = 0.0

        try:
            production_volume_float = float(production_volume or 0)
        except (TypeError, ValueError):
            production_volume_float = 0.0

        if rental_type == "hourly":
            if (duration_type or "hourly") == "daily" and duration_float > 0:
                delta = relativedelta(days=duration_float)
            elif duration_float > 0:
                delta = relativedelta(hours=duration_float)
        elif rental_type == "production" and project_duration_float > 0:
            delta = relativedelta(days=project_duration_float)

        return_date = start_date + delta

        notes = []
        if details:
            notes.append(details)
        if kwargs.get("include_operator"):
            notes.append("Includes operator")
        if kwargs.get("include_maintenance"):
            notes.append("Includes premium maintenance package")
        if rental_type == "hourly" and duration_float:
            unit = 'days' if (duration_type or 'hourly') == 'daily' else 'hours'
            duration_label = int(duration_float) if float(duration_float).is_integer() else duration_float
            notes.append(f"Duration: {duration_label} {unit}")
        if rental_type == "production" and project_duration_float:
            proj_label = int(project_duration_float) if float(project_duration_float).is_integer() else project_duration_float
            notes.append(f"Project duration: {proj_label} days")
        if rental_type == "production" and production_volume_float:
            volume_label = int(production_volume_float) if float(production_volume_float).is_integer() else production_volume_float
            notes.append(f"Production volume: {volume_label} m3")

        user = request.env.user
        tz_start = fields.Datetime.context_timestamp(user, start_date) if start_date else False
        tz_return = fields.Datetime.context_timestamp(user, return_date) if return_date else False
        start_display = tz_start.strftime('%Y-%m-%d %H:%M') if tz_start else ''
        return_display = tz_return.strftime('%Y-%m-%d %H:%M') if tz_return else ''
        if start_display and return_display:
            notes.append(f"Rental window: {start_display} -> {return_display}")

        note_text = "\n".join(filter(None, notes))

        amount_display = f"INR {int(round(amount_float)):,}"

        lead = False
        rental_team = request.env.ref("gear_on_rent.crm_team_rental", raise_if_not_found=False)
        Lead = request.env["crm.lead"].sudo()
        if rental_team:
            visitor_env = request.env["website.visitor"].sudo()
            visitor = visitor_env._get_visitor_from_request(request)
            if visitor and hasattr(visitor_env, "create_lead_from_page_visit"):
                try:
                    lead = visitor_env.create_lead_from_page_visit(visitor, rental_team.id, "/gear-on-rent")
                except Exception:
                    lead = False
        if not lead and rental_team:
            lead = Lead.search(
                [
                    ("team_id", "=", rental_team.id),
                    ("partner_id", "=", partner.id),
                ],
                order="create_date desc",
                limit=1,
            )
        if not lead and rental_team:
            lead_vals = {
                "name": f"Rental Estimate - {equipment or product.display_name}",
                "team_id": rental_team.id,
                "type": "lead",
                "partner_id": partner.id,
                "contact_name": partner.name,
                "email_from": partner.email,
                "phone": partner.phone or getattr(partner, "mobile", False),
                "description": note_text or details,
                "referred": "/gear-on-rent",
            }
            lead = Lead.create(lead_vals)
        if lead:
            lead = lead.sudo()
            if partner and (not lead.partner_id or lead.partner_id != partner):
                lead.write({"partner_id": partner.id})
            if lead.type != "opportunity":
                try:
                    lead.convert_opportunity(lead.partner_id or partner)
                except Exception:
                    lead.write({"type": "opportunity"})

        order_vals = {
            "partner_id": partner.id,
            "partner_invoice_id": addresses.get("invoice", partner.id),
            "partner_shipping_id": addresses.get("delivery", partner.id),
            "pricelist_id": pricelist.id if pricelist else False,
            "origin": "Gear On Rent Website Estimate",
            "x_billing_category": "rental",
            "note": note_text,
            "rental_start_date": start_date,
            "rental_return_date": return_date,
            "is_rental_order": True,
            "opportunity_id": lead.id if lead else False,
            "team_id": lead.team_id.id if lead and lead.team_id else False,
        }
        order = request.env["sale.order"].with_context(in_rental_app=True).sudo().create(order_vals)

        request.env["sale.order.line"].with_context(in_rental_app=True).sudo().create({
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1.0,
            "price_unit": amount_float,
            "name": equipment or product.display_name,
            "is_rental": True,
            "start_date": start_date,
            "return_date": return_date,
        })

        if lead:
            lead.message_post(body=f"Estimator quotation created: {order.name}")
        order.message_post(body="Generated from Gear On Rent estimator on website.")

        if order.state == "draft":
            try:
                order.action_quotation_sent()
            except Exception:
                _logger.exception("Unable to mark estimator quotation %s as sent", order.name)

        report_service = request.env["ir.actions.report"].sudo()
        filename = f"{order.name.replace('/', '_')}_quotation.pdf"
        pdf_bytes = None
        try:
            pdf_bytes, _ = report_service._render_qweb_pdf("sale.action_report_saleorder", [order.id])
        except UserError:
            pdf_bytes = self._render_basic_estimate_pdf(
                order,
                equipment or product.display_name,
                amount_display,
                start_display,
                return_display,
                note_text,
            )
        except Exception:
            pdf_bytes = None

        if pdf_bytes:
            headers = {
                "Content-Type": "application/pdf",
                "Content-Length": len(pdf_bytes),
                "Content-Disposition": f"attachment; filename={filename}",
            }
            return request.make_response(pdf_bytes, headers=headers)

        values = {
            "order": order,
            "product": product,
            "amount": amount_float,
            "details": details,
            "equipment": equipment or product.display_name,
            "amount_display": amount_display,
            "start_date": start_display,
            "return_date": return_display,
        }
        return request.render("gear_on_rent.quote_request_success", values)

    def _render_basic_estimate_pdf(
        self,
        order,
        equipment_label,
        amount_display,
        start_display,
        return_display,
        note_text,
    ):
        """Provide a minimal PDF when wkhtmltopdf is unavailable."""
        if not rl_canvas or not rl_letter:
            return None

        buffer = io.BytesIO()
        pdf = rl_canvas.Canvas(buffer, pagesize=rl_letter)
        _, page_height = rl_letter
        cursor_y = page_height - 60

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(40, cursor_y, "Rental Estimate")
        cursor_y -= 30

        pdf.setFont("Helvetica", 11)
        summary_lines = [
            f"Quotation: {order.name or 'Draft'}",
            f"Customer: {order.partner_id.display_name or ''}",
            f"Equipment: {equipment_label}",
            f"Estimated Amount: {amount_display}",
        ]
        if start_display and return_display:
            summary_lines.append(f"Rental Window: {start_display} -> {return_display}")

        for line in summary_lines:
            if not line.strip():
                continue
            pdf.drawString(40, cursor_y, line)
            cursor_y -= 18

        if note_text:
            cursor_y -= 10
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(40, cursor_y, "Estimator Details")
            cursor_y -= 18
            pdf.setFont("Helvetica", 10)
            for raw_line in note_text.splitlines():
                wrapped = textwrap.wrap(raw_line, width=88) or [""]
                for wrap_line in wrapped:
                    if cursor_y < 60:
                        pdf.showPage()
                        pdf.setFont("Helvetica", 10)
                        cursor_y = page_height - 60
                    pdf.drawString(45, cursor_y, wrap_line)
                    cursor_y -= 14

        pdf.save()
        buffer.seek(0)
        return buffer.read()

    # ------------------------------------------------------------------
    # Batching plant portal (new flow only)
    # ------------------------------------------------------------------
    def _bp_get_partner(self):
        return request.env.user.partner_id.commercial_partner_id

    def _bp_get_order(self, order_id):
        partner = self._bp_get_partner()
        order = request.env["sale.order"].sudo().browse(int(order_id))
        if (
            not order
            or not order.exists()
            or order.x_billing_category != "plant"
            or order.partner_id not in (partner | partner.child_ids)
        ):
            return None
        return order

    def _bp_encode_chart(self, path):
        if not path:
            return None
        if isinstance(path, str) and path.startswith("data:image"):
            return path
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            encoded = base64.b64encode(data).decode("ascii")
            return f"data:image/png;base64,{encoded}"
        except FileNotFoundError:
            return None

    @http.route("/my/batching-plant", type="http", auth="user", website=True)
    def portal_batching_quotes(self, **kwargs):
        partner = self._bp_get_partner()
        page = int(kwargs.get("page", 1)) if str(kwargs.get("page", "1")).isdigit() else 1
        page_size = 10

        SaleOrder = request.env["sale.order"].sudo()
        domain = [
            ("partner_id", "child_of", partner.id),
            ("x_billing_category", "=", "plant"),
        ]

        order_count = SaleOrder.search_count(domain)
        pager = portal_pager(
            url="/my/batching-plant",
            total=order_count,
            page=page,
            step=page_size,
        )

        orders = SaleOrder.search(
            domain,
            order="create_date desc",
            limit=page_size,
            offset=pager.get("offset", 0),
        )

        calculator = request.env["gear.batching.quotation.calculator"].sudo()
        display_rates = {}
        for order in orders:
            try:
                final_rates = calculator.generate_final_rates(order)
            except Exception:
                final_rates = {}

            if order.x_inventory_mode == "with_inventory":
                rate = (
                    order.gear_total_per_cum_rate
                    or final_rates.get("total_rate_per_cum")
                    or final_rates.get("total_per_cum")
                    or final_rates.get("base_plant_rate")
                )
            else:
                rate = (
                    order.gear_prime_rate_final
                    or final_rates.get("final_prime_rate")
                    or final_rates.get("prime_rate_final")
                    or final_rates.get("prime_rate")
                )

            display_rates[order.id] = rate

        values = {
            "page_name": "portal_batching_quotes",
            "orders": orders,
            "pager": pager,
            "display_rates": display_rates,
        }
        return request.render("gear_on_rent.portal_batching_quote_list", values)

    @http.route("/my/batching-plant/<int:order_id>", type="http", auth="user", website=True)
    def portal_batching_quote_detail(self, order_id, **kwargs):
        order = self._bp_get_order(order_id)
        if not order:
            return request.not_found()

        pdf_helper = request.env["gear.batching.quotation.pdf"].sudo()
        pdf_data = pdf_helper.prepare_pdf_assets(order)
        chart_urls = {
            key: self._bp_encode_chart(path) for key, path in pdf_data.get("charts", {}).items()
        }

        final_rates = pdf_data.get("final_rates", {})
        rate_breakdown = final_rates.get("full_rate_breakdown", {})
        optional_services = rate_breakdown.get("optional_services", [])

        material_breakdown = {}
        if order.x_inventory_mode == "with_inventory":
            material_breakdown = self._bp_material_breakdown(order)

        capex_breakdown = pdf_data.get("capex_breakdown") or {}
        if not capex_breakdown and order.gear_civil_scope == "vendor":
            capex_breakdown = pdf_helper._build_capex_breakdown(order, final_rates)
        if not capex_breakdown and order.gear_dead_cost_amount:
            capex_breakdown = {
                "total_amount": order.gear_dead_cost_amount,
                "dead_cost_per_cum": final_rates.get("dead_cost", 0.0),
                "items": [],
            }

        values = {
            "page_name": "portal_batching_quote_detail",
            "order": order,
            "pdf_data": pdf_data,
            "chart_urls": chart_urls,
            "final_rates": final_rates,
            "optional_services": optional_services,
            "material_breakdown": material_breakdown,
            "capex_breakdown": capex_breakdown,
        }
        return request.render("gear_on_rent.portal_batching_quote_detail", values)

    @http.route(
        ["/my/batching-plant/<int:quote_id>/pdf", "/my/batching-plant/<int:order_id>/pdf"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_batching_quote_pdf(self, order_id=None, quote_id=None, **kwargs):
        order_id = order_id or quote_id
        order = self._bp_get_order(order_id)
        if not order:
            return request.not_found()

        pdf_helper = request.env["gear.batching.quotation.pdf"].sudo()
        pdf_data = pdf_helper.prepare_pdf_assets(order)

        chart_urls = {
            key: self._bp_encode_chart(path) for key, path in pdf_data.get("charts", {}).items()
        }

        report_action = request.env.ref("gear_on_rent.action_report_batching_plant_quote", raise_if_not_found=False)
        if not report_action:
            return request.not_found()

        report_data = {
            "pdf_data": pdf_data,
            "chart_urls": chart_urls,
            "dead_cost": pdf_data.get("dead_cost_context") or {
                "per_cum": pdf_data.get("dead_cost") or 0.0,
                "total": (pdf_data.get("capex_breakdown") or {}).get("total_amount") or 0.0,
            },
        }
        pdf_content, _ = report_action._render_qweb_pdf(report_action.id, [order.id], data=report_data)
        filename = f"{order.name.replace('/', '_')}_batching_quote.pdf"
        headers = {
            "Content-Type": "application/pdf",
            "Content-Length": len(pdf_content),
            "Content-Disposition": f"attachment; filename={filename}",
        }
        return request.make_response(pdf_content, headers=headers)

    @http.route(
        "/my/batching-plant/<int:order_id>/accept",
        type="http",
        auth="user",
        methods=["POST"],
        website=True,
    )
    def portal_batching_quote_accept(self, order_id, **kwargs):
        order = self._bp_get_order(order_id)
        if not order:
            return request.not_found()

        so = order.sudo().action_accept_and_create_so()
        if so:
            return request.redirect(f"/my/orders/{so.id}")
        return request.redirect(f"/my/batching-plant/{order.id}")

    def _bp_material_breakdown(self, order):
        calculator = request.env["gear.batching.quotation.calculator"].sudo()

        design = order.gear_design_mix_id
        if not design:
            return {}

        bom_quantities = calculator._extract_bom_materials(design) if hasattr(calculator, "_extract_bom_materials") else {}

        def _qty(key, fallback):
            return bom_quantities.get(key, fallback or 0.0)

        cement_qty = _qty("cement_qty", getattr(design, "cement_qty", 0.0))
        agg10_qty = _qty("agg_10mm_qty", getattr(design, "agg_10mm_qty", 0.0))
        agg20_qty = _qty("agg_20mm_qty", getattr(design, "agg_20mm_qty", 0.0))
        admixture_qty = _qty("admixture_qty", getattr(design, "admixture_qty", 0.0))

        def _rate(area, field):
            return getattr(area, field, 0.0) if area else 0.0

        area_override = order.gear_material_area_id
        cement_area = order.gear_cement_area_id or area_override
        agg10_area = order.gear_agg_10mm_area_id or area_override
        agg20_area = order.gear_agg_20mm_area_id or area_override
        admixture_area = order.gear_admixture_area_id or area_override

        cement_rate = _rate(cement_area, "cement_rate")
        agg10_rate = _rate(agg10_area, "agg_10mm_rate")
        agg20_rate = _rate(agg20_area, "agg_20mm_rate")
        admixture_rate = _rate(admixture_area, "admixture_rate")

        cement_total = (cement_qty / 50.0) * cement_rate if cement_qty else 0.0
        agg10_total = (agg10_qty / 1000.0) * agg10_rate if agg10_qty else 0.0
        agg20_total = (agg20_qty / 1000.0) * agg20_rate if agg20_qty else 0.0
        admixture_total = (admixture_qty / 1000.0) * admixture_rate if admixture_qty else 0.0

        return {
            "grade": design.grade,
            "area": area_override or False,
            "lines": [
                {
                    "label": "Cement",
                    "qty": cement_qty,
                    "unit": "kg",
                    "rate": cement_rate,
                    "total": cement_total,
                },
                {
                    "label": "10mm Aggregate",
                    "qty": agg10_qty,
                    "unit": "kg",
                    "rate": agg10_rate,
                    "total": agg10_total,
                },
                {
                    "label": "20mm Aggregate",
                    "qty": agg20_qty,
                    "unit": "kg",
                    "rate": agg20_rate,
                    "total": agg20_total,
                },
                {
                    "label": "Admixture",
                    "qty": admixture_qty,
                    "unit": "ml",
                    "rate": admixture_rate,
                    "total": admixture_total,
                },
            ],
            "total": cement_total + agg10_total + agg20_total + admixture_total,
        }
