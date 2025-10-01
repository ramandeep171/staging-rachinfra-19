from odoo import models, fields, api, _
from odoo import tools


class KsMailComposeMessageInherit(models.TransientModel):
    _inherit = "mail.compose.message"
    ks_cc_partner_ids = fields.Many2many('res.partner', 'mail_compose_message_cc_partner_res_partner_rel')
    ks_bcc_partner_ids = fields.Many2many('res.partner', 'mail_compose_message_bcc_partner_res_partner_rel')
    email_to = fields.Char('To')
    ks_email_char_cc = fields.Char('Email Cc', default=lambda self: self.env.user.company_id.ks_default_cc if (self.env.user.company_id.ks_display_email_cc and not self.is_log) else False)
    ks_email_char_bcc = fields.Char('Email Bcc', default=lambda self: self.env.user.company_id.ks_default_bcc if (self.env.user.company_id.ks_display_email_bcc and not self.is_log) else False)
    reply_to = fields.Char('Reply-To',
                           help='Reply email address. Setting the reply_to bypasses the automatic thread creation.', default=lambda self: self.env.user.company_id.ks_default_reply_to if (self.env.user.company_id.ks_display_reply_to and not self.is_log) else False)
    ks_cc_partner_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_display_recipients_cc)
    ks_bcc_partner_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_display_recipients_bcc)
    ks_email_char_cc_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_display_email_cc)
    ks_email_char_bcc_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_display_email_bcc)
    ks_reply_to_bcc_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_display_reply_to)
    ks_email_to_visibility = fields.Boolean(compute='compute_fields_visibility', default=lambda self: self.env.user.company_id.ks_email_to)

    def compute_fields_visibility(self):
        for rec in self:
            rec.ks_email_char_cc_visibility = True if self.env.user.company_id.ks_display_email_cc else False
            rec.ks_email_char_bcc_visibility = True if self.env.user.company_id.ks_display_email_bcc else False
            rec.ks_reply_to_bcc_visibility = True if self.env.user.company_id.ks_display_reply_to else False
            rec.ks_cc_partner_visibility = True if self.env.user.company_id.ks_display_recipients_cc else False
            rec.ks_bcc_partner_visibility = True if self.env.user.company_id.ks_display_recipients_bcc else False
            rec.ks_email_to_visibility = True if self.env.user.company_id.ks_email_to else False

    def get_mail_values(self, res_ids):
        res = super(KsMailComposeMessageInherit, self).get_mail_values(res_ids)
        if self.is_log:
            return res

        for r in res.keys():
            rec = self.filtered(lambda x: x.res_id == r)
            ks_email_char_cc = ','.join(tools.formataddr((x.name or 'False', x.email or 'False')) for x in rec.ks_cc_partner_ids)
            ks_email_char_bcc = ','.join(tools.formataddr((x.name or 'False', x.email or 'False')) for x in rec.ks_bcc_partner_ids)
            if rec.ks_email_char_cc:
                if ks_email_char_cc:
                    ks_email_char_cc = ks_email_char_cc + ',' + ','.join(rec.ks_email_char_cc.split(','))
                else:
                    ks_email_char_cc = ','.join(rec.ks_email_char_cc.split(','))
            if rec.ks_email_char_bcc:
                if ks_email_char_bcc:
                    ks_email_char_bcc = ks_email_char_bcc + ','.join(rec.ks_email_char_bcc.split(','))
                else:
                    ks_email_char_bcc = ','.join(rec.ks_email_char_bcc.split(','))
            if rec:
                res[r].update({'email_cc': ks_email_char_cc,
                               'email_bcc': ks_email_char_bcc,
                               'email_to': rec.email_to,
                               'ks_email_cc_string': rec.ks_email_char_cc,
                               'ks_email_bcc_string': rec.ks_email_char_bcc,
                               'ks_cc_partner_ids': [(4, x.id) for x in rec.ks_cc_partner_ids] if rec.ks_cc_partner_ids else False,
                               'ks_bcc_partner_ids': [(4, x.id) for x in rec.ks_bcc_partner_ids] if rec.ks_bcc_partner_ids else False,
                               })
                mass_mail_mode = self.composition_mode == 'mass_mail'
                if not mass_mail_mode and self.env.user.company_id.ks_display_reply_to:
                    res[r].update({'reply_to': self.reply_to})
        return res