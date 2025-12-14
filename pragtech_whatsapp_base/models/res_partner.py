from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    chatId = fields.Char(string='Whatsapp Chat ID')
    whatsapp_message_ids = fields.One2many('whatsapp.messages', 'partner_id', string='Whatsapp Messages')
