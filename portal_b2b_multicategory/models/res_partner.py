# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_portal_categories = fields.Many2many(
        'product.category',
        'res_partner_portal_category_rel',
        'partner_id',
        'category_id',
        string='Portal Product Categories',
        help='Product categories inferred from confirmed sale orders. Used to tailor the portal dashboard.',
    )
    x_portal_role = fields.Selection(
        selection=[
            ('team_leader', 'Team Leader'),
            ('quality', 'Quality'),
            ('logistics', 'Logistics'),
            ('finance', 'Finance'),
        ],
        string='Portal Role',
        help='Determines which portal sections the contact can access.',
        default='team_leader',
    )

    def _portal_related_partners(self):
        """Return self, the commercial partner, and all child contacts.

        Updating the categories on the full set ensures that each
        contact inheriting access from the commercial partner stays in sync.
        """
        self.ensure_one()
        partners = self
        if self.commercial_partner_id and self.commercial_partner_id != self:
            partners |= self.commercial_partner_id
        partners |= partners.mapped('child_ids')
        return partners

    def add_portal_categories(self, categories):
        """Convenience helper to append new categories to the partner selection."""
        if not categories:
            return
        categories = categories.filtered(lambda c: c)
        if not categories:
            return
        for partner in self:
            target_partners = partner._portal_related_partners()
            for contact in target_partners:
                new_cats = categories - contact.x_portal_categories
                if new_cats:
                    contact.write({'x_portal_categories': [(4, cat.id) for cat in new_cats]})

    @api.model
    def update_partner_categories_from_products(self, partner, categories):
        """Utility for other models to sync partner categories."""
        if not partner or not categories:
            return
        partner.add_portal_categories(categories)

    def get_portal_dashboard_categories(self):
        """Fetch portal categories for use in controllers/templates."""
        self.ensure_one()
        return self.x_portal_categories.sorted('name')

    def get_portal_role_key(self):
        """Return the role to simplify template conditions. Defaults to team_leader."""
        self.ensure_one()
        return self.x_portal_role or 'team_leader'
