# -*- coding: utf-8 -*-
import base64
import inspect
import logging

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


OPTIONAL_SERVICE_FIELD_MAP = {
    "transport": {
        "flag_field": "gear_transport_opt_in",
        "value_field": "gear_transport_per_cum",
        "label_fallback": "Transport (per CUM)",
    },
    "pump": {
        "flag_field": "gear_pumping_opt_in",
        "value_field": "gear_pump_per_cum",
        "label_fallback": "Pump (per CUM)",
    },
    "manpower": {
        "flag_field": "gear_manpower_opt_in",
        "value_field": "gear_manpower_per_cum",
        "label_fallback": "Manpower (per CUM)",
    },
    "diesel": {
        "flag_field": "gear_diesel_opt_in",
        "value_field": "gear_diesel_per_cum",
        "label_fallback": "Diesel (per CUM)",
    },
    "jcb": {
        "flag_field": "gear_jcb_opt_in",
        "value_field": "gear_jcb_monthly",
        "label_fallback": "JCB (Monthly)",
    },
}


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

    def _prepare_optional_service_context(self, company):
        OptionalService = request.env['gear.optional.service.master'].sudo()
        services = OptionalService.search([('active', '=', True)], order='name asc, id asc')
        currency = company.currency_id
        diesel_surcharge_total = OptionalService.compute_diesel_surcharge_total()
        charge_labels = {
            "per_cum": "per CUM",
            "per_month": "per Month",
            "fixed": "Fixed / Contract",
        }

        def _format_rate(value):
            if not value:
                return "0.00"
            try:
                return "%s%.2f" % ((currency.symbol or ""), value)
            except Exception:
                return "%.2f" % value

        entries = []
        for service in services:
            field_map = OPTIONAL_SERVICE_FIELD_MAP.get(service.code)
            if not field_map:
                continue
            rate_value = service.rate or 0.0
            if service.code == "diesel":
                rate_value = diesel_surcharge_total or rate_value
            charge_type = service.charge_type or "per_cum"
            lock_quantity = service.code in {"diesel", "manpower"}
            entries.append(
                {
                    "label": service.name or field_map.get("label_fallback"),
                    "flag_field": field_map["flag_field"],
                    "value_field": field_map["value_field"],
                    "rate_value": rate_value,
                    "rate_display": _format_rate(rate_value),
                    "default_enabled": service.default_enabled,
                    "charge_type": charge_type,
                    "charge_label": charge_labels.get(charge_type, charge_type.title()),
                    "quantity_placeholder": service.charge_type == "per_month" and "Months" or "Qty / Multiplier",
                    "helper_text": lock_quantity
                    and "Standard rate auto-applies (no quantity needed)."
                    or "Standard rate auto-applies from master.",
                    "lock_quantity": lock_quantity,
                }
            )
        return entries

    def _format_currency(self, amount, currency):
        try:
            symbol = currency.symbol or ""
        except Exception:
            symbol = ""
        try:
            return f"{symbol}{float(amount):,.2f}"
        except Exception:
            try:
                return f"{symbol}{amount}"
            except Exception:
                return str(amount)

    def _compute_rate_summary(self, order):
        calculator = request.env["gear.batching.quotation.calculator"].sudo()
        final_rates = calculator.generate_final_rates(order) or {}
        per_cum_rate = (
            final_rates.get("total_per_cum")
            or final_rates.get("base_plant_rate")
            or final_rates.get("final_prime_rate")
            or final_rates.get("prime_rate")
            or 0.0
        )
        mgq_ctx, production_ctx = calculator._get_mgq_context(order)
        mgq_value = mgq_ctx or production_ctx or order.mgq_monthly or 0.0
        monthly_rate = per_cum_rate * mgq_value if per_cum_rate and mgq_value else 0.0
        currency = order.currency_id
        return {
            "per_cum": per_cum_rate,
            "per_cum_display": self._format_currency(per_cum_rate, currency),
            "monthly": monthly_rate,
            "monthly_display": self._format_currency(monthly_rate, currency),
            "mgq": mgq_value,
        }

    @http.route(['/batching-plant'], type='http', auth='public', website=True)
    def batching_plant_page(self, **kwargs):
        """Batching Plant landing page with lead tracking"""
        Order = request.env['sale.order']
        capacity_model = request.env['gear.plant.capacity.master'].sudo()
        design_model = request.env['gear.design.mix.master'].sudo()
        material_model = request.env['gear.material.area.master'].sudo()
        user = request.env.user
        partner = user.partner_id

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

        company = request.env.company

        values = {
            'service_types': Order._fields['gear_service_type'].selection,
            'inventory_modes': Order._fields['x_inventory_mode'].selection,
            'project_durations': Order._fields['gear_project_duration_years'].selection,
            'civil_scopes': Order._fields['gear_civil_scope'].selection,
            'plant_running_options': Order._fields['gear_plant_running'].selection,
            'capacities': capacity_model.search([('active', '=', True)], order='capacity_cum_hour'),
            'design_mixes': design_model.search([('active', '=', True)], order='grade'),
            'material_areas': material_model.search([('active', '=', True)], order='name'),
            'optional_services': self._prepare_optional_service_context(company),
        }

        if not user._is_public():
            values.update(
                {
                    'default_full_name': user.name or '',
                    'default_email': user.email or '',
                    'default_phone': user.phone or partner.phone or '',
                }
            )

        values.update(self._page_render_context('gear_on_rent.website_page_batching_plant'))
        return request.render('gear_on_rent.batching_plant_website_page', values)

    @http.route('/batching-plant/submit', type='json', auth='public', website=True)
    def submit_batching_plant_request(self, **kwargs):
        """Handle batching plant form submission"""
        Order = request.env['sale.order'].sudo()

        def _to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return False

        def _to_int_list(value):
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                candidates = value
            else:
                candidates = [value]

            ids = []
            for candidate in candidates:
                try:
                    if isinstance(candidate, str) and not candidate.strip():
                        continue
                    ids.append(int(candidate))
                except (TypeError, ValueError):
                    continue
            return ids

        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _to_bool(value):
            if isinstance(value, str):
                return value.lower() in ('1', 'true', 'on', 'yes')
            return bool(value)

        def _get_company():
            website = getattr(request, 'website', False)
            if website and website.company_id:
                return website.company_id
            return request.env.company
        preview_only = _to_bool(kwargs.get('preview_only'))

        def _get_silent_warehouse_id(company):
            param_model = request.env['ir.config_parameter'].sudo()
            keys = [f"gear_on_rent.silent_warehouse_id.{company.id}", "gear_on_rent.silent_warehouse_id"]
            for key in keys:
                raw_value = param_model.get_param(key)
                if not raw_value:
                    continue
                try:
                    return int(raw_value)
                except (TypeError, ValueError):
                    _logger.warning("Invalid silent warehouse parameter %s for key %s", raw_value, key)
            return False

        def _get_default_real_warehouse(company):
            Warehouse = request.env['stock.warehouse'].sudo()
            base_domain = [('company_id', '=', company.id)]
            silent_wh_id = _get_silent_warehouse_id(company)
            search_domain = list(base_domain)
            if silent_wh_id:
                search_domain.append(('id', '!=', silent_wh_id))
            warehouse = Warehouse.search(search_domain, order='sequence asc, id asc', limit=1)
            if warehouse:
                return warehouse
            if silent_wh_id:
                silent = Warehouse.browse(silent_wh_id)
                if silent.exists():
                    _logger.warning(
                        "Falling back to silent warehouse %s for company %s as no other warehouse is configured",
                        silent_wh_id,
                        company.id,
                    )
                    return silent
            return Warehouse.search(base_domain, order='sequence asc, id asc', limit=1)

        def _format_currency(amount, currency):
            try:
                symbol = currency.symbol or ""
            except Exception:
                symbol = ""
            try:
                return f"{symbol}{float(amount):,.2f}"
            except Exception:
                try:
                    return f"{symbol}{amount}"
                except Exception:
                    return str(amount)

        # Extract data
        partner_name = kwargs.get('partner_name')
        company_name = kwargs.get('company_name')
        email = kwargs.get('email')
        phone = kwargs.get('phone')
        service_type = kwargs.get('gear_service_type')
        capacity_id = _to_int(kwargs.get('gear_capacity_id'))
        mgq_monthly = _to_float(kwargs.get('mgq_monthly'))
        project_quantity = _to_float(
            kwargs.get('project_quantity') or kwargs.get('total_project_qty') or kwargs.get('project_qty')
        )
        expected_production = _to_float(kwargs.get('gear_expected_production_qty'))
        inventory_mode = kwargs.get('x_inventory_mode') or 'without_inventory'
        allowed_running = {val for val, _label in Order._fields['gear_plant_running'].selection}
        running_labels = dict(Order._fields['gear_plant_running'].selection)
        plant_running = kwargs.get('gear_plant_running')
        plant_running = plant_running if plant_running in allowed_running else False
        plant_running_label = running_labels.get(plant_running, plant_running)
        grade_ids = _to_int_list(kwargs.get('gear_design_mix_ids')) if inventory_mode == 'with_inventory' else []
        grade_id = grade_ids[0] if grade_ids else False
        if inventory_mode == 'with_inventory' and not grade_id:
            grade_id = _to_int(kwargs.get('gear_design_mix_id'))
            if grade_id:
                grade_ids.append(grade_id)
        area_id = _to_int(kwargs.get('gear_material_area_id'))
        raw_duration = kwargs.get('project_duration_years') or kwargs.get('gear_project_duration_years')
        if raw_duration is not None:
            raw_duration = str(raw_duration)
        allowed_durations = {val for val, _label in Order._fields['gear_project_duration_years'].selection}
        project_duration_years = raw_duration if raw_duration in allowed_durations else False
        project_duration_months = _to_int(
            kwargs.get('gear_project_duration_months') or kwargs.get('project_duration_months')
        )
        if project_duration_years and not project_duration_months:
            try:
                project_duration_months = int(float(project_duration_years) * 12)
            except (TypeError, ValueError):
                project_duration_months = False
        civil_scope = kwargs.get('gear_civil_scope')
        notes = kwargs.get('note')

        pricing_type = kwargs.get('pricing_type')
        allowed_pricing_types = {'individual_rate', 'full_package_rate'}
        pricing_type = pricing_type if pricing_type in allowed_pricing_types else False

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

        if not service_type or not capacity_id or not plant_running:
            return {'error': 'Missing project inputs'}

        if inventory_mode == 'with_inventory' and not grade_ids:
            return {'error': 'Please select at least one design mix for inventory mode.'}

        company = _get_company()
        real_warehouse = False
        if inventory_mode == 'with_inventory':
            real_warehouse = _get_default_real_warehouse(company)
            if not real_warehouse:
                _logger.warning(
                    "Batching plant submission blocked: inventory mode selected but no real warehouse configured for company %s",
                    company.id,
                )
                return {
                    'error': 'Inventory mode requires a configured plant warehouse on our side. Please contact us or choose Without Inventory.'
                }

        # Find or create partner
        Partner = request.env['res.partner'].sudo()
        partner = Partner.search([('email', '=', email)], limit=1)
        if partner:
            partner.write({'phone': phone, 'company_name': company_name or partner.company_name})
        elif preview_only:
            partner = request.env.user.partner_id or company.partner_id
        else:
            partner = Partner.create({
                'name': partner_name,
                'email': email,
                'phone': phone,
                'company_name': company_name,
            })

        if not partner:
            return {'error': 'Unable to resolve contact. Please retry.'}

        # Create Lead
        Lead = request.env['crm.lead'].sudo()
        team = request.env.ref('gear_on_rent.crm_team_rental', raise_if_not_found=False)

        lead_description = (
            f"Service Type: {service_type}\n"
            f"Capacity ID: {capacity_id}\n"
            f"MGQ Monthly: {mgq_monthly}\n"
            f"Project Quantity: {project_quantity or '-'}\n"
            f"Expected Production: {expected_production}\n"
            f"Inventory Mode: {inventory_mode}\n"
            f"Plant Running: {plant_running_label or '-'}\n"
            f"Grade IDs: {', '.join(map(str, grade_ids)) if grade_ids else '-'}\n"
            f"Area ID: {area_id or '-'}\n"
            f"Project Duration (Years): {project_duration_years or '-'}\n"
            f"Project Duration (Months): {project_duration_months or '-'}\n"
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
        lead = False if preview_only else Lead.create(lead_vals)

        service_master = request.env['gear.service.master'].sudo().search([('category', '=', service_type)], limit=1)

        note_text = notes or ''
        if project_quantity:
            note_text = f"{note_text}\nProject Quantity: {project_quantity}" if note_text else f"Project Quantity: {project_quantity}"

        order_vals = {
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'opportunity_id': lead.id,
            'team_id': team.id if team else False,
            'origin': 'Batching Plant Landing Page',
            'company_id': company.id,
            'x_billing_category': 'plant',
            'gear_service_type': service_type,
            'gear_capacity_id': capacity_id,
            'gear_service_id': service_master.id if service_master else False,
            'x_inventory_mode': inventory_mode,
            'x_real_warehouse_id': real_warehouse.id if real_warehouse else False,
            'pricing_type': pricing_type,
            'gear_design_mix_id': grade_id if inventory_mode == 'with_inventory' else False,
            'gear_design_mix_ids': [(6, 0, grade_ids)] if grade_ids else False,
            'gear_material_area_id': area_id,
            'gear_project_duration_years': project_duration_years,
            'gear_project_duration_months': project_duration_months or False,
            'gear_civil_scope': civil_scope,
            'x_monthly_mgq': mgq_monthly,
            'mgq_monthly': mgq_monthly,
            'gear_expected_production_qty': expected_production,
            'gear_plant_running': plant_running,
            'note': note_text,
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

        project_qty_field = next(
            (fname for fname in (
                'gear_total_project_qty',
                'gear_project_quantity',
                'x_total_project_qty',
                'project_quantity',
            ) if fname in Order._fields),
            False,
        )
        if project_qty_field:
            order_vals[project_qty_field] = project_quantity

        if preview_only:
            temp_order = Order.new(order_vals)
            try:
                rate_summary = self._compute_rate_summary(temp_order)
            except Exception:
                _logger.exception("Unable to compute batching plant rate preview")
                rate_summary = {}
            return {
                'success': True,
                'sale_order_name': False,
                'pdf_filename': False,
                'pdf_content': False,
                'rate_summary': rate_summary,
            }

        sale_order = Order.create(order_vals)

        if lead:
            lead.message_post(body=f"Quotation created: {sale_order.name}")

        rate_summary = {}
        try:
            calculator = request.env["gear.batching.quotation.calculator"].sudo()
            final_rates = calculator.generate_final_rates(sale_order) or {}
            per_cum_rate = (
                final_rates.get("total_per_cum")
                or final_rates.get("base_plant_rate")
                or final_rates.get("final_prime_rate")
                or final_rates.get("prime_rate")
                or 0.0
            )
            mgq_ctx, production_ctx = calculator._get_mgq_context(sale_order)
            mgq_value = mgq_ctx or production_ctx or sale_order.mgq_monthly or 0.0
            monthly_rate = per_cum_rate * mgq_value if per_cum_rate and mgq_value else 0.0
            currency = sale_order.currency_id
            rate_summary = {
                "per_cum": per_cum_rate,
                "per_cum_display": _format_currency(per_cum_rate, currency),
                "monthly": monthly_rate,
                "monthly_display": _format_currency(monthly_rate, currency),
                "mgq": mgq_value,
            }
        except Exception:
            _logger.exception("Unable to compute batching plant rate preview for %s", sale_order.name)

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
            'rate_summary': rate_summary,
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
            """Call `_get_response`/`_generate_response` when arguments match."""
            if not callable(method):
                return None
            try:
                signature = inspect.signature(method)
            except (TypeError, ValueError):
                signature = None

            if signature:
                params = list(signature.parameters.values())
                positional = [
                    param for param in params
                    if param.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                required = [param for param in positional if param.default is inspect._empty]
                if not positional:
                    return method()
                first_name = positional[0].name
                if first_name in ('request', 'req'):
                    if len(required) <= 1:
                        return method(request)
                    # Additional required params (e.g. placeholders) can't be provided here.
                    return None
                if not required:
                    return method()
                return None

            try:
                return method(request)
            except TypeError:
                try:
                    return method()
                except TypeError:
                    return None

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
