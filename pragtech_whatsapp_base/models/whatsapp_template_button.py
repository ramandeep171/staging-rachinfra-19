from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from werkzeug.urls import url_join
import re

# Template Call-To-Action Buttons
class WhatsAppTemplateButton(models.Model):
    _name = 'whatsapp.templates.button'
    _description = 'WhatsApp Template Buttons'

    template_id = fields.Many2one('whatsapp.templates', string="WhatsApp Template", required=True, ondelete="cascade")
    type = fields.Selection([
        ('visit_website', 'Visit Website'),
        ('call_phone', 'Call Phone Number'),
        ('copy_offer_code', 'Copy Offer Code'),
    ], string='Button Type', required=True)
    url_type = fields.Selection([
        ('static', 'Static'),
        ('dynamic', 'Dynamic')
    ], string="URL Type")
    text = fields.Char(string="Button Text", required=True)
    url = fields.Char(string="Website URL")  # For visit_website
    phone_number = fields.Char(string="Phone Number")  # For call_phone
    offer_code = fields.Char(string="Offer Code")  # For copy_offer_code
