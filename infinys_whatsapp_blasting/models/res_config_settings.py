from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whatsapp_api_url = fields.Char(config_parameter='infinys_whatsapp_blasting.whatsapp_api_url', string='WhatsApp API URL')
    token = fields.Char(config_parameter='infinys_whatsapp_blasting.token', string='Access Token / Session Key')
    authentication_user = fields.Char(config_parameter='infinys_whatsapp_blasting.authentication_user', string='Auth User / App ID')
    authentication_password = fields.Char(config_parameter='infinys_whatsapp_blasting.authentication_password', string='Auth Password / App Secret')
    whatsapp_number = fields.Char(config_parameter='infinys_whatsapp_blasting.whatsapp_number', string='Phone Number ID')
    webhook_url = fields.Char(config_parameter='infinys_whatsapp_blasting.webhook_url', string='Webhook URL (N8n)')
    provider = fields.Selection(
        [('waha', 'WAHA (WhatsApp API by Infinys)'), ('meta', 'Meta Cloud API (Facebook)')],
        config_parameter='infinys_whatsapp_blasting.provider',
        string='Provider',
        default='waha',
    )
    active = fields.Boolean(config_parameter='infinys_whatsapp_blasting.active', string='Active')

    def _get_config_record(self):
        config = self.env['infinys.whatsapp.config'].search([], limit=1)
        if not config:
            config = self.env['infinys.whatsapp.config'].create({
                'name': 'Default Configuration',
                'provider': self.provider or 'waha',
                'whatsapp_number': self.whatsapp_number or '',
                'token': self.token or '',
                'webhook_url': self.webhook_url or '',
                'authentication_user': self.authentication_user or '',
                'authentication_password': self.authentication_password or '',
                'whatsapp_api_url': self.whatsapp_api_url or '',
                'active': self.active,
            })
        return config

    def set_values(self):
        super().set_values()
        for settings in self:
            config = settings._get_config_record()
            config_vals = {
                'provider': settings.provider,
                'whatsapp_number': settings.whatsapp_number,
                'token': settings.token,
                'webhook_url': settings.webhook_url,
                'authentication_user': settings.authentication_user,
                'authentication_password': settings.authentication_password,
                'whatsapp_api_url': settings.whatsapp_api_url,
                'active': settings.active,
            }
            config.write({k: v for k, v in config_vals.items() if v is not None})

    @api.model
    def get_values(self):
        res = super().get_values()
        config = self.env['infinys.whatsapp.config'].search([], limit=1)
        if config:
            res.update({
                'provider': config.provider,
                'whatsapp_number': config.whatsapp_number,
                'token': config.token,
                'webhook_url': config.webhook_url,
                'authentication_user': config.authentication_user,
                'authentication_password': config.authentication_password,
                'whatsapp_api_url': config.whatsapp_api_url,
                'active': config.active,
            })
        return res
