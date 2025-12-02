# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WebsiteVisitor(models.Model):
    _inherit = 'website.visitor'

    @api.model
    def create_lead_from_page_visit(self, visitor, team_id, page_url):
        """Create a CRM lead from website visitor"""
        if not visitor:
            return False
            
        Lead = self.env['crm.lead']
        
        # Check if lead already exists for this visitor and team
        existing_lead = Lead.search([
            ('visitor_ids', 'in', visitor.id),
            ('team_id', '=', team_id)
        ], limit=1)
        
        if existing_lead:
            return existing_lead
        
        # Determine lead name based on page
        if 'batching-plant' in page_url:
            lead_name = f"Batching Plant Inquiry - {visitor.name or 'Website Visitor'}"
            description = "Visitor showed interest in Batching Plant rental services"
        else:
            lead_name = f"Rental Inquiry - {visitor.name or 'Website Visitor'}"
            description = "Visitor showed interest in Gear rental services"
        
        # Create lead
        lead_vals = {
            'name': lead_name,
            'team_id': team_id,
            'type': 'lead',
            'visitor_ids': [(4, visitor.id)],
            'description': description,
            'referred': page_url,
        }
        
        # Add contact info if available
        if visitor.partner_id:
            lead_vals.update({
                'partner_id': visitor.partner_id.id,
                'contact_name': visitor.partner_id.name,
                'email_from': visitor.partner_id.email,
                'phone': visitor.partner_id.phone,
                'mobile': visitor.partner_id.mobile,
            })
        elif hasattr(visitor, 'email') and visitor.email:
            lead_vals['email_from'] = visitor.email
        
        lead = Lead.create(lead_vals)
        return lead
