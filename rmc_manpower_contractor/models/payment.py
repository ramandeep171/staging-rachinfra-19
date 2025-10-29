# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='RMC Agreement',
        help='Link to RMC contractor agreement'
    )

    @api.constrains('agreement_id', 'move_type')
    def _check_payment_hold(self):
        """
        Before creating/validating a vendor bill linked to an agreement,
        check if payment is on hold
        """
        for move in self:
            if move.agreement_id and move.move_type == 'in_invoice':
                if move.agreement_id.payment_hold:
                    reasons = move.agreement_id.payment_hold_reason or 'Unknown reasons'
                    raise ValidationError(
                        _('Payment on hold for agreement %s.\n\nReasons:\n%s') % 
                        (move.agreement_id.name, reasons)
                    )
                
                if not move.agreement_id.is_signed():
                    raise ValidationError(
                        _('Cannot create vendor bill: Agreement %s is not signed yet.') % 
                        move.agreement_id.name
                    )

    def action_post(self):
        """Override to check payment hold before posting"""
        for move in self:
            if move.agreement_id and move.move_type == 'in_invoice':
                if move.agreement_id.payment_hold:
                    raise ValidationError(
                        _('Cannot post bill: Payment on hold for agreement %s.\n\n%s') % 
                        (move.agreement_id.name, move.agreement_id.payment_hold_reason)
                    )
        return super(AccountMove, self).action_post()
