# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    # Partner-based CC/BCC (contact picker)
    cc_partner_ids = fields.Many2many(
        'res.partner',
        'mail_compose_message_cc_partner_rel',
        'wizard_id',
        'partner_id',
        string='CC Partners',
        help='Carbon Copy: Additional contacts who will receive a copy of the email'
    )
    bcc_partner_ids = fields.Many2many(
        'res.partner',
        'mail_compose_message_bcc_partner_rel',
        'wizard_id',
        'partner_id',
        string='BCC Partners',
        help='Blind Carbon Copy: Hidden contacts who will receive a copy of the email'
    )

    # Email-based CC/BCC (manual entry)
    email_cc = fields.Char(
        string='CC Emails',
        help='Carbon Copy: Additional email addresses (comma-separated)'
    )
    email_bcc = fields.Char(
        string='BCC Emails',
        help='Blind Carbon Copy: Hidden email addresses (comma-separated)'
    )

    @api.onchange('cc_partner_ids')
    def _onchange_cc_partner_ids(self):
        """Auto-populate email_cc from selected partners"""
        if self.cc_partner_ids:
            emails = [p.email for p in self.cc_partner_ids if p.email]
            if emails:
                existing = self.email_cc.split(',') if self.email_cc else []
                existing = [e.strip() for e in existing if e.strip()]
                # Merge partner emails with existing manual emails
                all_emails = list(set(emails + existing))
                self.email_cc = ', '.join(all_emails)

    @api.onchange('bcc_partner_ids')
    def _onchange_bcc_partner_ids(self):
        """Auto-populate email_bcc from selected partners"""
        if self.bcc_partner_ids:
            emails = [p.email for p in self.bcc_partner_ids if p.email]
            if emails:
                existing = self.email_bcc.split(',') if self.email_bcc else []
                existing = [e.strip() for e in existing if e.strip()]
                # Merge partner emails with existing manual emails
                all_emails = list(set(emails + existing))
                self.email_bcc = ', '.join(all_emails)

    def _prepare_mail_values(self, res_ids):
        """Override to include CC and BCC in mail values (mass mail mode only)"""
        mail_values = super()._prepare_mail_values(res_ids)

        # Add CC and BCC to each mail value in mass mail mode
        if self.composition_mode == 'mass_mail':
            for res_id in res_ids:
                if res_id in mail_values:
                    if self.email_cc:
                        mail_values[res_id]['email_cc'] = self.email_cc
                    if self.email_bcc:
                        mail_values[res_id]['email_bcc'] = self.email_bcc

        return mail_values

    def _action_send_mail_comment(self, res_ids):
        """Override to handle CC/BCC in comment mode"""
        self.ensure_one()

        # Call parent to post messages
        messages = super()._action_send_mail_comment(res_ids)

        # If CC or BCC specified, update the related mail.mail records
        if self.email_cc or self.email_bcc:
            # Find mail.mail records created from these messages
            mail_ids = self.env['mail.mail'].sudo().search([
                ('mail_message_id', 'in', messages.ids)
            ])

            # Update CC/BCC
            for mail in mail_ids:
                if self.email_cc:
                    mail.email_cc = self.email_cc
                if self.email_bcc:
                    mail.email_bcc = self.email_bcc

        return messages
