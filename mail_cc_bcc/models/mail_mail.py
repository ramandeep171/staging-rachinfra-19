# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo import tools


class MailMail(models.Model):
    _inherit = 'mail.mail'

    email_bcc = fields.Char(
        string='BCC',
        help='Blind Carbon Copy: Hidden recipients who will receive a copy of the email'
    )

    def _prepare_outgoing_list(self, mail_server=False, doc_to_followers=None):
        """Ensure BCC recipients are preserved in outgoing emails"""
        email_list = super()._prepare_outgoing_list(
            mail_server=mail_server,
            doc_to_followers=doc_to_followers,
        )

        email_bcc_formatted = tools.mail.email_split_and_format_normalize(self.email_bcc) if self.email_bcc else []
        email_bcc_normalized = tools.mail.email_normalize_all(self.email_bcc) if self.email_bcc else []

        for email_dict in email_list:
            headers = dict(email_dict.get('headers') or {})
            if email_bcc_formatted:
                headers['Bcc'] = ', '.join(email_bcc_formatted)
                normalized = list(dict.fromkeys((email_dict.get('email_to_normalized') or []) + email_bcc_normalized))
                email_dict['email_to_normalized'] = normalized
                email_dict['email_bcc'] = email_bcc_formatted
            else:
                headers.pop('Bcc', None)
                email_dict['email_bcc'] = []
            email_dict['headers'] = headers

        return email_list
