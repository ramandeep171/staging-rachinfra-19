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

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if order._rmc_is_brand_order():
                order._portal_ensure_token()
                order.rmc_brand_response = "pending"
                order._rmc_send_brand_rfq(auto_send=True)
        return orders

    def _rmc_is_brand_order(self):
        self.ensure_one()
        return any(
            line.product_id and line.product_id.allowed_subcontractor_ids
            for line in self.order_line
            if not line.display_type
        )

    def _rmc_send_brand_rfq(self, auto_send=False):
        template = self.env.ref(
            "rmc_variant_brand_subcontractor.mail_template_brand_rfq",
            raise_if_not_found=False,
        )
        for order in self:
            if not order._rmc_is_brand_order():
                continue
            order._portal_ensure_token()
            if order.state == "draft":
                order.state = "sent"
            if template:
                template.with_context(force_send=auto_send).send_mail(
                    order.id, force_send=auto_send
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
        self.rmc_brand_response = "accepted"

    def action_rmc_brand_reject(self):
        self.ensure_one()
        if not self._rmc_is_brand_order():
            return False
        next_partner = self._rmc_find_next_partner()
        if not next_partner:
            self.rmc_brand_response = "unavailable"
            self.message_post(
                body=_(
                    "Vendor %(vendor)s rejected the RFQ and no alternative subcontractor is configured.",
                    vendor=self.partner_id.display_name,
                )
            )
            return False

        if consteq(str(next_partner.id), str(self.partner_id.id)):
            return False

        self.message_post(
            body=_(
                "Vendor %(old)s rejected the RFQ. Resending to %(new)s.",
                old=self.partner_id.display_name,
                new=next_partner.display_name,
            )
        )
        self.write({"partner_id": next_partner.id, "state": "draft"})
        self._onchange_partner_id()
        self.rmc_brand_response = "pending"
        self._rmc_send_brand_rfq(auto_send=True)
        return True

    def _rmc_find_next_partner(self):
        self.ensure_one()
        current_partner = self.partner_id
        candidate_scores = {}
        has_brand_lines = False

        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            ptav = get_variant_brand_ptav(line.product_id)
            if not ptav:
                continue
            mappings = ptav.get_current_subcontractor_maps()
            if not mappings:
                continue
            has_brand_lines = True
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

            if not considered:
                return False

            line_candidates = {
                partner.id: next(m.sequence for m in mappings if m.partner_id == partner)
                for partner in considered
            }
            if not line_candidates:
                return False

            if not candidate_scores:
                candidate_scores = line_candidates
            else:
                candidate_scores = {
                    partner_id: min(candidate_scores[partner_id], line_candidates[partner_id])
                    for partner_id in candidate_scores.keys() & line_candidates.keys()
                }
            if not candidate_scores:
                return False

        if not has_brand_lines or not candidate_scores:
            return False

        next_partner_id = min(candidate_scores.items(), key=lambda item: item[1])[0]
        return self.env["res.partner"].browse(next_partner_id)
