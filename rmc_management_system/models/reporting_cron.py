from odoo import models, fields, api, _
from datetime import timedelta


class RmcReportingCron(models.AbstractModel):
    _name = 'rmc.reporting.cron'
    _description = 'RMC Reporting Cron Helpers'

    @api.model
    def run_cube_followups(self):
        # Find completed workorders and check due dates
        today = fields.Datetime.now()
        wo_model = self.env['dropshipping.workorder']
        # 7-day due
        due7 = wo_model.search([
            ('state', '=', 'completed'),
            ('date_completed', '!=', False),
        ])
        for wo in due7:
            try:
                # Send 7-day if exactly or past 7 days and not sent before today
                if wo.date_completed and (today - wo.date_completed) >= timedelta(days=7):
                    if not wo.cube7_last_sent or wo.cube7_last_sent.date() < fields.Date.context_today(self):
                        wo._send_cube_followup('7')
                if wo.date_completed and (today - wo.date_completed) >= timedelta(days=28):
                    if not wo.cube28_last_sent or wo.cube28_last_sent.date() < fields.Date.context_today(self):
                        wo._send_cube_followup('28')
            except Exception as e:
                wo.message_post(body=_('Cube follow-up cron error: %s') % (e,))

    @api.model
    def run_sale_order_periodic(self):
        so_model = self.env['sale.order']
        today = fields.Datetime.now()
        for so in so_model.search([('state', 'in', ['sale','done']), ('reporting_enabled', '=', True)]):
            try:
                # Only one send per SO per day
                sent_today = any([
                    so.last_sent_30d and so.last_sent_30d.date() == fields.Date.context_today(self),
                    so.last_sent_7d and so.last_sent_7d.date() == fields.Date.context_today(self),
                    so.last_sent_15d and so.last_sent_15d.date() == fields.Date.context_today(self),
                ])
                if sent_today:
                    continue
                # 30-day cadence based on confirmation_date or date_order
                conf_dt = getattr(so, 'confirmation_date', False) or so.date_order
                if conf_dt and (today - conf_dt) >= timedelta(days=30):
                    # Send every 30 days from conf date; simple modulo check by days since
                    days_since = (today - conf_dt).days
                    if days_since % 30 == 0:
                        if so._send_sale_order_summary(30, 'rmc_management_system.mail_tmpl_so_summary_30'):
                            continue
                # Periodic 7/15
                period = int(so.reporting_period or 7)
                if conf_dt and (today - conf_dt) >= timedelta(days=period):
                    days_since = (today - conf_dt).days
                    if days_since % period == 0:
                        tmpl = 'rmc_management_system.mail_tmpl_so_summary_7' if period == 7 else 'rmc_management_system.mail_tmpl_so_summary_15'
                        so._send_sale_order_summary(period, tmpl)
            except Exception as e:
                so.message_post(body=_('SO periodic reporting cron error: %s') % (e,))
