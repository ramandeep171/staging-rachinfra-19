from odoo import api, fields, models, _


class Users(models.Model):
    _inherit = "res.users"

    whatsapp_instance_id = fields.Many2one('whatsapp.instance', string='Whatsapp instance', help="From this instance message is sent on whatsapp")
