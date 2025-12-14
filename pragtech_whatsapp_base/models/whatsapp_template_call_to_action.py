from odoo import fields, models, _


class WhatsappTemplateCallToAction(models.Model):
    _name = 'whatsapp.template.call.to.action'
    _description = 'Whatsapp Template Call To Action'

    call_action = fields.Selection([('url', 'URL'), ('phone', 'Phone')], string='Call action')
    whatsapp_template_id = fields.Many2one('whatsapp.templates', string='Whatsapp Template')
    button_name = fields.Char(string='Button Name')
    phone = fields.Char(string='Phone')
    url = fields.Char(string='URL')
    url_type = fields.Selection([('static', 'Static'), ('dynamic', 'Dynamic')], default='static', string='URL Type')

