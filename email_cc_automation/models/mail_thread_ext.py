from odoo import api, models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def _get_notify_valid_parameters(self):
        params = super()._get_notify_valid_parameters()
        params.update({'email_cc', 'email_bcc'})
        return params

    def _notify_thread_by_email(
        self,
        message,
        recipients_data,
        *,
        msg_vals=False,
        mail_auto_delete=True,
        model_description=False,
        force_email_company=False,
        force_email_lang=False,
        force_record_name=False,
        subtitles=None,
        resend_existing=False,
        force_send=True,
        send_after_commit=True,
        **kwargs,
    ):
        email_cc = kwargs.get('email_cc')
        email_bcc = kwargs.get('email_bcc')
        result = super()._notify_thread_by_email(
            message,
            recipients_data,
            msg_vals=msg_vals,
            mail_auto_delete=mail_auto_delete,
            model_description=model_description,
            force_email_company=force_email_company,
            force_email_lang=force_email_lang,
            force_record_name=force_record_name,
            subtitles=subtitles,
            resend_existing=resend_existing,
            force_send=force_send,
            send_after_commit=send_after_commit,
            **kwargs,
        )
        if not (message and (email_cc or email_bcc)):
            return result

        mails = message.mail_ids

        if email_cc:
            mails.filtered(lambda mail: not mail.email_cc).write({'email_cc': email_cc})
        if email_bcc:
            mails.filtered(lambda mail: not mail.email_bcc).write({'email_bcc': email_bcc})

        return result
