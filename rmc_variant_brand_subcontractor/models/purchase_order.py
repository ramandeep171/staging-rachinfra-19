# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.tools import consteq

from .brand_utils import get_variant_brand_ptav


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    rmc_brand_response = fields.Selection(
        [
            ("pending", "Waiting Vendor Response"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("unavailable", "No Subcontractor Available"),
        ],
        string="Brand RFQ Status",
        default="pending",
        tracking=True,
    )
    rmc_sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Source Sale Order",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if self.env.context.get("rmc_skip_brand_autosend"):
                continue
            brand_order = order._rmc_is_brand_order()
            order._portal_ensure_token()
            if brand_order:
                order.rmc_brand_response = "pending"
            if not order.rmc_sale_order_id:
                sale_orders = order.order_line.mapped("sale_line_id.order_id")
                if sale_orders:
                    order.rmc_sale_order_id = sale_orders[:1].id
            order._rmc_send_brand_rfq(auto_send=True, force=not brand_order)
        return orders

    def _rmc_is_brand_order(self):
        self.ensure_one()
        return any(
            line.product_id and line.product_id.allowed_subcontractor_ids
            for line in self.order_line
            if not line.display_type
        )

    def _rmc_send_brand_rfq(self, auto_send=False, force=False):
        template = self.env.ref(
            "rmc_variant_brand_subcontractor.mail_template_brand_rfq",
            raise_if_not_found=False,
        )
        for order in self:
            if not force and not order._rmc_is_brand_order():
                continue
            order._portal_ensure_token()
            if order.state == "draft":
                order.state = "sent"
            if template:
                template.sudo().with_context(force_send=True).send_mail(
                    order.id, force_send=True
                )
            else:
                order.message_post(
                    body=_(
                        "RFQ ready for %(vendor)s (Brand subcontractor workflow).",
                        vendor=order.partner_id.display_name,
                    )
                )

    def action_rmc_brand_accept(self):
        self.ensure_one()
        if not self._rmc_is_brand_order():
            return
        if self.rmc_brand_response == "accepted":
            return
        if self.state in ("draft", "sent"):
            self.message_post(
                body=_("Vendor %(vendor)s accepted the RFQ.", vendor=self.partner_id.display_name)
            )
            self.button_confirm()
            if self.state == "to approve":
                self.sudo().button_approve()
            if self.state != "purchase":
                self.write({
                    "state": "purchase",
                    "date_approve": fields.Datetime.now(),
                })
        self.rmc_brand_response = "accepted"
        self.message_post(body=_("Brand RFQ accepted; purchase order confirmed."))

    def action_rmc_brand_reject(self):
        self.ensure_one()
        if not self._rmc_is_brand_order():
            self.button_cancel()
            self.rmc_brand_response = "rejected"
            return False
        next_info = self._rmc_find_next_partner()
        if not next_info:
            self.rmc_brand_response = "unavailable"
            self.message_post(
                body=_(
                    "Vendor %(vendor)s rejected the RFQ and no alternative subcontractor is configured.",
                    vendor=self.partner_id.display_name,
                )
            )
            self.button_cancel()
            return False

        next_partner, source = next_info

        self.button_cancel()
        self.rmc_brand_response = "rejected"

        sale_orders = self.order_line.mapped("sale_line_id.order_id")
        sale_origin = sale_orders[:1].name if sale_orders else False
        new_order_vals = {
            "partner_id": next_partner.id,
            "state": "draft",
            "rmc_brand_response": "pending",
            "origin": sale_origin or self.origin or self.name,
        }
        # Propagate procurement group when available to keep link with sale order
        if "group_id" in self._fields and getattr(self, "group_id", False):
            new_order_vals["group_id"] = self.group_id.id

        new_order = self.with_context(rmc_skip_brand_autosend=True).copy(new_order_vals)
        if sale_orders and hasattr(new_order, "rmc_sale_order_id"):
            new_order.rmc_sale_order_id = sale_orders[:1].id
        if hasattr(new_order, "_onchange_partner_id"):
            new_order._onchange_partner_id()
        else:
            new_order.onchange_partner_id()
        used_original_ids = set()
        for line in new_order.order_line.filtered(lambda l: not l.display_type and l.product_id):
            original_line = line._origin if line._origin in self.order_line else False
            if not original_line:
                candidates = self.order_line.filtered(
                    lambda l: not l.display_type
                    and l.product_id == line.product_id
                    and l.id not in used_original_ids
                ).sorted(key=lambda l: (l.sequence, l.id))
                original_line = candidates[:1]
            sale_line = original_line.sale_line_id if original_line else False
            if hasattr(line, "_onchange_product_id"):
                line._onchange_product_id()
            else:
                line.onchange_product_id()
            if source == "supplier":
                line.x_subcontractor_id = next_partner
            if sale_line:
                if original_line:
                    used_original_ids.add(original_line.id)
                line.write({"sale_line_id": sale_line.id})
        new_order.message_post(
            body=_(
                "RFQ created from %(origin)s after vendor %(old)s rejected. You are next priority subcontractor.",
                origin=self.name,
                old=self.partner_id.display_name,
            )
        )
        self.message_post(
            body=_(
                "Vendor %(old)s rejected the RFQ. Created new RFQ %(new)s for %(partner)s.",
                old=self.partner_id.display_name,
                new=new_order.name,
                partner=next_partner.display_name,
            )
        )
        new_order._rmc_send_brand_rfq(auto_send=True, force=source != "brand")
        if sale_orders:
            sale_orders.invalidate_model(['purchase_order_count'])
        return new_order

    def _rmc_find_next_partner(self):
        self.ensure_one()
        current_partner = self.partner_id
        brand_scores = {}
        has_brand_lines = False
        supplier_scores = {}

        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            ptav = get_variant_brand_ptav(line.product_id)
            if not ptav:
                mappings = []
            else:
                mappings = ptav.get_current_subcontractor_maps()
                if mappings:
                    has_brand_lines = True
            if mappings:
                partner_order = [m.partner_id for m in mappings]
                current_index = next(
                    (idx for idx, partner in enumerate(partner_order) if partner == current_partner),
                    None,
                )

                if current_index is not None:
                    considered = partner_order[current_index + 1 :]
                else:
                    considered = partner_order

                considered = [partner for partner in considered if partner != current_partner]
                if not considered:
                    considered = [partner for partner in partner_order if partner != current_partner]

                line_candidates = {
                    partner.id: next(m.sequence for m in mappings if m.partner_id == partner)
                    for partner in considered
                }
                if line_candidates:
                    if not brand_scores:
                        brand_scores = line_candidates
                    else:
                        brand_scores = {
                            partner_id: min(brand_scores[partner_id], line_candidates[partner_id])
                            for partner_id in brand_scores.keys() & line_candidates.keys()
                        }
            # Supplier fallback
            suppliers = line.product_id.seller_ids.filtered(
                lambda s: s.partner_id != current_partner
                and (not s.company_id or s.company_id == self.company_id)
            )
            for supplier in suppliers:
                partner = supplier.partner_id
                supplier_scores[partner.id] = min(
                    supplier_scores.get(partner.id, supplier.sequence or 100),
                    supplier.sequence or 100,
                )

        if brand_scores:
            next_partner_id = min(brand_scores.items(), key=lambda item: item[1])[0]
            return self.env["res.partner"].browse(next_partner_id), "brand"

        if supplier_scores:
            next_partner_id = min(supplier_scores.items(), key=lambda item: item[1])[0]
            return self.env["res.partner"].browse(next_partner_id), "supplier"

        if has_brand_lines:
            return False

        # No brand lines; rely solely on suppliers if any were available earlier
        return False
