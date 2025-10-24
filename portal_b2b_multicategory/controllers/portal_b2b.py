# -*- coding: utf-8 -*-
from datetime import datetime, time as time_obj, date as date_obj

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from werkzeug.exceptions import NotFound
from odoo.tools import format_datetime, format_date, format_amount


class PortalB2BCustomerPortal(CustomerPortal):
    """Custom portal dashboard for multi-category B2B customers."""

    @staticmethod
    def _is_rmc_category(category):
        """Detect whether a product category should render the RMC experience."""
        if not category:
            return False
        name = (category.name or '').strip().lower()
        return 'rmc' in name or 'ready mix' in name

    def _portal_prepare_home_values(self, counters):
        values = super()._portal_prepare_home_values(counters)
        partner = request.env.user.partner_id
        categories = partner.get_portal_dashboard_categories()
        rmc_categories = categories.filtered(lambda c: self._is_rmc_category(c))

        if rmc_categories:
            subcontractor_group = request.env.ref('rmc_management_system.group_rmc_subcontractor_portal', raise_if_not_found=False)
            if subcontractor_group:
                user_sudo = request.env.user.sudo()
                if subcontractor_group not in user_sudo.groups_id:
                    user_sudo.write({'groups_id': [(4, subcontractor_group.id)]})

        values.update({
            'portal_b2b_category_count': len(categories),
            'portal_b2b_role': partner.get_portal_role_key(),
        })
        return values

    @http.route(['/my/b2b-dashboard', '/my/b2b-dashboard/<int:category_id>'], type='http', auth='user', website=True)
    def portal_b2b_dashboard(self, category_id=None, **kwargs):
        contact_partner = request.env.user.partner_id
        helper = request.env['portal.b2b.helper']
        categories = contact_partner.get_portal_dashboard_categories()
        rmc_categories = categories.filtered(lambda c: self._is_rmc_category(c))
        selected_category = False
        if category_id:
            selected_category = request.env['product.category'].sudo().browse(category_id)
            if not selected_category or selected_category not in categories:
                raise NotFound()
        elif categories:
            selected_category = categories[0]

        selected_category_is_rmc = bool(selected_category and selected_category in rmc_categories)

        orders = request.env['sale.order']
        if selected_category:
            orders = helper.get_partner_orders(contact_partner, category=selected_category, limit=50)

        workorder_state_labels = {}
        ticket_state_labels = {}
        if selected_category_is_rmc:
            workorder_state_labels = dict(request.env['dropshipping.workorder']._fields['state'].selection)
            ticket_state_labels = dict(request.env['dropshipping.workorder.ticket']._fields['state'].selection)

        orders_data = []
        for order in orders:
            order_sudo = order.sudo()
            workorders_payload = []
            if selected_category_is_rmc:
                for workorder in helper.get_order_workorders(order_sudo):
                    wo_sudo = workorder.sudo()
                    tickets_data = []
                    for ticket in wo_sudo.ticket_ids.sudo():
                        ticket_timeline = helper.prepare_rmc_ticket_timeline(ticket)
                        tickets_data.append({
                            'record': ticket,
                            'state_label': ticket_state_labels.get(ticket.state, ticket.state),
                            'timeline': ticket_timeline,
                        })
                    workorders_payload.append({
                        'record': wo_sudo,
                        'state_label': workorder_state_labels.get(wo_sudo.state, wo_sudo.state),
                        'ordered_qty': wo_sudo.total_qty or wo_sudo.quantity_ordered or 0.0,
                        'delivered_qty': wo_sudo.quantity_delivered or 0.0,
                        'remaining_qty': wo_sudo.quantity_remaining or 0.0,
                        'delivery_date': wo_sudo.delivery_date,
                        'tickets': tickets_data,
                    })
            timeline = helper.prepare_order_timeline(order_sudo)
            orders_data.append({
                'order': order_sudo,
                'timeline': timeline,
                'quality_lines': order_sudo.order_line,
                'logistics_pickings': order_sudo.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing'),
                'finance_invoices': order_sudo.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice'),
                'workorders': workorders_payload,
            })

        category_summary = {}
        if selected_category_is_rmc:
            category_summary = helper.get_category_summary(contact_partner, selected_category)

        values = self._prepare_portal_layout_values()
        def _format_datetime(dt):
            if not dt:
                return ''
            if isinstance(dt, date_obj) and not isinstance(dt, datetime):
                dt = datetime.combine(dt, time_obj())
            return format_datetime(request.env, dt)

        def _format_date(dt):
            if not dt:
                return ''
            return format_date(request.env, dt)

        def _format_amount(amount, currency):
            if currency is None:
                return ''
            return format_amount(request.env, amount, currency)

        values.update({
            'contact_partner': contact_partner,
            'role': contact_partner.get_portal_role_key(),
            'categories': categories,
            'selected_category': selected_category,
            'selected_category_is_rmc': selected_category_is_rmc,
            'orders_data': orders_data,
            'category_summary': category_summary,
            # expose formatting helpers for QWeb usage while avoiding None callables
            'format_datetime': _format_datetime,
            'format_date': _format_date,
            'format_amount': _format_amount,
        })
        return request.render('portal_b2b_multicategory.portal_my_b2b_dashboard', values)
