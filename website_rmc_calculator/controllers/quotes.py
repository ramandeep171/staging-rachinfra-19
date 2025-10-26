
from odoo import http, fields
from odoo.http import request
import logging
import math

from odoo.addons.website_sale.models.website import (
    PRICELIST_SELECTED_SESSION_CACHE_KEY,
    PRICELIST_SESSION_CACHE_KEY,
)

_logger = logging.getLogger(__name__)


class RMCQuoteController(http.Controller):
    def _get_active_pricelist(self, partner=None):
        """Return the pricelist currently active for the visitor session."""
        env = request.env
        Pricelist = env["product.pricelist"].sudo()

        pricelist = getattr(request, "pricelist", None)
        if pricelist:
            pricelist = pricelist.sudo()
            if pricelist.exists():
                return pricelist

        session_ids = [
            request.session.get(PRICELIST_SESSION_CACHE_KEY),
            request.session.get(PRICELIST_SELECTED_SESSION_CACHE_KEY),
        ]
        session_ids = [pid for pid in session_ids if pid]
        if session_ids:
            pl_session = Pricelist.browse(session_ids).filtered(lambda pl: pl.active)
            if pl_session:
                return pl_session[0]

        website = getattr(request, "website", None)
        if website:
            getter_names = (
                "get_current_pricelist",
                "_get_current_pricelist",
                "_get_and_cache_current_pricelist",
            )
            for getter in getter_names:
                if hasattr(website, getter):
                    try:
                        pl_candidate = getattr(website, getter)()
                        if pl_candidate:
                            pl_candidate = pl_candidate.sudo()
                            if pl_candidate.exists():
                                return pl_candidate
                    except Exception:
                        continue

        if partner:
            try:
                partner_pl = partner.property_product_pricelist.sudo()
                if partner_pl.exists():
                    return partner_pl
            except Exception:
                pass

        try:
            company_pl = env.company.sudo().property_product_pricelist
            if company_pl and company_pl.exists():
                return company_pl.sudo()
        except Exception:
            pass
        return Pricelist.browse()

    @http.route(
        '/rmc_calculator/request_quote',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST'],
        website=True,
    )
    def request_quote(self, product_id=None, product_tmpl_id=None, qty=0, location=None, city=None, postal_code=None, delivery_date=None,
                      contact_name=None, contact_phone=None, contact_email=None, volume=None, **kw):
        """Create a quotation and CRM lead using website calculator inputs."""
        _logger.info('RMC quote payload: product_id=%s tmpl=%s qty=%s volume=%s contact=%s %s',
                     product_id, product_tmpl_id, qty, volume, contact_name, contact_email)

        env = request.env
        Partner = env['res.partner'].sudo()
        Sale = env['sale.order'].sudo()
        SaleLine = env['sale.order.line'].sudo()
        ProductProduct = env['product.product'].sudo()
        ProductTemplate = env['product.template'].sudo()
        Crm = env['crm.lead'].sudo()
        Team = env['crm.team'].sudo()

        def _parse_float(value):
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        qty_f = _parse_float(qty)
        volume_f = _parse_float(volume)
        if qty_f <= 0 and volume_f > 0:
            qty_f = volume_f
        if qty_f <= 0:
            return {'success': False, 'error': 'invalid_qty', 'message': 'qty must be > 0'}

        prod = None
        try:
            if product_id:
                prod = ProductProduct.browse(int(product_id))
            elif product_tmpl_id:
                tmpl = ProductTemplate.browse(int(product_tmpl_id))
                if tmpl.exists():
                    prod = tmpl.product_variant_id or tmpl.product_variant_ids[:1]
        except Exception:
            prod = None

        if not prod or not prod.exists():
            return {'success': False, 'error': 'product_not_found'}

        # partner resolution with fallback to visitor partner
        partner = None
        if request.session.uid and env.user.partner_id:
            partner = env.user.partner_id.sudo()
        if not partner and (contact_email or contact_phone or contact_name):
            vals = {'name': contact_name or (contact_email.split('@')[0] if contact_email else contact_phone or 'Website Visitor')}
            if contact_email:
                vals['email'] = contact_email
            if contact_phone:
                vals['phone'] = contact_phone
            partner = Partner.create(vals)
        if not partner:
            partner = env.ref('base.public_partner').sudo()

        pricelist = self._get_active_pricelist(partner)

        # locate existing draft quotation for this visitor/customer to avoid duplicates
        order = None
        domain = [('partner_id', '=', partner.id), ('state', 'in', ('draft', 'sent'))]
        if getattr(request, 'website', None):
            domain.append(('website_id', '=', request.website.id))
        try:
            existing_orders = Sale.search(domain, order='id desc', limit=5)
            for quotation in existing_orders:
                for line in quotation.order_line:
                    if line.product_id.id == prod.id and abs(line.product_uom_qty - qty_f) < 0.0001:
                        order = quotation
                        break
                if order:
                    break
        except Exception:
            order = None

        visitor = None
        try:
            visitor = env['website.visitor']._get_visitor_from_request()
        except Exception:
            visitor = None

        city = city or kw.get('city')
        postal_code = postal_code or kw.get('zip') or kw.get('postal_code')

        if not order:
            order_vals = {
                'partner_id': partner.id,
                'partner_invoice_id': partner.id,
                'partner_shipping_id': partner.id,
                'company_id': env.company.id,
            }
            if pricelist:
                order_vals['pricelist_id'] = pricelist.id
            if getattr(request, 'website', None):
                order_vals['website_id'] = request.website.id
            order = Sale.create(order_vals)
            if visitor:
                try:
                    order.visitor_id = visitor.id
                except Exception:
                    pass

        price_unit = prod.list_price
        try:
            if pricelist:
                price_unit = pricelist._get_product_price(prod, qty_f, partner)
        except Exception:
            price_unit = prod.list_price

        add_line = True
        for ln in order.order_line:
            if ln.product_id.id == prod.id and abs(ln.product_uom_qty - qty_f) < 0.0001:
                add_line = False
                break

        if add_line:
            line_vals = {
                'order_id': order.id,
                'product_id': prod.id,
                'name': prod.display_name,
                'product_uom_qty': qty_f,
                'price_unit': price_unit,
            }
            # In Odoo 19, the field is product_uom_id, not product_uom
            if getattr(prod, 'uom_id', False):
                line_vals['product_uom_id'] = prod.uom_id.id
            SaleLine.create(line_vals)

        try:
            team = Team.search([('name', '=', 'rmc_dropshing')], limit=1)
            if not team:
                team = Team.create({'name': 'rmc_dropshing'})
        except Exception:
            team = None

        lead = order.opportunity_id.sudo() if getattr(order, 'opportunity_id', False) else None

        if not lead:
            lead_vals = {
                'name': f'RMC Quote - {prod.display_name}',
                'partner_id': partner.id,
                'contact_name': contact_name or partner.name,
                'phone': contact_phone,
                'email_from': contact_email,
                'type': 'opportunity',
                'team_id': team.id if team else False,
                'description': f'Requested via RMC calculator for {prod.display_name} ({qty_f} m³).',
                'rmc_volume': qty_f,
                'rmc_grade_tmpl_id': prod.product_tmpl_id.id,
                'rmc_variant_id': prod.id,
            }
            if location:
                lead_vals['street'] = location
            if city:
                lead_vals['city'] = city
            if postal_code:
                lead_vals['zip'] = postal_code
            if delivery_date:
                lead_vals['date_deadline'] = delivery_date
            # Note: website_id field doesn't exist in crm.lead in Odoo 19
            # Removed: if getattr(request, 'website', None):
            #     lead_vals['website_id'] = request.website.id
            if visitor:
                try:
                    lead_vals['visitor_ids'] = [(4, visitor.id)]
                except Exception:
                    pass
            lead = Crm.with_context(mail_create_nosubscribe=True, mail_create_nolog=True).create(lead_vals)

        if lead and order and order.opportunity_id != lead:
            try:
                order.write({'opportunity_id': lead.id})
            except Exception:
                _logger.exception('Failed to link order %s to lead %s', order.id, lead.id)

        price_data = self.price_breakdown(product_id=prod.id, qty=qty_f)
        report_url = None
        try:
            # leverage the sale portal route so the access token grants safe report access
            order._portal_ensure_token()
            report_url = order.get_portal_url(report_type='pdf', download=True)
        except Exception:
            report_url = None

        response = {
            'success': True,
            'order_id': order.id,
            'lead_id': lead.id if lead else False,
            'report_url': report_url,
            'price': price_data if isinstance(price_data, dict) and price_data.get('success') else {},
        }
        if lead:
            response['lead_url'] = f"/web#id={lead.id}&model=crm.lead"
        return response

    @http.route(
        '/rmc_calculator/price_breakdown',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST'],
        website=True,
    )
    def price_breakdown(self, product_id=None, product_tmpl_id=None, qty=0, truck_capacity=7, **kw):
        env = request.env
        ProductProduct = env['product.product'].sudo()
        ProductTemplate = env['product.template'].sudo()

        def _parse_float(value):
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        qty_f = _parse_float(qty)
        if qty_f <= 0:
            return {'success': False, 'error': 'invalid_qty'}

        prod = None
        try:
            if product_id:
                prod = ProductProduct.browse(int(product_id))
            elif product_tmpl_id:
                tmpl = ProductTemplate.browse(int(product_tmpl_id))
                if tmpl.exists():
                    prod = tmpl.product_variant_id or tmpl.product_variant_ids[:1]
        except Exception:
            prod = None
        if not prod or not prod.exists():
            return {'success': False, 'error': 'product_not_found'}

        partner = env.user.sudo().partner_id if request.session.uid and env.user.partner_id else env.ref('base.public_partner').sudo()

        pricelist = self._get_active_pricelist(partner)

        currency = (
            (pricelist and pricelist.currency_id)
            or prod.currency_id
            or (getattr(request, 'website', None) and request.website.currency_id)
            or env.company.currency_id
        )
        date_ctx = fields.Date.context_today(prod)

        base_unit_price = prod.list_price
        unit_price = base_unit_price
        price_rule_id = False
        discount_percent = 0.0
        if pricelist:
            try:
                unit_price, price_rule_id = pricelist._get_product_price_rule(
                    prod,
                    qty_f,
                    uom=prod.uom_id,
                    date=date_ctx,
                )
            except Exception:  # noqa: BLE001
                unit_price = base_unit_price
                price_rule_id = False
        if unit_price is None:
            unit_price = base_unit_price

        if pricelist and price_rule_id:
            rule = request.env['product.pricelist.item'].sudo().browse(price_rule_id)
            if rule and rule.exists():
                try:
                    base_before = rule._compute_price_before_discount(
                        product=prod,
                        quantity=qty_f,
                        uom=prod.uom_id,
                        date=date_ctx,
                        currency=currency,
                    )
                except Exception:  # noqa: BLE001
                    base_before = False
                if base_before:
                    base_unit_price = base_before
                if base_unit_price:
                    discount_percent = max((base_unit_price - unit_price) / base_unit_price * 100.0, 0.0)

        base_total = base_unit_price * qty_f
        computed_total = unit_price * qty_f
        discount_value = max(base_total - computed_total, 0.0)
        try:
            truck_cap = float(truck_capacity or 7)
        except Exception:
            truck_cap = 7.0
        truck_cap = truck_cap if truck_cap > 0 else 7.0
        truck_count = max(math.ceil(qty_f / truck_cap), 1)

        return {
            'success': True,
            'currency': currency and currency.name,
            'base_price': base_total,
            'computed_price': computed_total,
            'discount_value': discount_value,
            'discount_rate': discount_value / base_total * 100 if base_total else 0.0,
            'discount_percent': discount_percent,
            'truck_capacity': truck_cap,
            'truck_count': truck_count,
            'price': unit_price,
            'unit_price': unit_price,
        }

    @http.route(
        '/rmc_calculator/create_lead',
        type='json',
        auth='public',
        csrf=False,
        methods=['POST'],
        website=True,
    )
    def create_lead(self, product_id=None, product_tmpl_id=None, qty=0, location=None, contact_name=None, contact_phone=None, contact_email=None, **kw):
        """Create only a crm.lead assigned to sales team 'rmc_dropshing'."""
        _logger.info('create_lead called with payload: product_id=%s product_tmpl_id=%s qty=%s contact=%s %s', product_id, product_tmpl_id, qty, contact_name, contact_email)
        env = request.env
        Partner = env['res.partner'].sudo()
        Crm = env['crm.lead'].sudo()
        Team = env['crm.team'].sudo()
        ProductProduct = env['product.product'].sudo()
        ProductTemplate = env['product.template'].sudo()

        def _parse_float(value):
            try:
                return float(value or 0)
            except Exception:
                return 0.0

        qty_f = _parse_float(qty)

        product = None
        try:
            if product_id:
                product = ProductProduct.browse(int(product_id))
            elif product_tmpl_id:
                tmpl = ProductTemplate.browse(int(product_tmpl_id))
                if tmpl.exists():
                    product = tmpl.product_variant_id or tmpl.product_variant_ids[:1]
        except Exception:
            product = None

        try:
            team = Team.search([('name', '=', 'rmc_dropshing')], limit=1)
            if not team:
                team = Team.create({'name': 'rmc_dropshing'})
        except Exception:
            _logger.exception('crm.team handling failed')
            team = None

        try:
            if request.session.uid and env.user and env.user.partner_id:
                partner = env.user.partner_id.sudo()
            elif contact_email or contact_phone or contact_name:
                vals = {'name': contact_name or (contact_email.split('@')[0] if contact_email else contact_phone or 'Website Visitor')}
                if contact_email:
                    vals['email'] = contact_email
                if contact_phone:
                    vals['phone'] = contact_phone
                partner = Partner.create(vals)
            else:
                partner = env.ref('base.public_partner').sudo()
        except Exception:
            _logger.exception('create_lead partner create failed, using public partner')
            try:
                partner = env.user.partner_id.sudo() if env.user and env.user.partner_id else env.ref('base.public_partner').sudo()
            except Exception:
                partner = env.ref('base.public_partner').sudo()

        city = kw.get('city') or kw.get('contact_city') or None
        postal_code = kw.get('zip') or kw.get('postal_code') or None

        lead_vals = {
            'name': 'RMC Interest: %s' % (product_id or product_tmpl_id or 'Unknown'),
            'partner_id': partner.id,
            'contact_name': contact_name or partner.name,
            'type': 'opportunity',
            'description': 'Added to cart / expressed interest via website RMC calculator. Volume: %s m3. Location: %s %s %s' % (
                qty,
                location or '',
                city or '',
                postal_code or '',
            ),
            'team_id': team.id if team else False,
            'rmc_volume': qty_f,
        }
        if location:
            lead_vals['street'] = location
        if city:
            lead_vals['city'] = city
        if postal_code:
            lead_vals['zip'] = postal_code
        if product and product.exists():
            lead_vals.update({
                'rmc_grade_tmpl_id': product.product_tmpl_id.id,
                'rmc_variant_id': product.id,
            })
        try:
            # try to find an existing lead for this partner and product string
            try:
                domain = [('partner_id', '=', partner.id), ('type', '=', 'opportunity'), ('name', 'ilike', product_id or product_tmpl_id or '')]
                existing = Crm.search(domain, order='id desc', limit=1)
                if existing:
                    return {'success': True, 'lead_id': existing.id}
            except Exception:
                _logger.exception('create_lead search failed')

            try:
                with request.env.cr.savepoint():
                    lead = Crm.with_context(mail_create_nosubscribe=True, mail_create_nolog=True).create(lead_vals)
            except Exception:
                _logger.exception('failed creating crm.lead (create_lead) inside savepoint')
                return {'success': False, 'error': 'create_failed'}
            return {'success': True, 'lead_id': lead.id}
        except Exception:
            _logger.exception('unexpected error in create_lead')
            return {'success': False, 'error': 'create_failed'}
