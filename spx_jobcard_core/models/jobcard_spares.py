# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MaintenanceJobcardSpare(models.Model):
    _name = "maintenance.jobcard.spare"
    _description = "Job Card Spare Issue"
    _order = "id desc"

    jobcard_id = fields.Many2one("maintenance.jobcard", string="Job Card", required=True, ondelete="cascade")
    request_id = fields.Many2one("maintenance.request", string="Request")
    product_id = fields.Many2one("product.product", string="Spare Part")
    description = fields.Char(string="Description")
    qty = fields.Float(string="Qty", default=1.0)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    unit_cost = fields.Float(string="Unit Cost")
    amount_total = fields.Float(string="Amount", compute="_compute_amount", store=True)
    picking_id = fields.Many2one("stock.picking", string="Picking", readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('issued', 'Issued'), ('cancel', 'Cancelled')], default='draft')
    company_id = fields.Many2one(related='jobcard_id.company_id', store=True, readonly=True)

    @api.onchange('product_id')
    def _onchange_product(self):
        for rec in self:
            if rec.product_id:
                rec.uom_id = rec.product_id.uom_id
                if not rec.description:
                    rec.description = rec.product_id.display_name

    @api.depends('qty', 'unit_cost')
    def _compute_amount(self):
        for rec in self:
            rec.amount_total = (rec.qty or 0.0) * (rec.unit_cost or 0.0)
