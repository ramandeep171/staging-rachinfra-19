import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class WhatsappGupshupTemplates(models.TransientModel):
    _name = 'whatsapp.gupshup.templates'
    _description = 'Whatsapp Gupshup View Template Wizard'

    def _get_default_language(self):
        language_id = self.env['res.lang'].search([('code', '=', 'en_US')])
        return language_id.id

    template_labels = fields.Char(string='Template Labels')
    template_category = fields.Char(string='Template Category')
    template_type = fields.Selection(
        [('text', 'TEXT'), ('media_image', 'MEDIA: IMAGE'), ('media_document', 'MEDIA: DOCUMENT'), ('media_video', 'MEDIA : VIDEO'), ('location', 'LOCATION')],
        default="text", string='Template Type')
    languages = fields.Char(string='Template Language', default=_get_default_language)
    element_name = fields.Char(string='Element name')
    template_format = fields.Text(string='Template Format')
    add_sample_media_message = fields.Text(string="Add Sample Media")
    sample_url = fields.Char(string='Sample URL')
    sample_message = fields.Text(string='Sample message')
    interactive_actions = fields.Selection([('none', 'None'), ('call_to_action', 'Call To Action'), ('quick_replies', 'Quick Replies')], default='none',
                                           string='Add interactive actions')
    quick_reply1 = fields.Char(string='Quick Reply1')

