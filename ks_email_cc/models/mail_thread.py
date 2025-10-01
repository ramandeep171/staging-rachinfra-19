# -*- coding: utf-8 -*-
"""Extend mail.thread suggested recipients for Odoo 19.
We add all follower partners as selectable recipients in the composer.
"""
from odoo import models, _

class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_get_suggested_recipients(self, reply_discussion=False, reply_message=None,
                                            no_create=True, primary_email=False, additional_partners=None):
        """Extend suggestions by adding follower partners (reason 'Customer').

        Odoo 19 core seems to have changed return type to a list in some contexts.
        We therefore only inject extra recipients when the legacy dict structure
        is returned to avoid breaking the core discuss store process.
        """
        suggestions = super()._message_get_suggested_recipients(
            reply_discussion=reply_discussion, reply_message=reply_message,
            no_create=no_create, primary_email=primary_email, additional_partners=additional_partners
        )

        # If core returns a list (new API), don't try to mutate assuming dict structure.
        if isinstance(suggestions, list):
            return suggestions

        # Expected legacy structure: {res_id: {'partners': set(), 'emails': set(), ...}}
        if isinstance(suggestions, dict):
            for record in self:
                rec_sugg = suggestions.get(record.id)
                if not rec_sugg:
                    continue
                # core stores partners in a set under key 'partners'
                partners_set = rec_sugg.get('partners') if isinstance(rec_sugg, dict) else None
                if partners_set is None:
                    continue
                for partner in record.message_follower_ids.partner_id:
                    # add partner only if he has an email to avoid noise
                    if partner.email:
                        partners_set.add((partner.id, partner.email_formatted, _('Customer')))
        return suggestions
