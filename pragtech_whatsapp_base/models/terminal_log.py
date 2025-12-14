from odoo import fields, models, _
from datetime import timedelta


class TerminalLog(models.Model):
    _name = 'terminal.log'
    _description = 'Terminal Log'
    _order = 'timestamp desc, id desc'

    timestamp = fields.Datetime(string='Timestamp')
    log_message = fields.Text(string='Message')
    terminal_log_id = fields.Many2one('whatsapp.instance')

    def log_info(self, log_message):
        whatsapp_instance_id = self.env['whatsapp.instance'].get_whatsapp_instance()
        self.create({
             'timestamp': fields.Datetime.now(),
             'log_message': log_message,
             'terminal_log_id': whatsapp_instance_id.id,
        })

    def _auto_delete_records(self):
        two_days_ago = fields.Datetime.now() - timedelta(days=2)
        records_to_delete = self.search([('timestamp', '<', two_days_ago)])
        records_to_delete.unlink()