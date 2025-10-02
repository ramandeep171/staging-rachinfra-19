from odoo import _, api, models
import logging
from odoo import tools
import ast

_logger = logging.getLogger(__name__)


class MailMailInherit(models.Model):
    _inherit = 'mail.mail'

    def _prepare_outgoing_list(self, mail_server=False, doc_to_followers=None):
        """Override to inject email_cc and email_bcc into outgoing email values."""
        results = super()._prepare_outgoing_list(
            mail_server=mail_server,
            doc_to_followers=doc_to_followers
        )

        for email_values in results:
            # Inject CC into headers if present
            if self.email_cc:
                cc_list = tools.mail.email_split_and_format_normalize(self.email_cc)
                if cc_list:
                    if not email_values.get('headers'):
                        email_values['headers'] = {}
                    email_values['headers']['Cc'] = ', '.join(cc_list)
            
            # Inject BCC into headers if present
            if self.email_bcc:
                bcc_list = tools.mail.email_split_and_format_normalize(self.email_bcc)
                if bcc_list:
                    if not email_values.get('headers'):
                        email_values['headers'] = {}
                    email_values['headers']['Bcc'] = ', '.join(bcc_list)

        return results

    def _send(self, auto_commit=False, raise_exception=False, smtp_session=None, alias_domain_id=False,
              mail_server=False, post_send_callback=None):
        """Override _send to ensure compatibility with Odoo 19 signature.
        
        This method accepts all parameters that Odoo 19's mail.mail._send() expects,
        including the new alias_domain_id parameter that was added in Odoo 19.
        """
        return super()._send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            smtp_session=smtp_session,
            alias_domain_id=alias_domain_id,
            mail_server=mail_server,
            post_send_callback=post_send_callback
        )