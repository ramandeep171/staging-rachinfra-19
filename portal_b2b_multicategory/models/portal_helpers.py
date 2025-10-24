# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.tools import format_datetime


class PortalB2BHelper(models.AbstractModel):
    _name = 'portal.b2b.helper'
    _description = 'Helper methods for the B2B multi-category portal'

    @api.model
    def _get_commercial_partner(self, partner):
        partner.ensure_one()
        return partner.commercial_partner_id or partner

    @api.model
    def get_partner_orders(self, partner, category=None, limit=20):
        """Fetch confirmed and ongoing orders for the portal partner."""
        if not partner:
            return self.env['sale.order']
        partner = partner.sudo()
        commercial_partner = self._get_commercial_partner(partner)
        domain = [
            ('partner_id.commercial_partner_id', '=', commercial_partner.id),
        ]
        if category:
            domain.append(('order_line.product_id.categ_id', 'in', category.ids))
        return self.env['sale.order'].sudo().search(domain, limit=limit, order='date_order desc, id desc')

    @api.model
    def prepare_order_timeline(self, order):
        """Build the chronological timeline for the customer portal."""
        order = order.sudo()
        is_rmc_order = bool(getattr(order, 'is_rmc_order', False))
       
        timeline = []

        is_confirmed = order.state in ('sale', 'done')
        timeline.append({
            'key': 'confirmed',
            'label': _('Order Confirmed'),
            'completed': is_confirmed,
            'date': order.date_order,
            'details': _('Order %s confirmed.') % (order.name,),
        })

        pickings = order.picking_ids.filtered(lambda p: p.state not in ('draft', 'cancel'))
        plant_date = False
        if pickings:
            ordered_pickings = pickings.sorted(lambda p: p.scheduled_date or p.create_date or p.id)
            plant_date = ordered_pickings[0].scheduled_date or ordered_pickings[0].create_date
        timeline.append({
            'key': 'plant_check',
            'label': _('Plant Approval / Check'),
            'completed': bool(pickings),
            'date': plant_date,
            'details': _('Awaiting plant approval.') if not pickings else _('Plant processing started.'),
        })

        picking_move_field = 'move_ids_without_package' if 'move_ids_without_package' in self.env['stock.picking']._fields else 'move_ids'
        production_moves = pickings.mapped(picking_move_field).filtered(lambda m: m.state in ('assigned', 'done'))
        production_date = False
        if production_moves:
            production_moves = production_moves.sorted(lambda m: m.date_deadline or m.date or m.create_date or m.id)
            production_date = production_moves[0].date_deadline or production_moves[0].date or production_moves[0].create_date
        timeline.append({
            'key': 'production',
            'label': _('In Production'),
            'completed': bool(production_moves),
            'date': production_date,
            'details': _('Stock moves reserved for production.') if production_moves else _('Waiting for production scheduling.'),
        })

        outgoing_pickings = pickings.filtered(lambda p: p.picking_type_code == 'outgoing')
        dispatched_pickings = outgoing_pickings.filtered(lambda p: p.state in ('assigned', 'done'))
        dispatch_date = False
        if dispatched_pickings:
            dispatched_pickings = dispatched_pickings.sorted(lambda p: p.date_done or p.scheduled_date or p.create_date or p.id)
            dispatch_date = dispatched_pickings[0].date_done or dispatched_pickings[0].scheduled_date or dispatched_pickings[0].create_date
        timeline.append({
            'key': 'dispatched',
            'label': _('Dispatched'),
            'completed': bool(dispatched_pickings),
            'date': dispatch_date,
            'details': _('Shipment prepared.') if dispatched_pickings else _('Shipment pending dispatch.'),
        })

        delivered_pickings = outgoing_pickings.filtered(lambda p: p.state == 'done')
        delivery_date = False
        if delivered_pickings:
            delivered_pickings = delivered_pickings.sorted(lambda p: p.date_done or p.create_date or p.id)
            delivery_date = delivered_pickings[0].date_done or delivered_pickings[0].create_date
        timeline.append({
            'key': 'delivered',
            'label': _('Delivered'),
            'completed': bool(delivered_pickings),
            'date': delivery_date,
            'details': _('Shipment delivered to customer.') if delivered_pickings else _('Delivery in transit.'),
        })

        invoices = order.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted')
        invoice_date = False
        if invoices:
            invoices = invoices.sorted(lambda inv: inv.invoice_date or inv.date or inv.create_date or inv.id)
            invoice_date = invoices[0].invoice_date or invoices[0].date or invoices[0].create_date
        timeline.append({
            'key': 'invoiced',
            'label': _('Invoiced'),
            'completed': bool(invoices),
            'date': invoice_date,
            'details': _('Invoice posted.') if invoices else _('Awaiting invoice posting.'),
        })

        return timeline

  

    @api.model
    def prepare_rmc_ticket_timeline(self, ticket):
        """Specialised timeline for an RMC workorder ticket."""
        ticket = ticket.sudo()
        TruckLoading = self.env['rmc.truck_loading'].sudo()
        PlantCheck = self.env['rmc.plant_check'].sudo()
        Docket = self.env['rmc.docket'].sudo()
        AccountMove = self.env['account.move'].sudo()

        sale_order = ticket.workorder_id.sale_order_id.sudo() if ticket.workorder_id and ticket.workorder_id.sale_order_id else self.env['sale.order'].sudo()
        helpdesk_ticket = ticket.helpdesk_ticket_id.sudo() if ticket.helpdesk_ticket_id else self.env['helpdesk.ticket'].sudo()
        truck_loadings = helpdesk_ticket.truck_loading_ids.sudo() if helpdesk_ticket else TruckLoading.browse([])
        plant_checks = truck_loadings.mapped('plant_check_id').sudo() if truck_loadings else PlantCheck.browse([])
        dockets = helpdesk_ticket.docket_ids.sudo() if helpdesk_ticket else Docket.browse([])
        invoices = dockets.mapped('invoice_id').sudo() if dockets else AccountMove.browse([])

        def _earliest_datetime(records, *field_names):
            values = []
            for record in records:
                for field_name in field_names:
                    value = getattr(record, field_name, False)
                    if value:
                        values.append(value)
            return min(values) if values else False

        timeline = []

        order_confirmed = sale_order.filtered(lambda so: so.state in ('sale', 'done'))
        timeline.append({
            'key': 'order_confirmed',
            'label': _('Order Confirmed'),
            'completed': bool(order_confirmed),
            'date': sale_order.date_order if sale_order else False,
            'details': _('Order %s confirmed.') % sale_order.name if order_confirmed else _('Waiting for order confirmation.'),
        })

        confirmed_tickets = ticket.filtered(lambda t: t.state in ('in_progress', 'completed'))
        timeline.append({
            'key': 'ticket_confirmed',
            'label': _('Ticket Confirmed'),
            'completed': bool(confirmed_tickets),
            'date': _earliest_datetime(confirmed_tickets, 'write_date', 'create_date'),
            'details': _('Tickets are in progress or completed.') if confirmed_tickets else _('Awaiting ticket confirmation.'),
        })

        active_loadings = truck_loadings.filtered(lambda tl: tl.loading_status in ('in_progress', 'completed'))
        timeline.append({
            'key': 'truck_loading',
            'label': _('Truck Loading'),
            'completed': bool(active_loadings),
            'date': _earliest_datetime(active_loadings, 'loading_start_time', 'loading_date'),
            'details': _('Truck loading is underway.') if active_loadings else _('Truck loading not started yet.'),
        })

        completed_checks = plant_checks.filtered(lambda pc: pc.check_status == 'completed')
        timeline.append({
            'key': 'plant_check',
            'label': _('Plant Approval / Check'),
            'completed': bool(completed_checks),
            'date': _earliest_datetime(completed_checks, 'completed_date', 'check_date'),
            'details': _('Plant checks completed for at least one load.') if completed_checks else _('Plant checks pending.'),
        })

        dispatched_dockets = dockets.filtered(lambda d: d.state in ('dispatched', 'delivered'))
        timeline.append({
            'key': 'dispatched',
            'label': _('Dispatched'),
            'completed': bool(dispatched_dockets),
            'date': _earliest_datetime(dispatched_dockets, 'write_date'),
            'details': _('Loads dispatched to site.') if dispatched_dockets else _('Dispatch pending.'),
        })

        posted_invoices = invoices.filtered(lambda inv: inv.state == 'posted')
        timeline.append({
            'key': 'invoiced',
            'label': _('Invoiced'),
            'completed': bool(posted_invoices),
            'date': _earliest_datetime(posted_invoices, 'invoice_date', 'date'),
            'details': _('Customer invoice posted.') if posted_invoices else _('Invoice yet to be posted.'),
        })

        delivered_dockets = dockets.filtered(lambda d: d.state == 'delivered')
        timeline.append({
            'key': 'delivered',
            'label': _('Delivered'),
            'completed': bool(delivered_dockets),
            'date': _earliest_datetime(delivered_dockets, 'write_date'),
            'details': _('Delivery marked complete.') if delivered_dockets else _('Delivery outstanding.'),
        })

        from datetime import datetime, time as time_obj
        for step in timeline:
            dt_value = step.get('date')
            if dt_value and not isinstance(dt_value, datetime):
                dt_value = datetime.combine(dt_value, time_obj())
            step['display_date'] = format_datetime(self.env, dt_value) if dt_value else ''

        return timeline

    @api.model
    def get_category_summary(self, partner, category):
        """Aggregate simple KPIs for a given product category."""
        if not partner or not category:
            return {}
        partner = partner.sudo()
        commercial_partner = self._get_commercial_partner(partner)
        domain = [
            ('partner_id.commercial_partner_id', '=', commercial_partner.id),
            ('order_line.product_id.categ_id', 'in', category.ids),
        ]
        orders = self.env['sale.order'].sudo().search(domain)
        if not orders:
            return {}

        lines = orders.mapped('order_line').filtered(lambda l: l.product_id.categ_id == category)
        total_qty = sum(lines.mapped('product_uom_qty'))
        delivered_qty = sum(lines.mapped('qty_delivered'))
        total_amount = sum(orders.mapped('amount_total'))
        posted_invoices = orders.mapped('invoice_ids').filtered(lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted')
        invoice_amount = sum(posted_invoices.mapped('amount_total'))
        last_order_date = max(orders.mapped('date_order')) if orders else False
        currency = orders[:1].currency_id if orders and orders[:1].currency_id else False

        return {
            'order_count': len(orders),
            'total_qty': total_qty,
            'delivered_qty': delivered_qty,
            'total_amount': total_amount,
            'invoice_amount': invoice_amount,
            'last_order_date': last_order_date,
            'currency': currency,
        }

    @api.model
    def get_orders_grouped_by_category(self, partner):
        """Return a mapping of category -> orders for the dashboard."""
        if not partner:
            return {}
        categories = partner.get_portal_dashboard_categories()
        return {
            category: self.get_partner_orders(partner, category=category)
            for category in categories
        }

    @api.model
    def get_order_workorders(self, order):
        """Fetch RMC workorders linked to a sale order."""
        if not order:
            return self.env['dropshipping.workorder']
        return self.env['dropshipping.workorder'].sudo().search(
            [('sale_order_id', '=', order.id)],
            order='date_order desc, id desc'
        )
