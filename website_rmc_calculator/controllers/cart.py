from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class RMCCartController(http.Controller):
    
    @http.route('/rmc/cart/add', type='http', auth='public', methods=['POST', 'GET'], website=True, csrf=False)
    def add_to_cart(self, product_id=None, add_qty=1, **kwargs):
        """Simple endpoint to add product to cart without CSRF"""
        _logger.info('=== RMC ADD TO CART START === product_id=%s, add_qty=%s', product_id, add_qty)
        try:
            if not product_id:
                _logger.warning('No product_id provided')
                return request.redirect('/shop/cart')

            product_id = int(product_id)
            add_qty = float(add_qty)
            _logger.info('Parsed: product_id=%s (type=%s), add_qty=%s (type=%s)',
                        product_id, type(product_id), add_qty, type(add_qty))
            
            # Get or create sale order (cart) - Odoo 19 compatible
            # In Odoo 19, use website_sale controller's method
            website = request.env['website'].get_current_website()
            partner = request.env.user.partner_id

            # Get current order from session or create new one
            order_id = request.session.get('sale_order_id')
            order = None

            if order_id:
                order = request.env['sale.order'].sudo().browse(order_id)
                if not order or not order.exists() or order.state != 'draft':
                    order = None

            if not order:
                # Create new cart order
                order = request.env['sale.order'].sudo().create({
                    'partner_id': partner.id,
                    'website_id': website.id,
                    'state': 'draft',
                })
                request.session['sale_order_id'] = order.id
                _logger.info('Created new cart order: id=%s', order.id)
            else:
                _logger.info('Using existing cart order: id=%s', order.id)
            
            # Verify product exists
            product = request.env['product.product'].sudo().browse(product_id)
            _logger.info('Product lookup: id=%s, exists=%s, name=%s', product_id, product.exists(), product.name if product.exists() else 'N/A')

            if not product.exists():
                _logger.error('Product %s not found', product_id)
                return request.redirect('/shop/cart')

            # Add product to cart by creating order line directly
            _logger.info('Adding product to cart: product_id=%s, add_qty=%s', product_id, add_qty)

            # Check if product already in cart
            existing_line = order.order_line.filtered(lambda l: l.product_id.id == product_id)

            if existing_line:
                # Update existing line
                existing_line[0].product_uom_qty += add_qty
                _logger.info('Updated existing line, new qty: %s', existing_line[0].product_uom_qty)
            else:
                # Create new order line
                order_line = request.env['sale.order.line'].sudo().create({
                    'order_id': order.id,
                    'product_id': product_id,
                    'product_uom_qty': add_qty,
                    'price_unit': product.list_price,
                })
                _logger.info('Created new order line: id=%s', order_line.id)

            _logger.info('=== CART UPDATE SUCCESS === Order now has %s lines', len(order.order_line))

            return request.redirect('/shop/cart')
            
        except Exception as e:
            _logger.exception('Failed to add to cart: %s', e)
            return request.redirect('/shop/cart')
