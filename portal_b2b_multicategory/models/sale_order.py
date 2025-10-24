# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        res = super().action_confirm()
        self._sync_portal_categories()
        return res

    def _sync_portal_categories(self):
        """Populate partner portal categories from confirmed orders."""
        Category = self.env['product.category']
        for order in self:
            categories = Category.browse()
            for line in order.order_line:
                if line.product_id and line.product_id.categ_id:
                    categories |= line.product_id.categ_id
            if not categories:
                continue
            partner = order.partner_id
            if partner:
                partner.sudo().add_portal_categories(categories)
