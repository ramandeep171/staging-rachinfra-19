from odoo import _, api, models,fields


class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    ks_display_email_cc = fields.Boolean('Display Cc(Emails)')
    ks_display_email_bcc = fields.Boolean('Display Bcc(Emails)')
    ks_display_reply_to = fields.Boolean('Display Reply To')
    ks_email_to = fields.Boolean('Email To')
    ks_display_recipients_cc = fields.Boolean('Display Recipients Cc (Partners)')
    ks_display_recipients_bcc = fields.Boolean('Display Recipients Bcc (Partners)')
    ks_default_cc = fields.Char('Default Cc (Emails)', help='Comma(,) seperated emails')
    ks_default_bcc = fields.Char('Default Bcc (Emails)', help='Comma(,) seperated emails')
    ks_default_reply_to = fields.Char('Default Reply To(Emails)')