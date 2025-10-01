from odoo import _, api, exceptions, fields, models, tools, SUPERUSER_ID
import threading


class MailThreadInherit(models.AbstractModel):
    _inherit = 'mail.thread'
    # Removed custom _notify_thread override that relied on deprecated _notify_compute_recipients.
    # Core behavior is used. If future filtering of recipients is required, it should
    # be done by adjusting message_post kwargs or context before calling message_post.

    # Removed custom _message_add_suggested_recipient override.
    # Base method is sufficient. Follower partners are injected via override in mail_thread.py.

    def _notify_record_by_email(self, message, recipients_data, msg_vals=False,
                                model_description=False, mail_auto_delete=True, check_existing=False,
                                force_send=True, send_after_commit=True,
                                **kwargs):
        """Simplified copy of base version with added cc/bcc + email_to merging.
        Maintains original behavior while remaining shorter and correctly indented.
        """
        partners_data = [r for r in recipients_data['partners'] if r['notif'] == 'email']
        if not partners_data:
            return True

        model = msg_vals.get('model') if msg_vals else message.model
        model_name = model_description or (self._fallback_lang().env['ir.model']._get(model).display_name if model else False)
        recipients_groups_data = self._notify_classify_recipients(partners_data, model_name, msg_vals=msg_vals)
        if not recipients_groups_data:
            return True
        force_send = self.env.context.get('mail_notify_force_send', force_send)

        template_values = self._notify_prepare_template_context(message, msg_vals, model_description=model_description)
        email_layout_xmlid = msg_vals.get('email_layout_xmlid') if msg_vals else message.email_layout_xmlid
        template_xmlid = email_layout_xmlid if email_layout_xmlid else 'mail.message_notification_email'
        try:
            base_template = self.env.ref(template_xmlid, raise_if_not_found=True).with_context(lang=template_values['lang'])
        except ValueError:
            base_template = False

        mail_subject = message.subject or (message.record_name and 'Re: %s' % message.record_name)
        base_mail_values = {
            'mail_message_id': message.id,
            'mail_server_id': message.mail_server_id.id,
            'auto_delete': mail_auto_delete,
            'references': message.parent_id.sudo().message_id if message.parent_id else False,
            'subject': mail_subject,
        }
        base_mail_values = self._notify_by_email_add_values(base_mail_values)

        ctx = {k: v for k, v in self._context.items() if not k.startswith('default_')}
        SafeMail = self.env['mail.mail'].sudo().with_context(ctx)
        SafeNotification = self.env['mail.notification'].sudo().with_context(ctx)
        emails = self.env['mail.mail'].sudo()

        notif_create_values = []
        recipients_max = 50
        for recipients_group_data in recipients_groups_data:
            recipients_ids = recipients_group_data.pop('recipients')
            # base template values + current group specific values
            render_values = dict(template_values)
            render_values.update(recipients_group_data)
            mail_body = base_template._render(render_values, engine='ir.qweb', minimal_qcontext=True) if base_template else message.body
            mail_body = self.env['mail.render.mixin']._replace_local_links(mail_body)
            for i in range(0, len(recipients_ids), recipients_max):
                recipients_ids_chunk = recipients_ids[i:i+recipients_max]
                recipient_values = self._notify_email_recipient_values(recipients_ids_chunk)
                email_to = recipient_values['email_to']
                recipient_ids = recipient_values['recipient_ids']
                create_values = {
                    'body_html': mail_body,
                    'subject': mail_subject,
                    'recipient_ids': [(4, pid) for pid in recipient_ids],
                }
                if msg_vals and msg_vals.get('email_cc'):
                    create_values['email_cc'] = msg_vals.get('email_cc')
                if msg_vals and msg_vals.get('email_bcc'):
                    create_values['email_bcc'] = msg_vals.get('email_bcc')
                if email_to or (msg_vals and msg_vals.get('email_to')):
                    combined = ''
                    if email_to:
                        combined = email_to + ','
                    combined += (msg_vals.get('email_to') if msg_vals else '')
                    if combined:
                        create_values['email_to'] = combined.rstrip(',')
                create_values.update(base_mail_values)
                email_rec = SafeMail.create(create_values)
                if email_rec and recipient_ids:
                    tocreate = list(recipient_ids)
                    if check_existing:
                        existing = self.env['mail.notification'].sudo().search([
                            ('mail_message_id', '=', message.id),
                            ('notification_type', '=', 'email'),
                            ('res_partner_id', 'in', tocreate)
                        ])
                        if existing:
                            tocreate = [rid for rid in recipient_ids if rid not in existing.mapped('res_partner_id.id')]
                            existing.write({'notification_status': 'ready', 'mail_id': email_rec.id})
                    notif_create_values += [{
                        'mail_message_id': message.id,
                        'res_partner_id': rid,
                        'notification_type': 'email',
                        'mail_id': email_rec.id,
                        'is_read': True,
                        'notification_status': 'ready',
                    } for rid in tocreate]
                emails |= email_rec

        if notif_create_values:
            SafeNotification.create(notif_create_values)

        test_mode = getattr(threading.currentThread(), 'testing', False)
        if force_send and len(emails) < recipients_max and (not self.pool._init or test_mode):
            if not test_mode and send_after_commit:
                email_ids = emails.ids
                dbname = self.env.cr.dbname
                _context = self._context
                @self.env.cr.postcommit.add
                def send_notifications():
                    db_registry = self.env.registry
                    with api.Environment.manage(), db_registry.cursor() as cr:
                        env = api.Environment(cr, SUPERUSER_ID, _context)
                        env['mail.mail'].browse(email_ids).send()
            else:
                emails.send()
        return True


class MailMessageInherit(models.Model):
    _inherit = "mail.message"
    email_cc = fields.Char('Email CC')
    email_bcc = fields.Char('Email BCC')
    email_to = fields.Char('To')
    ks_email_cc_string = fields.Char('Cc String', help='Used to store only cc mails that can be shown in chatter')
    ks_email_bcc_string = fields.Char('Bcc String', help='Used to store only bcc mails that can be shown in chatter')
    ks_cc_partners = fields.Char('cc partners string')
    ks_bcc_partners = fields.Char('bcc partners string')
    ks_cc_partner_ids = fields.Many2many('res.partner', 'mail_message_cc_partner_res_partner_rel')
    ks_bcc_partner_ids = fields.Many2many('res.partner', 'mail_message_bcc_partner_res_partner_rel')

    @api.constrains('ks_cc_partner_ids')
    def update_cc_partners_field(self):
        for rec in self:
            if rec.ks_cc_partner_ids:
                rec.ks_cc_partners = ','.join([x.name for x in rec.ks_cc_partner_ids])

    @api.constrains('ks_bcc_partner_ids')
    def update_bcc_partners_field(self):
        for rec in self:
            if rec.ks_bcc_partner_ids:
                rec.ks_bcc_partners = ','.join([x.name for x in rec.ks_bcc_partner_ids])

    def _get_message_format_fields(self):
        return [
            'id', 'body', 'date', 'author_id', 'email_from',  # base message fields
            'message_type', 'subtype_id', 'subject',  # message specific
            'model', 'res_id', 'record_name',  # document related
            'channel_ids', 'partner_ids',  # recipients
            'starred_partner_ids',  # list of partner ids for whom the message is starred
            'moderation_status', 'ks_email_cc_string','ks_email_bcc_string', 'ks_bcc_partners','ks_cc_partners'
        ]
