# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.tools import consteq


class RmcBrandPurchaseController(http.Controller):
    def _get_order(self, order_id, token):
        order = request.env["purchase.order"].sudo().browse(order_id)
        if not order or not order.exists():
            return None
        access_token = order._portal_ensure_token()
        if not token or not consteq(access_token, token):
            return None
        return order

    @http.route(
        "/brand/rfq/<int:order_id>/accept",
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
        csrf=False,
    )
    def brand_rfq_accept(self, order_id, token=None, **kwargs):
        order = self._get_order(order_id, token)
        if not order:
            return request.render(
                "rmc_variant_brand_subcontractor.portal_purchase_invalid", {}
            )
        order.action_rmc_brand_accept()
        url = order.get_portal_url()
        separator = "&" if "?" in url else "?"
        return request.redirect(f"{url}{separator}brand_status=accepted")

    @http.route(
        "/brand/rfq/<int:order_id>/reject",
        type="http",
        auth="public",
        methods=["GET"],
        website=True,
        csrf=False,
    )
    def brand_rfq_reject(self, order_id, token=None, **kwargs):
        order = self._get_order(order_id, token)
        if not order:
            return request.render(
                "rmc_variant_brand_subcontractor.portal_purchase_invalid", {}
            )
        fallback = order.action_rmc_brand_reject()
        if fallback:
            status = "reassigned"
        elif order.rmc_brand_response == "unavailable":
            status = "unavailable"
        else:
            status = "rejected"
        url = order.get_portal_url()
        separator = "&" if "?" in url else "?"
        return request.redirect(f"{url}{separator}brand_status={status}")
