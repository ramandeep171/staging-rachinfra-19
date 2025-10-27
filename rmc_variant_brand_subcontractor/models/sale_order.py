# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_purchase_orders(self):
        purchase_orders = super()._get_purchase_orders()
        extras = self.env["purchase.order"].search(
            [
                ("rmc_sale_order_id", "=", self.id),
                ("id", "not in", purchase_orders.ids),
            ]
        )
        return (purchase_orders | extras)
