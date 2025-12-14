import logging
from odoo import fields, models,api
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class WhatsappMessages(models.Model):
    _name = 'whatsapp.messages'
    _description = "Whatsapp Messages"
    _order = 'time desc'

    name = fields.Char('Name', readonly=True, help='Whatsapp message')
    message_body = fields.Text('Message', readonly=True, help='If whatsapp message have caption (for image,video,document) else add message body')
    message_id = fields.Text('Message Id', readonly=True, help='Whatsapp Message id')
    fromMe = fields.Boolean('Form Me', readonly=True, help="If message is sent then from me true else false")
    to = fields.Char('To', readonly=True, help='If message is sending from current instance then to contains To Me else add sender number')
    chatId = fields.Char('Chat ID', readonly=True, help="It contains number & @.us")
    type = fields.Char('Type', readonly=True, help='Type of message is text,image,document,etc.')
    msg_image = fields.Binary('Image', readonly=True, help="If type of message is image then add message")
    senderName = fields.Char('Sender Name', readonly=True, help='If message is coming then it contains name sender '
                                                                'else if message is sending from odoo then name/mobile of sender which has current instance attached')
    chatName = fields.Char('Chat Name', readonly=True, help='Mobile number with country on which message is sending/receiving')
    author = fields.Char('Author', readonly=True, help='From which number message is sending or receiving same as chatId')
    time = fields.Datetime('Date and time', readonly=True, help='Time on which message is sent or receive')
    partner_id = fields.Many2one('res.partner', 'Partner', readonly=True, help= "If message is sending or receiving from partner then added partner id")
    state = fields.Selection([('sent', 'Sent'), ('received', 'Received')], readonly=True, help="It is based on message is sent or receive")
    attachment_id = fields.Many2one('ir.attachment', 'Attachment ', readonly=True, help="If message have an attachment then add attachment")
    attachment_data = fields.Binary(related='attachment_id.datas', string='Attachment', help="Download attachment")
    whatsapp_instance_id = fields.Many2one('whatsapp.instance', string='Whatsapp Instance', ondelete='restrict', help= 'Whatsapp Instance on which message is sent or received')
    whatsapp_message_provider = fields.Selection([('whatsapp_chat_api', '1msg'), ('meta', 'Meta')], string="Whatsapp Service Provider",
                                                 default='whatsapp_chat_api', help='Whatsapp provider on which message is sent or received')
    model = fields.Char('Related Document Model', index=True)
    res_id = fields.Integer('Related Document ID', index=True, model_field='model')
    # res_id = fields.Many2oneReference('Related Document ID', index=True, model_field='model')

    