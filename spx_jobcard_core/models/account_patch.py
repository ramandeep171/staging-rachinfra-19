# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class AccountMove(models.Model):
    _inherit = "account.move"

    jobcard_id = fields.Many2one(
        "maintenance.jobcard",
        string="Job Card",
        help="Set on a Vendor Bill to push its lines as Job Card Vendor cost lines."
    )

    # ---- one place sync (idempotent, sudo, robust) ----
    def _spx_push_lines_to_jobcard(self, summary=False):
        """
        Create vendor cost lines on the linked Job Card from this posted Vendor Bill.
        - summary=False: one cost line per invoice line (default)
        - summary=True : one aggregated cost line per bill
        Always deletes previous lines for (bill, jobcard) pair first to avoid duplicates.
        """
        Cost = self.env["maintenance.jobcard.cost.line"].sudo()
        for move in self:
            if move.move_type != "in_invoice" or move.state != "posted" or not move.jobcard_id:
                continue

            # purge old
            Cost.search([
                ("vendor_bill_id", "=", move.id),
                ("jobcard_id", "=", move.jobcard_id.id),
            ]).unlink()

            if summary:
                # single summarized line per bill
                Cost.create({
                    "jobcard_id": move.jobcard_id.id,
                    "line_type": "vendor",
                    "description": move.ref or move.name or _("Vendor Bill"),
                    "qty": 1.0,
                    "uom_id": False,
                    "unit_cost": abs(move.amount_untaxed) if "amount_untaxed" in move._fields else abs(move.amount_total),
                    "vendor_bill_id": move.id,
                })
            else:
                # one line per invoice line (skip display sections/notes)
                invoice_lines = move.invoice_line_ids.filtered(lambda l: not l.display_type)
                if not invoice_lines:
                    # fallback to summary if no lines (edge customizations)
                    self._spx_push_lines_to_jobcard(summary=True)
                    continue

                for line in invoice_lines:
                    Cost.create({
                        "jobcard_id": move.jobcard_id.id,
                        "line_type": "vendor",
                        "product_id": line.product_id.id or False,  # optional
                        "description": line.name or (line.product_id and line.product_id.display_name) or _("Vendor Line"),
                        "qty": (line.quantity or 1.0),
                        "uom_id": (getattr(line, "product_uom_id", False) or (line.product_id and line.product_id.uom_id.id) or False),
                        "unit_cost": ((line.price_subtotal / (line.quantity or 1.0)) if (line.quantity or 0) else line.price_subtotal),
                        "vendor_bill_id": move.id,
                    })

    def action_post(self):
        res = super().action_post()
        # after posting, push lines (per-line mode by default)
        self._spx_push_lines_to_jobcard(summary=False)
        return res

    def write(self, vals):
        need_sync = self.browse()
        # if jobcard set/changed OR state becomes posted, resync after write
        if "jobcard_id" in vals or (vals.get("state") == "posted"):
            need_sync |= self
        res = super().write(vals)
        if need_sync:
            need_sync._spx_push_lines_to_jobcard(summary=False)
        return res
