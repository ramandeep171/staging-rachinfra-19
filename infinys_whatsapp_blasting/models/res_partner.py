import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    infinys_whatsapp_contact_ids = fields.One2many(
        'infinys.whatsapp.contact',
        'partner_id',
        string='WhatsApp Contacts',
        help='Technical link used to mirror Contacts records into the WhatsApp recipient list.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners.with_context(skip_partner_sync=True)._ensure_infinys_whatsapp_contact()
        return partners

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_partner_sync'):
            self._ensure_infinys_whatsapp_contact()
        return res

    def _ensure_infinys_whatsapp_contact(self):
        """Guarantee that every partner has a mirrored WhatsApp contact."""
        Contact = self.env['infinys.whatsapp.contact']
        for partner in self.with_context(active_test=False):
            if partner.infinys_whatsapp_contact_ids:
                continue
            Contact.with_context(skip_partner_creation=True).create({
                'partner_id': partner.id,
                'is_manual': False,
                'is_active': partner.active,
            })
        return True

    def init(self):
        """Backfill WhatsApp contacts for existing partners when updating the module."""
        Contact = self.env['infinys.whatsapp.contact'].with_context(skip_partner_creation=True, active_test=False)
        self.env.cr.execute("""
            SELECT p.id
            FROM res_partner p
            LEFT JOIN infinys_whatsapp_contact c ON c.partner_id = p.id
            WHERE c.id IS NULL
        """)
        missing_ids = [row[0] for row in self.env.cr.fetchall()]
        if not missing_ids:
            return
        _logger.info("Creating mirrored WhatsApp contacts for %s partners", len(missing_ids))
        for chunk_index in range(0, len(missing_ids), 1000):
            batch = missing_ids[chunk_index:chunk_index + 1000]
            Contact.create([{
                'partner_id': partner_id,
                'is_manual': False,
            } for partner_id in batch])
