from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rmc_report_cc_emails = fields.Char(string='RMC Report CC Emails', config_parameter='rmc.report.cc_emails')
    rmc_report_bcc_emails = fields.Char(string='RMC Report BCC Emails', config_parameter='rmc.report.bcc_emails')
    rmc_completion_template_id = fields.Many2one('mail.template', string='WO Completion Template', config_parameter='rmc.template.wo_completion_id')
    rmc_cube7_template_id = fields.Many2one('mail.template', string='Cube 7-Day Template', config_parameter='rmc.template.cube7_id')
    rmc_cube28_template_id = fields.Many2one('mail.template', string='Cube 28-Day Template', config_parameter='rmc.template.cube28_id')
