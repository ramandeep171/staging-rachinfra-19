from odoo import api, fields, models
import logging
logger = logging.getLogger(__name__)


class ExportTemplateWizard(models.TransientModel):
    _name = 'export.template.wizard'
    _description = "Export Template Message"

    message = fields.Text(string="Response", readonly=True)
    source = fields.Selection([('instance', 'Settings'), ('template', 'Template')])
    whatsapp_instance_id = fields.Many2one('whatsapp.instance', string='Whatsapp Instance')

    @api.model
    def default_get(self, fields):
        res = super(ExportTemplateWizard, self).default_get(fields)
        res.update({
            'message': 'Make sure you have set the correct signature in WhatsApp -> Select Instance -> Signature. As once WhatsApp template is exported, WhatsApp template signature cannot change',
        })
        record = self.env[self.env.context.get('active_model','')].browse(self.env.context.get('active_id',''))
        if self.env.context.get('active_model','') == 'whatsapp.templates':
            res.update({'source': 'template', 'whatsapp_instance_id': record.whatsapp_instance_id.id})
        else:
            res.update({'source': 'instance', 'whatsapp_instance_id': record.id})
        return res

    def action_export_templates_from_wizard(self):
        if self.source == 'instance':
            active_model = self.env.context.get('active_model')
            res_id = self.env.context.get('active_id')
            record = self.env[active_model].browse(res_id)
            whatsapp_template_ids = self.env['whatsapp.templates'].search(
                [('whatsapp_instance_id', '=', record.id), ('approval_state', 'not in', ['approved', 'APPROVED', 'submitted', 'rejected'])])
            for whatsapp_template_id in whatsapp_template_ids:
                try:
                    if whatsapp_template_id.send_template:
                        signature = ''
                        if whatsapp_template_id.whatsapp_instance_id.signature:
                            signature = whatsapp_template_id.whatsapp_instance_id.signature
                        else:
                            signature = self.env.user.company_id.name
                        whatsapp_template_id.footer = signature
                    self.whatsapp_instance_id.confirm_export_template(whatsapp_template_id)
                except Exception as exception:
                    logger.exception("Error in creating 1msg template------------>\n" + str(exception))

        elif self.source == 'template':
            record_whatsapp_template_id = self.env[self.env.context.get('active_model')].browse(self.env.context.get('active_id'))
            signature = ''
            if record_whatsapp_template_id.whatsapp_instance_id.signature:
                signature = record_whatsapp_template_id.whatsapp_instance_id.signature
            else:
                signature = self.env.user.company_id.name
            record_whatsapp_template_id.footer = signature
            record_whatsapp_template_id.whatsapp_instance_id.confirm_export_template(record_whatsapp_template_id)
        return True