from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    whatsapp_instance_id = fields.Many2one('whatsapp.instance', string='Whatsapp instance', help="From this instance message is sent on whatsapp")
    welcome_template_name = fields.Char(string="Welcome Template name")
