from datetime import datetime, time

from odoo import fields, http, _

from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class RmcSubcontractorPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        user = request.env.user
        if user.has_group('rmc_management_system.group_rmc_subcontractor_portal'):
            subcontractor = self._get_subcontractor(fetch_if_missing=False)
            if subcontractor:
                values.update({
                    'rmc_subcontractor': subcontractor,
                    'rmc_subcontractor_plants_count': len(subcontractor.plant_ids),
                })
        if user.has_group('rmc_management_system.group_rmc_operator_portal'):
            plant = self._get_operator_plant(fetch_if_missing=False)
            if plant:
                values.update({'rmc_operator_plant': plant})
        ticket_ctx = values.get('ticket')
        if not ticket_ctx or 'ticket_ref' not in getattr(ticket_ctx, '_fields', {}):
            values['ticket'] = request.env['helpdesk.ticket'].sudo().browse()
        return values

    def _get_subcontractor(self, fetch_if_missing=True):
        user = request.env.user
        subcontractor_group_xmlid = 'rmc_management_system.group_rmc_subcontractor_portal'
        if not user.has_group(subcontractor_group_xmlid):
            # Continue anyway so we can auto-link and grant the group when possible
            pass

        partner_ids = {user.partner_id.id} if user.partner_id else set()
        commercial_partner = user.partner_id.commercial_partner_id if user.partner_id else False
        if commercial_partner:
            partner_ids.add(commercial_partner.id)

        Subcontractor = request.env['rmc.subcontractor'].sudo()
        if partner_ids:
            domain = [('partner_id', 'in', list(partner_ids))]
            if commercial_partner:
                domain = ['|'] + domain + [('partner_id', 'child_of', commercial_partner.id)]
            subcontractor = Subcontractor.search(domain, limit=1)
        else:
            subcontractor = Subcontractor.browse()

        if not subcontractor and fetch_if_missing and partner_ids:
            # Auto-create a lightweight subcontractor record mapped to the user's commercial partner
            partner_for_record = commercial_partner or user.partner_id
            if partner_for_record:
                subcontractor = Subcontractor.create({
                    'name': partner_for_record.name or user.name or _('Subcontractor'),
                    'partner_id': partner_for_record.id,
                })

        if subcontractor:
            subcontractor_group = request.env.ref(subcontractor_group_xmlid, raise_if_not_found=False)
            if subcontractor_group:
                sudo_user = user.sudo()
                if not sudo_user.has_group(subcontractor_group_xmlid):
                    sudo_user.write({'groups_id': [(4, subcontractor_group.id)]})

        # If the user still lacks the subcontractor portal group, avoid exposing data
        if not user.has_group(subcontractor_group_xmlid):
            return False

        return subcontractor

    def _get_operator_plant(self, fetch_if_missing=True):
        user = request.env.user
        if not user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return False
        domain = [('operator_user_id', '=', user.id)]
        plant = request.env['rmc.subcontractor.plant'].sudo().search(domain, limit=1)
        if not plant and fetch_if_missing:
            return False
        return plant

    def _compute_subcontractor_dashboard(self, subcontractor):
        transport_model = request.env['rmc.subcontractor.transport'].sudo()
        docket_model = request.env['rmc.docket'].sudo()
        fuel_log_model = request.env['rmc.transport.fuel.log'].sudo()
        workorder_model = request.env['dropshipping.workorder'].sudo()
        ticket_model = request.env['dropshipping.workorder.ticket'].sudo()
        today_start = fields.Datetime.to_string(datetime.combine(fields.Date.context_today(request.env.user), time.min))
        today_end = fields.Datetime.to_string(datetime.combine(fields.Date.context_today(request.env.user), time.max))

        transports = transport_model.search([('subcontractor_id', '=', subcontractor.id), ('active', '=', True)])
        plants = subcontractor.plant_ids.sudo()
        pump_model = request.env['rmc.subcontractor.pump'].sudo()
        pumps = pump_model.search([
            ('subcontractor_id', '=', subcontractor.id),
            ('active', '=', True),
        ])
        dockets_today = docket_model.search([
            ('subcontractor_id', '=', subcontractor.id),
            ('docket_date', '>=', today_start),
            ('docket_date', '<=', today_end),
        ])
        operators = plants.filtered(lambda p: p.operator_portal_enabled and p.operator_user_id)
        fleet_utilization = 0.0
        if transports:
            active_with_jobs = len(transports.filtered(lambda t: t.jobs_today > 0))
            fleet_utilization = round((active_with_jobs / len(transports)) * 100, 2)
        documents_due = sum(transports.mapped('documents_due_count'))
        today_str = fields.Date.to_string(fields.Date.context_today(request.env.user))
        fuel_litres = sum(fuel_log_model.search([
            ('transport_id', 'in', transports.ids),
            ('log_date', '=', today_str),
        ]).mapped('litre_count')) if transports else 0.0

        partner_id = subcontractor.partner_id.id if subcontractor.partner_id else False
        workorder_domain = [('subcontractor_id', '=', partner_id)] if partner_id else []
        workorders_active = workorder_model.search(workorder_domain + [('state', 'not in', ['completed', 'cancelled'])], order='date_order desc', limit=20) if workorder_domain else workorder_model.browse([])
        workorders_count = workorder_model.search_count(workorder_domain) if workorder_domain else 0
        workorders_active_count = workorder_model.search_count(workorder_domain + [('state', 'not in', ['completed', 'cancelled'])]) if workorder_domain else 0

        ticket_domain = [('workorder_id.subcontractor_id', '=', partner_id)] if partner_id else []
        tickets_open = ticket_model.search(ticket_domain + [('state', 'not in', ['completed', 'cancelled'])], order='delivery_date desc, id desc', limit=20) if ticket_domain else ticket_model.browse([])
        tickets_open_count = ticket_model.search_count(ticket_domain + [('state', 'not in', ['completed', 'cancelled'])]) if ticket_domain else 0
        return {
            'plants': plants,
            'transports': transports,
            'pumps': pumps,
            'operators': operators,
            'dockets_today': dockets_today,
            'workorders_active': workorders_active,
            'tickets_open': tickets_open,
            'fleet_utilization': fleet_utilization,
            'documents_due': documents_due,
            'fuel_litres': fuel_litres,
            'totals': {
                'plants': len(plants),
                'operators': len(operators),
                'fleet': len(transports),
                'pumps': len(pumps),
                'jobs_today': len(dockets_today),
                'workorders': workorders_count,
                'active_workorders': workorders_active_count,
                'open_tickets': tickets_open_count,
            },
        }

    @http.route(['/my/rmc/subcontractor'], type='http', auth='user', website=True)
    def portal_subcontractor_dashboard(self, **kwargs):
        subcontractor = self._get_subcontractor()
        if not subcontractor:
            return request.redirect('/my')
        data = self._compute_subcontractor_dashboard(subcontractor)
        values = {
            'subcontractor': subcontractor,
            'plants': data['plants'],
            'transports': data['transports'],
            'pumps': data['pumps'],
            'operators': data['operators'],
            'dockets_today': data['dockets_today'],
            'workorders_active': data['workorders_active'],
            'tickets_open': data['tickets_open'],
            'fleet_utilization': data['fleet_utilization'],
            'documents_due': data['documents_due'],
            'fuel_litres': data['fuel_litres'],
            'totals': data['totals'],
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_dashboard', values)

    @http.route(['/my/rmc/subcontractor/plant/<int:plant_id>'], type='http', auth='user', website=True)
    def portal_subcontractor_plant(self, plant_id, **kwargs):
        subcontractor = self._get_subcontractor()
        if not subcontractor:
            return request.redirect('/my')
        plant = request.env['rmc.subcontractor.plant'].sudo().search([
            ('id', '=', plant_id),
            ('subcontractor_id', '=', subcontractor.id),
        ], limit=1)
        if not plant:
            return request.redirect('/my/rmc/subcontractor')
        transport_model = request.env['rmc.subcontractor.transport'].sudo()
        pump_model = request.env['rmc.subcontractor.pump'].sudo()
        transports = transport_model.search([
            ('plant_id', '=', plant.id),
            ('active', '=', True),
        ])
        pumps = pump_model.search([
            ('plant_id', '=', plant.id),
            ('active', '=', True),
        ])
        day_reports = request.env['rmc.operator.day.report'].sudo().search([
            ('plant_id', '=', plant.id),
        ], order='report_date desc', limit=10)
        docket_model = request.env['rmc.docket']
        dockets = docket_model.sudo().search([
            '|',
            ('subcontractor_transport_id', 'in', transports.ids),
            ('subcontractor_plant_id', '=', plant.id),
        ], order='docket_date desc, id desc', limit=20)
        state_labels = dict(docket_model._fields['state'].selection)
        portal_status_labels = dict(docket_model._fields['operator_portal_status'].selection)
        values = {
            'subcontractor': subcontractor,
            'plant': plant,
            'transports': transports,
            'pumps': pumps,
            'day_reports': day_reports,
            'dockets': dockets,
            'docket_state_labels': state_labels,
            'docket_portal_state_labels': portal_status_labels,
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_plant', values)

    @http.route(['/my/rmc/subcontractor/day-report/<int:report_id>'], type='http', auth='user', website=True)
    def portal_subcontractor_day_report(self, report_id, **kwargs):
        subcontractor, partner_id = self._get_subcontractor_partner_id()
        if not subcontractor:
            return request.redirect('/my')

        report = request.env['rmc.operator.day.report'].sudo().browse(report_id)
        if not report or report.plant_id.subcontractor_id.id != subcontractor.id:
            return request.redirect('/my/rmc/subcontractor')

        docket_model = request.env['rmc.docket']
        state_labels = dict(docket_model._fields['state'].selection)
        portal_status_labels = dict(docket_model._fields['operator_portal_status'].selection)
        dockets = report.docket_ids.sorted(key=lambda d: (d.docket_date or fields.Datetime.now(), d.id), reverse=True)

        values = {
            'subcontractor': subcontractor,
            'day_report': report,
            'dockets': dockets,
            'docket_state_labels': state_labels,
            'docket_portal_state_labels': portal_status_labels,
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_day_report', values)

    @http.route(['/my/rmc/subcontractor/day-report/<int:report_id>/pdf'], type='http', auth='user', website=True)
    def portal_subcontractor_day_report_pdf(self, report_id, **kwargs):
        subcontractor, partner_id = self._get_subcontractor_partner_id()
        if not subcontractor:
            return request.redirect('/my')

        report = request.env['rmc.operator.day.report'].sudo().browse(report_id)
        if not report or report.plant_id.subcontractor_id.id != subcontractor.id:
            return request.redirect('/my/rmc/subcontractor')

        report_service = request.env['ir.actions.report'].sudo()
        report_name = 'rmc_management_system.report_operator_day_report'
        try:
            report_action = report_service._get_report_from_name(report_name)
        except ValueError:
            template = request.env.ref(report_name, raise_if_not_found=False)
            if not template:
                return request.redirect('/my/rmc/subcontractor')
            report_action = report_service.search([
                ('report_name', '=', report_name)
            ], limit=1)
            if not report_action:
                binding_model_id = request.env['ir.model']._get_id('rmc.operator.day.report')
                report_action = report_service.create({
                    'name': 'Operator Day Report',
                    'model': 'rmc.operator.day.report',
                    'report_type': 'qweb-pdf',
                    'report_name': report_name,
                    'report_file': report_name,
                    'binding_model_id': binding_model_id,
                    'binding_type': 'report',
                })
        report_action = report_action.sudo()
        binding_model = request.env['ir.model']._get('rmc.operator.day.report')
        if not binding_model:
            return request.redirect('/my/rmc/subcontractor')
        if any(r.model != binding_model.model or r.binding_model_id.id != binding_model.id for r in report_action):
            report_action.write({
                'model': binding_model.model,
                'binding_model_id': binding_model.id,
                'binding_type': 'report',
            })
            report_action = report_service.browse(report_action.ids)
        primary_action = report_action[:1]
        if not primary_action.model or primary_action.model != binding_model.model:
            primary_action.write({
                'model': binding_model.model,
                'binding_model_id': binding_model.id,
                'binding_type': 'report',
            })
        primary_action = report_service.browse(primary_action.id)
        pdf_content, _ = primary_action._render_qweb_pdf(primary_action.id, res_ids=report.ids)
        filename = 'DayReport_%s_%s.pdf' % (
            (report.plant_id.plant_code or report.plant_id.name or report.plant_id.id or 'Plant'),
            report.report_date or fields.Date.today(),
        )
        filename = ''.join(ch if ch.isalnum() or ch in ('_', '-', '.') else '_' for ch in filename)
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', str(len(pdf_content))),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(pdf_content, headers=headers)

    def _get_subcontractor_partner_id(self):
        subcontractor = self._get_subcontractor()
        partner_id = subcontractor.partner_id.id if subcontractor and subcontractor.partner_id else False
        return subcontractor, partner_id

    @http.route(['/my/rmc/subcontractor/workorder/<int:workorder_id>'], type='http', auth='user', website=True)
    def portal_subcontractor_workorder(self, workorder_id, **kwargs):
        subcontractor, partner_id = self._get_subcontractor_partner_id()
        if not subcontractor:
            return request.redirect('/my')
        workorder = request.env['dropshipping.workorder'].sudo().browse(workorder_id)
        if not workorder or workorder.subcontractor_id.id != partner_id:
            return request.redirect('/my/rmc/subcontractor')
        dockets = request.env['rmc.docket'].sudo().search([
            ('workorder_id', '=', workorder.id),
        ], order='docket_date desc, id desc')
        tickets = workorder.ticket_ids.sudo()
        values = {
            'subcontractor': subcontractor,
            'workorder': workorder,
            'dockets': dockets,
            'wo_tickets': tickets,
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_workorder', values)

    @http.route(['/my/rmc/subcontractor/ticket/<int:ticket_id>'], type='http', auth='user', website=True)
    def portal_subcontractor_ticket(self, ticket_id, **kwargs):
        subcontractor, partner_id = self._get_subcontractor_partner_id()
        if not subcontractor:
            return request.redirect('/my')
        ticket = request.env['dropshipping.workorder.ticket'].sudo().browse(ticket_id)
        if not ticket or ticket.workorder_id.subcontractor_id.id != partner_id:
            return request.redirect('/my/rmc/subcontractor')
        values = {
            'subcontractor': subcontractor,
            'wo_ticket': ticket,
            'workorder': ticket.workorder_id,
            'helpdesk_ticket': ticket.helpdesk_ticket_id.sudo(),
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_ticket', values)

    @http.route(['/my/rmc/subcontractor/docket/<int:docket_id>'], type='http', auth='user', website=True)
    def portal_subcontractor_docket(self, docket_id, **kwargs):
        subcontractor, partner_id = self._get_subcontractor_partner_id()
        if not subcontractor:
            return request.redirect('/my')
        docket = request.env['rmc.docket'].sudo().browse(docket_id)
        if not docket or docket.subcontractor_id.id != subcontractor.id:
            return request.redirect('/my/rmc/subcontractor')
        state_labels = dict(docket._fields['state'].selection)
        portal_status_labels = dict(docket._fields['operator_portal_status'].selection)
        values = {
            'subcontractor': subcontractor,
            'docket': docket,
            'state_labels': state_labels,
            'portal_status_labels': portal_status_labels,
        }
        values.setdefault('ticket', request.env['helpdesk.ticket'].sudo().browse())
        return request.render('rmc_management_system.portal_subcontractor_docket', values)


class RmcOperatorPortal(CustomerPortal):

    def _get_operator_plant(self, fetch_if_missing=True):
        plant = request.env['rmc.subcontractor.plant'].sudo().search([
            ('operator_user_id', '=', request.env.user.id),
        ], limit=1)
        if not plant and fetch_if_missing:
            return False
        return plant

    def _get_today_bounds(self):
        today = fields.Date.context_today(request.env.user)
        return (
            fields.Datetime.to_string(datetime.combine(today, time.min)),
            fields.Datetime.to_string(datetime.combine(today, time.max)),
        )

    def _get_dockets_today(self, plant):
        if not plant:
            return request.env['rmc.docket']
        start, end = self._get_today_bounds()
        domain = [
            ('operator_user_id', '=', request.env.user.id),
            ('docket_date', '>=', start),
            ('docket_date', '<=', end),
        ]
        dockets = request.env['rmc.docket'].sudo().search(domain, order='docket_date asc')
        state_priority = {
            'draft': 0,
            'in_production': 1,
            'ready': 2,
            'dispatched': 3,
            'delivered': 4,
            'cancel': 5,
        }
        return dockets.sorted(key=lambda d: (state_priority.get(d.state or '', 99), d.docket_date or datetime.max))

    @http.route(['/my/rmc/operator'], type='http', auth='user', website=True)
    def portal_operator_dashboard(self, submitted=False, **kwargs):
        if not request.env.user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return request.redirect('/my')
        plant = self._get_operator_plant()
        if not plant:
            return request.redirect('/my')
        dockets = self._get_dockets_today(plant)
        day_report = request.env['rmc.operator.day.report'].sudo().search([
            ('plant_id', '=', plant.id),
            ('operator_user_id', '=', request.env.user.id),
            ('report_date', '=', fields.Date.context_today(request.env.user)),
        ], limit=1)
        submitted_flag = submitted in (True, '1', 'true', 'True')
        completed_jobs = len(dockets.filtered(lambda d: d.operator_portal_status == 'completed'))
        total_quantity = sum(dockets.mapped('quantity_produced'))
        reports_today_count = request.env['rmc.operator.day.report'].sudo().search_count([
            ('plant_id', '=', plant.id),
            ('operator_user_id', '=', request.env.user.id),
            ('report_date', '=', fields.Date.context_today(request.env.user)),
        ])
        values = {
            'plant': plant,
            'dockets': dockets,
            'day_report': day_report,
            'submitted': submitted_flag,
            'operator_totals': {
                'total_jobs': len(dockets),
                'completed_jobs': completed_jobs,
                'total_quantity': total_quantity,
                'reports_today_count': reports_today_count,
            },
            'today_date': fields.Date.context_today(request.env.user),
        }
        return request.render('rmc_management_system.portal_operator_dashboard', values)

    @http.route(['/my/rmc/operator/docket/<int:docket_id>/update'], type='http', auth='user', methods=['POST'], website=True)
    def portal_operator_update_docket(self, docket_id, **post):
        if not request.env.user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return request.redirect('/my')
        docket = request.env['rmc.docket'].sudo().browse(docket_id)
        if not docket or docket.operator_user_id.id != request.env.user.id:
            return request.redirect('/my/rmc/operator')
        status = post.get('operator_portal_status', 'in_progress')
        notes = post.get('operator_notes')
        quantity = post.get('quantity_produced')
        current_capacity = post.get('current_capacity')
        docket_number = post.get('docket_number')
        update_vals = {}
        if quantity:
            try:
                update_vals['quantity_produced'] = float(quantity)
            except ValueError:
                pass
        if current_capacity:
            try:
                update_vals['current_capacity'] = float(current_capacity)
            except ValueError:
                pass
        if docket_number is not None:
            docket_number_val = docket_number.strip()
            update_vals['docket_number'] = docket_number_val or False
            if docket.state == 'draft' and docket_number_val:
                update_vals.setdefault('state', 'in_production')
        if update_vals:
            docket.sudo().write(update_vals)
        docket.sudo().action_operator_set_status(status, notes)
        redirect_url = '/my/rmc/operator/docket/%s' % docket.id if post.get('from_detail') else '/my/rmc/operator'
        return request.redirect(redirect_url)

    @http.route(['/my/rmc/operator/docket/<int:docket_id>'], type='http', auth='user', website=True)
    def portal_operator_view_docket(self, docket_id, **kwargs):
        if not request.env.user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return request.redirect('/my')
        docket = request.env['rmc.docket'].sudo().browse(docket_id)
        if not docket or docket.operator_user_id.id != request.env.user.id:
            return request.redirect('/my/rmc/operator')
        values = self._prepare_portal_layout_values()
        values.update({
            'plant': docket.subcontractor_plant_id or docket.subcontractor_transport_id.plant_id,
            'docket': docket,
            'loading_created': kwargs.get('loading_created') in ('1', 'true', 'True'),
        })
        return request.render('rmc_management_system.portal_operator_docket_form', values)

    @http.route(['/my/rmc/operator/day-report/submit'], type='http', auth='user', methods=['POST'], website=True)
    def portal_operator_submit_report(self, **post):
        if not request.env.user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return request.redirect('/my')
        plant = self._get_operator_plant()
        if not plant:
            return request.redirect('/my')
        docket_ids = request.httprequest.form.getlist('docket_ids')
        docket_ids = [int(d_id) for d_id in docket_ids if d_id]
        dockets = request.env['rmc.docket'].sudo().browse(docket_ids)
        dockets = dockets.filtered(lambda d: d.operator_user_id.id == request.env.user.id)
        remarks = post.get('remarks')
        report_model = request.env['rmc.operator.day.report'].sudo()
        report = report_model.search([
            ('plant_id', '=', plant.id),
            ('operator_user_id', '=', request.env.user.id),
            ('report_date', '=', fields.Date.context_today(request.env.user)),
        ], limit=1)
        vals = {
            'plant_id': plant.id,
            'operator_user_id': request.env.user.id,
            'report_date': fields.Date.context_today(request.env.user),
            'remarks': remarks,
        }
        if report:
            report.write({'remarks': remarks, 'docket_ids': [(6, 0, dockets.ids)]})
        else:
            vals['docket_ids'] = [(6, 0, dockets.ids)]
            report = report_model.create(vals)
        if dockets:
            dockets.write({'operator_day_report_id': report.id})
            for docket in dockets.filtered(lambda d: d.operator_portal_status != 'completed'):
                docket.sudo().action_operator_set_status('completed', docket.operator_notes)
        return request.redirect('/my/rmc/operator?submitted=1')

    def _parse_portal_datetime(self, value):
        if not value:
            return False
        try:
            dt_value = datetime.fromisoformat(value)
        except ValueError:
            return False
        return fields.Datetime.to_string(dt_value)

    def _format_portal_datetime(self, value):
        if not value:
            return ''
        if isinstance(value, str):
            value = fields.Datetime.from_string(value)
        user_dt = fields.Datetime.context_timestamp(request.env.user, value)
        return user_dt.strftime('%Y-%m-%dT%H:%M') if user_dt else ''

    @http.route(['/my/rmc/operator/docket/<int:docket_id>/create-truck-loading'], type='http', auth='user', methods=['GET', 'POST'], website=True)
    def portal_operator_create_truck_loading(self, docket_id, **post):
        if not request.env.user.has_group('rmc_management_system.group_rmc_operator_portal'):
            return request.redirect('/my')
        docket = request.env['rmc.docket'].sudo().browse(docket_id)
        if not docket or docket.operator_user_id.id != request.env.user.id:
            return request.redirect('/my/rmc/operator')

        plant = docket.subcontractor_plant_id or docket.subcontractor_transport_id.plant_id
        transport_domain = [('active', '=', True)]
        if plant:
            transport_domain.append(('plant_id', '=', plant.id))
        elif docket.subcontractor_id:
            transport_domain.append(('subcontractor_id', '=', docket.subcontractor_id.id))
        transports = request.env['rmc.subcontractor.transport'].sudo().search(transport_domain, order='transport_code asc')

        if request.httprequest.method == 'POST':
            transport_id = post.get('subcontractor_transport_id') or (docket.subcontractor_transport_id.id if docket.subcontractor_transport_id else False)
            vals = {
                'docket_id': docket.id,
                'loading_status': post.get('loading_status') or 'scheduled',
            }
            loading_date = self._parse_portal_datetime(post.get('loading_date'))
            start_time = self._parse_portal_datetime(post.get('loading_start_time'))
            end_time = self._parse_portal_datetime(post.get('loading_end_time'))
            if loading_date:
                vals['loading_date'] = loading_date
            if start_time:
                vals['loading_start_time'] = start_time
            if end_time:
                vals['loading_end_time'] = end_time
            if transport_id:
                transport = request.env['rmc.subcontractor.transport'].sudo().browse(int(transport_id))
                if transport:
                    vals['subcontractor_transport_id'] = transport.id
                    if transport.fleet_vehicle_id:
                        vals['vehicle_id'] = transport.fleet_vehicle_id.id
            request.env['rmc.truck_loading'].sudo().create(vals)
            return request.redirect('/my/rmc/operator/docket/%s?loading_created=1' % docket.id)

        values = self._prepare_portal_layout_values()
        values.update({
            'docket': docket,
            'plant': plant,
            'transports': transports,
            'default_transport_id': docket.subcontractor_transport_id.id if docket.subcontractor_transport_id else False,
            'default_loading_date': self._format_portal_datetime(fields.Datetime.now()),
        })
        return request.render('rmc_management_system.portal_operator_truck_loading_form', values)
