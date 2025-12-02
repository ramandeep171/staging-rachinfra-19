# -*- coding: utf-8 -*-
import base64
import inspect
import logging

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class GearOnRentWebsite(http.Controller):

    @http.route(['/gear-on-rent'], type='http', auth='public', website=True)
    def gear_on_rent_page(self, **kwargs):
        """Gear on Rent landing page with lead tracking"""
        # Track visitor and create lead
        try:
            visitor = request.env['website.visitor'].sudo()._get_visitor_from_request(request)
            if visitor:
                team = request.env.ref('gear_on_rent.crm_team_rental', raise_if_not_found=False)
                if team:
                    request.env['website.visitor'].sudo().create_lead_from_page_visit(
                        visitor, team.id, '/gear-on-rent'
                    )
        except Exception as e:
            # Log error but don't break the page
            pass
        return self._render_page_response('gear_on_rent.gear_on_rent_landing_page')

    @http.route(['/batching-plant'], type='http', auth='public', website=True)
    def batching_plant_page(self, **kwargs):
        """Batching Plant landing page with lead tracking"""
        Order = request.env['sale.order']
        capacity_model = request.env['gear.plant.capacity.master'].sudo()
        design_model = request.env['gear.design.mix.master'].sudo()
        material_model = request.env['gear.material.area.master'].sudo()

        # Track visitor and create lead
        try:
            visitor = request.env['website.visitor'].sudo()._get_visitor_from_request(request)
            if visitor:
                team = request.env.ref('gear_on_rent.crm_team_rental', raise_if_not_found=False)
                if team:
                    request.env['website.visitor'].sudo().create_lead_from_page_visit(
                        visitor, team.id, '/batching-plant'
                    )
        except Exception as e:
            # Log error but don't break the page
            pass

        values = {
            'service_types': Order._fields['gear_service_type'].selection,
            'inventory_modes': Order._fields['x_inventory_mode'].selection,
            'project_durations': Order._fields['gear_project_duration_years'].selection,
            'civil_scopes': Order._fields['gear_civil_scope'].selection,
            'capacities': capacity_model.search([('active', '=', True)], order='capacity_cum_hour'),
            'design_mixes': design_model.search([('active', '=', True)], order='grade'),
            'material_areas': material_model.search([('active', '=', True)], order='name'),
        }

        values.update(self._page_render_context('gear_on_rent.website_page_batching_plant'))
        return request.render('gear_on_rent.batching_plant_website_page', values)

    @http.route('/batching-plant/submit', type='json', auth='public', website=True)
    def submit_batching_plant_request(self, **kwargs):
        """Handle batching plant form submission"""
        def _to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return False

        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _to_bool(value):
            if isinstance(value, str):
                return value.lower() in ('1', 'true', 'on', 'yes')
            return bool(value)

        # Extract data
        partner_name = kwargs.get('partner_name')
        company_name = kwargs.get('company_name')
        email = kwargs.get('email')
        phone = kwargs.get('phone')
        service_type = kwargs.get('gear_service_type')
        capacity_id = _to_int(kwargs.get('gear_capacity_id'))
        mgq_monthly = _to_float(kwargs.get('mgq_monthly'))
        expected_production = _to_float(kwargs.get('gear_expected_production_qty'))
        inventory_mode = kwargs.get('x_inventory_mode') or 'without_inventory'
        grade_id = _to_int(kwargs.get('gear_design_mix_id')) if inventory_mode == 'with_inventory' else False
        area_id = _to_int(kwargs.get('gear_material_area_id'))
        project_duration_years = kwargs.get('gear_project_duration_years')
        civil_scope = kwargs.get('gear_civil_scope')
        notes = kwargs.get('note')

        transport_rate = _to_float(kwargs.get('gear_transport_per_cum'))
        pump_rate = _to_float(kwargs.get('gear_pump_per_cum'))
        manpower_rate = _to_float(kwargs.get('gear_manpower_per_cum'))
        diesel_rate = _to_float(kwargs.get('gear_diesel_per_cum'))
        jcb_rate = _to_float(kwargs.get('gear_jcb_monthly'))

        transport_opt = _to_bool(kwargs.get('gear_transport_opt_in')) or bool(transport_rate)
        pump_opt = _to_bool(kwargs.get('gear_pumping_opt_in')) or bool(pump_rate)
        manpower_opt = _to_bool(kwargs.get('gear_manpower_opt_in')) or bool(manpower_rate)
        diesel_opt = _to_bool(kwargs.get('gear_diesel_opt_in')) or bool(diesel_rate)
        jcb_opt = _to_bool(kwargs.get('gear_jcb_opt_in')) or bool(jcb_rate)

        if not partner_name or not email or not phone:
            return {'error': 'Missing required fields'}

        if not service_type or not capacity_id:
            return {'error': 'Missing project inputs'}

        # Find or create partner
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('email', '=', email)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': partner_name,
                'email': email,
                'phone': phone,
                'company_name': company_name,
            })
        else:
            partner.write({'phone': phone, 'company_name': company_name or partner.company_name})

        # Create Lead
        Lead = request.env['crm.lead'].sudo()
        team = request.env.ref('gear_on_rent.crm_team_rental', raise_if_not_found=False)

        lead_description = (
            f"Service Type: {service_type}\n"
            f"Capacity ID: {capacity_id}\n"
            f"MGQ Monthly: {mgq_monthly}\n"
            f"Expected Production: {expected_production}\n"
            f"Inventory Mode: {inventory_mode}\n"
            f"Grade ID: {grade_id or '-'}\n"
            f"Area ID: {area_id or '-'}\n"
            f"Project Duration (Years): {project_duration_years or '-'}\n"
            f"Civil Scope: {civil_scope or '-'}\n"
            f"Notes: {notes or '-'}\n"
            f"Optional — Transport: {transport_rate}, Pump: {pump_rate}, Manpower: {manpower_rate}, Diesel: {diesel_rate}, JCB: {jcb_rate}"
        )

        lead_vals = {
            'name': f'Batching Plant Inquiry - {company_name or partner_name}',
            'partner_id': partner.id,
            'contact_name': partner_name,
            'email_from': email,
            'phone': phone,
            'description': lead_description,
            'team_id': team.id if team else False,
            'user_id': False,
        }
        lead = Lead.create(lead_vals)

        Order = request.env['sale.order'].sudo()
        service_master = request.env['gear.service.master'].sudo().search([('category', '=', service_type)], limit=1)

        order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'opportunity_id': lead.id,
            'team_id': team.id if team else False,
            'origin': 'Batching Plant Landing Page',
            'x_billing_category': 'plant',
            'gear_service_type': service_type,
            'gear_capacity_id': capacity_id,
            'gear_service_id': service_master.id if service_master else False,
            'x_inventory_mode': inventory_mode,
            'gear_design_mix_id': grade_id if inventory_mode == 'with_inventory' else False,
            'gear_material_area_id': area_id,
            'gear_project_duration_years': project_duration_years,
            'gear_civil_scope': civil_scope,
            'x_monthly_mgq': mgq_monthly,
            'mgq_monthly': mgq_monthly,
            'gear_expected_production_qty': expected_production,
            'note': notes,
            'gear_transport_per_cum': transport_rate,
            'gear_pump_per_cum': pump_rate,
            'gear_manpower_per_cum': manpower_rate,
            'gear_diesel_per_cum': diesel_rate,
            'gear_jcb_monthly': jcb_rate,
            'gear_transport_opt_in': transport_opt,
            'gear_pumping_opt_in': pump_opt,
            'gear_manpower_opt_in': manpower_opt,
            'gear_diesel_opt_in': diesel_opt,
            'gear_jcb_opt_in': jcb_opt,
        }

        sale_order = Order.create(order_vals)

        lead.message_post(body=f"Quotation created: {sale_order.name}")

        pdf_filename = False
        pdf_base64 = False
        Attachment = request.env['ir.attachment'].sudo()
        pdf_action = request.env.ref('gear_on_rent.action_report_batching_plant_quote', raise_if_not_found=False)
        try:
            if pdf_action:
                pdf_content, _format = pdf_action._render_qweb_pdf(pdf_action.id, res_ids=[sale_order.id])
                if pdf_content:
                    pdf_filename = f"{sale_order.name}.pdf"
                    pdf_base64 = base64.b64encode(pdf_content).decode('ascii')
                    Attachment.create({
                        'name': pdf_filename,
                        'type': 'binary',
                        'datas': pdf_base64,
                        'mimetype': 'application/pdf',
                        'res_model': 'sale.order',
                        'res_id': sale_order.id,
                        'public': True,
                    })
        except Exception:
            _logger.exception("Unable to generate batching plant quotation PDF for %s", sale_order.name)
            pdf_base64 = False
            pdf_filename = False

        try:
            template = request.env.ref('gear_on_rent.mail_template_batching_quote_send', raise_if_not_found=False)
            if template:
                template.sudo().send_mail(sale_order.id, force_send=True)
        except Exception:
            _logger.exception("Unable to send batching plant quotation email for %s", sale_order.name)

        if sale_order.state == 'draft':
            try:
                sale_order.action_quotation_sent()
            except Exception:
                _logger.exception("Unable to mark quotation %s as sent", sale_order.name)

        return {
            'success': True,
            'lead_id': lead.id,
            'sale_order_name': sale_order.name,
            'pdf_filename': pdf_filename,
            'pdf_content': pdf_base64,
        }

    @staticmethod
    def _page_render_context(xml_id):
        """Return qcontext data so the website builder keeps publish/edit tools."""
        page = request.env.ref(xml_id, raise_if_not_found=False)
        if not page:
            return {}
        page = page.sudo()
        if request.env.user._is_public() and not page.is_visible:
            raise NotFound()
        return {'main_object': page}

    @staticmethod
    def _render_page_response(xml_id):
        """Render the website.page via the standard engine for full editability."""
        page = request.env.ref(xml_id, raise_if_not_found=False)
        if not page:
            raise NotFound()
        page = page.sudo()
        if request.env.user._is_public() and not page.is_visible:
            raise NotFound()
        def _call_page_renderer(method):
            """Call `_get_response`/`_generate_response` regardless of signature."""
            if not callable(method):
                return None
            try:
                signature = inspect.signature(method)
            except (TypeError, ValueError):
                signature = None

            if signature:
                parameters = signature.parameters
                # legacy API without the request argument
                if not parameters:
                    return method()
                return method(request)

            try:
                return method(request)
            except TypeError:
                return method()

        for renderer_name in ('_get_response', '_generate_response'):
            renderer = getattr(page, renderer_name, None)
            response = _call_page_renderer(renderer)
            if response is not None:
                return response

        # As a last resort, render the underlying view so the page still works
        # even if neither of the helper methods exists on this Odoo version.
        view = page.view_id
        if view:
            template = view.key or view.id
            return request.render(template, {'main_object': page})
        raise NotFound()
