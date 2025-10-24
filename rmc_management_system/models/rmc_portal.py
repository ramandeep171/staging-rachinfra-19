import logging
from datetime import date, datetime, timedelta

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)

class RmcSubcontractorPlant(models.Model):
    _inherit = 'rmc.subcontractor.plant'

    operator_portal_email = fields.Char(string='Operator Portal Email')
    operator_portal_password = fields.Char(string='Operator Portal Password', password=True)
    operator_user_id = fields.Many2one('res.users', string='Operator Portal User', readonly=True)
    operator_portal_enabled = fields.Boolean(string='Operator Portal Enabled', default=False)
    operator_portal_last_login = fields.Datetime(related='operator_user_id.login_date', string='Last Operator Login', readonly=True)
    day_report_ids = fields.One2many('rmc.operator.day.report', 'plant_id', string='Day Reports')

    def action_sync_operator_portal_user(self):
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=True)
        operator_group = self.env.ref('rmc_management_system.group_rmc_operator_portal', raise_if_not_found=False)
        user_type_category = self.env.ref('base.module_category_user_type', raise_if_not_found=False)
        for plant in self:
            if not plant.operator_portal_email:
                raise ValidationError(_('Set an operator portal email before enabling access.'))

            groups_to_assign = portal_group | (operator_group or portal_group)
            if plant.operator_user_id:
                user = plant.operator_user_id.sudo()
                if user_type_category:
                    preserved_groups = user.group_ids.filtered(lambda g: g.category_id != user_type_category)
                else:
                    preserved_groups = self.env['res.groups']
                final_groups = preserved_groups | groups_to_assign
                user.write({
                    'name': '%s (%s)' % (plant.subcontractor_id.name or _('Operator'), plant.plant_code or plant.id),
                    'login': plant.operator_portal_email.strip(),
                    'email': plant.operator_portal_email.strip(),
                    'group_ids': [Command.set(final_groups.ids)],
                })
            else:
                user = self.env['res.users'].sudo().create({
                    'name': '%s (%s)' % (plant.subcontractor_id.name or _('Operator'), plant.plant_code or plant.id),
                    'login': plant.operator_portal_email.strip(),
                    'email': plant.operator_portal_email.strip(),
                    'group_ids': [Command.set(groups_to_assign.ids)],
                })

            if plant.operator_portal_password:
                user.with_context(no_reset_password=True).write({'password': plant.operator_portal_password})
                plant.operator_portal_password = False
            plant.operator_user_id = user.id
            plant.operator_portal_enabled = True
        return True

    def action_disable_operator_portal(self):
        for plant in self:
            if plant.operator_user_id:
                user = plant.operator_user_id.sudo()
                base_groups = self.env['res.groups']
                public_group = self.env.ref('base.group_public', raise_if_not_found=False)
                if public_group:
                    base_groups |= public_group
                user.write({'group_ids': [Command.set(base_groups.ids)]})
            plant.operator_portal_enabled = False
        return True


class RmcSubcontractorTransport(models.Model):
    _inherit = 'rmc.subcontractor.transport'

    operator_user_ids = fields.Many2many('res.users', string='Linked Operators', compute='_compute_operator_users', store=False)
    docket_ids = fields.One2many('rmc.docket', 'subcontractor_transport_id', string='Dockets')
    fuel_log_ids = fields.One2many('rmc.transport.fuel.log', 'transport_id', string='Fuel Logs')
    jobs_completed = fields.Integer(string='Jobs Completed', compute='_compute_driver_metrics')
    jobs_today = fields.Integer(string='Jobs Today', compute='_compute_driver_metrics')
    efficiency_score = fields.Float(string='Efficiency Score', compute='_compute_driver_metrics')
    fuel_consumed_litres = fields.Float(string='Fuel Used (L)', compute='_compute_driver_metrics')
    fuel_cost_total = fields.Float(string='Fuel Cost', compute='_compute_driver_metrics')
    document_ids = fields.One2many('rmc.transport.document', 'transport_id', string='Documents')
    documents_due_count = fields.Integer(string='Documents Due', compute='_compute_document_alerts')
    next_document_expiry = fields.Date(string='Next Expiry', compute='_compute_document_alerts')

    @api.depends('plant_id.operator_user_id')
    def _compute_operator_users(self):
        for transport in self:
            transport.operator_user_ids = transport.plant_id.operator_user_id

    @api.depends('docket_ids.state', 'docket_ids.docket_date', 'docket_ids.quantity_ordered', 'docket_ids.quantity_produced', 'fuel_log_ids.litre_count', 'fuel_log_ids.cost_amount')
    def _compute_driver_metrics(self):
        today = date.today()
        for transport in self:
            dockets = transport.docket_ids.filtered(lambda d: d.state in ('ready', 'dispatched', 'delivered'))
            completed = dockets.filtered(lambda d: d.state == 'delivered')
            transport.jobs_completed = len(completed)
            transport.jobs_today = len(dockets.filtered(lambda d: fields.Datetime.to_datetime(d.docket_date).date() == today if d.docket_date else False))
            ratios = []
            for docket in dockets:
                ordered = docket.quantity_ordered or 0
                produced = docket.quantity_produced or 0
                if ordered > 0 and produced >= 0:
                    ratios.append(min(produced / ordered, 2.0))
            transport.efficiency_score = sum(ratios) / len(ratios) if ratios else 0.0
            fuel_litre = sum(transport.fuel_log_ids.mapped('litre_count'))
            transport.fuel_consumed_litres = fuel_litre
            transport.fuel_cost_total = sum(transport.fuel_log_ids.mapped('cost_amount'))

    @api.depends('document_ids.expiry_date', 'document_ids.is_expired', 'document_ids.reminder_days')
    def _compute_document_alerts(self):
        for transport in self:
            due = 0
            next_expiry = False
            for doc in transport.document_ids:
                exp_date = fields.Date.to_date(doc.expiry_date) if doc.expiry_date else False
                if exp_date:
                    if not next_expiry or exp_date < next_expiry:
                        next_expiry = exp_date
                    if doc.is_expired or (doc.days_to_expiry is not False and doc.days_to_expiry <= doc.reminder_days):
                        due += 1
            transport.documents_due_count = due
            transport.next_document_expiry = next_expiry


class RmcTransportFuelLog(models.Model):
    _name = 'rmc.transport.fuel.log'
    _description = 'Transport Fuel Log'
    _order = 'log_date desc'

    transport_id = fields.Many2one('rmc.subcontractor.transport', string='Transport', required=True, ondelete='cascade')
    log_date = fields.Date(string='Date', default=fields.Date.context_today)
    litre_count = fields.Float(string='Litres', required=True)
    cost_amount = fields.Float(string='Cost')
    driver_id = fields.Many2one('res.partner', string='Driver')
    note = fields.Char(string='Note')


class RmcTransportDocument(models.Model):
    _name = 'rmc.transport.document'
    _description = 'Transport Document'
    _order = 'expiry_date asc'

    name = fields.Char(string='Document Name', required=True)
    transport_id = fields.Many2one('rmc.subcontractor.transport', string='Transport', required=True, ondelete='cascade')
    document_type = fields.Selection([
        ('insurance', 'Insurance'),
        ('fitness', 'Fitness Certificate'),
        ('permit', 'Permit'),
        ('pollution', 'Pollution Certificate'),
        ('other', 'Other'),
    ], string='Document Type', default='other')
    expiry_date = fields.Date(string='Expiry Date')
    reminder_days = fields.Integer(string='Reminder Days', default=7)
    days_to_expiry = fields.Integer(string='Days to Expiry', compute='_compute_expiry_meta', store=True)
    is_expired = fields.Boolean(string='Expired', compute='_compute_expiry_meta', store=True)
    attachment_id = fields.Binary(string='Attachment', attachment=True)
    attachment_filename = fields.Char(string='Filename')
    note = fields.Char(string='Remarks')
    last_reminder_date = fields.Date(string='Last Reminder Date')

    @api.depends('expiry_date')
    def _compute_expiry_meta(self):
        today = date.today()
        for doc in self:
            if doc.expiry_date:
                exp_date = fields.Date.to_date(doc.expiry_date)
                delta = (exp_date - today).days
                doc.days_to_expiry = delta
                doc.is_expired = delta < 0
            else:
                doc.days_to_expiry = False
                doc.is_expired = False

    @api.model
    def cron_notify_expiring_documents(self):
        today = fields.Date.context_today(self)
        today_date = fields.Date.to_date(today) if isinstance(today, str) else today
        docs = self.search([
            ('transport_id.subcontractor_id', '!=', False),
            ('expiry_date', '!=', False),
            ('reminder_days', '>=', 0),
        ])
        Mail = self.env['mail.mail'].sudo()
        sent_docs = self.env['rmc.transport.document']
        for doc in docs:
            partner = doc.transport_id.subcontractor_id.partner_id
            email_to = doc.transport_id.subcontractor_id.contact_email or partner.email
            if not email_to:
                continue
            if doc.last_reminder_date and fields.Date.to_date(doc.last_reminder_date) == today_date:
                continue
            due = doc.is_expired or (doc.days_to_expiry is not False and doc.days_to_expiry <= doc.reminder_days)
            if not due:
                continue
            body = _(
                'Document %(document)s for vehicle %(vehicle)s is due on %(date)s. Please renew it promptly.'
            ) % {
                'document': doc.name,
                'vehicle': doc.transport_id.transport_code,
                'date': doc.expiry_date,
            }
            mail_values = {
                'subject': _('Fleet Document Reminder: %s') % doc.name,
                'body_html': '<p>%s</p>' % body,
                'email_to': email_to,
                'author_id': partner.id,
            }
            Mail.create(mail_values).send()
            doc.write({'last_reminder_date': today_date})
            sent_docs |= doc
        return bool(sent_docs)


class RmcOperatorDayReport(models.Model):
    _name = 'rmc.operator.day.report'
    _description = 'Operator Day Report'
    _order = 'report_date desc'

    name = fields.Char(string='Reference', required=True, copy=False, default=lambda self: self._default_name())
    plant_id = fields.Many2one('rmc.subcontractor.plant', string='Plant', required=True, ondelete='cascade')
    operator_user_id = fields.Many2one('res.users', string='Operator User', required=True)
    report_date = fields.Date(string='Report Date', default=fields.Date.context_today, required=True)
    docket_ids = fields.Many2many('rmc.docket', 'rmc_operator_day_report_docket_rel', 'report_id', 'docket_id', string='Dockets')
    total_jobs = fields.Integer(string='Total Jobs', compute='_compute_totals', store=True)
    completed_jobs = fields.Integer(string='Completed Jobs', compute='_compute_totals', store=True)
    pending_jobs = fields.Integer(string='Pending Jobs', compute='_compute_totals', store=True)
    total_quantity = fields.Float(string='Total Quantity', compute='_compute_totals', store=True)
    remarks = fields.Text(string='Remarks')
    generated_automatically = fields.Boolean(string='Generated Automatically', default=False, readonly=True)

    _sql_constraints = [
        ('unique_plant_date_operator', 'unique(plant_id, operator_user_id, report_date)', 'A day report already exists for this plant, operator, and date.'),
    ]

    def _default_name(self):
        today = fields.Date.context_today(self)
        return _('Day Report - %s') % today

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for report, vals in zip(records, vals_list):
            if not report.name:
                report_date = vals.get('report_date') or report.report_date
                plant = report.plant_id
                plant_label = plant.plant_code or plant.name or _('Day Report')
                report.name = '%s - %s' % (plant_label, report_date)
            elif report.name.startswith('Day Report -') and report.plant_id:
                report.name = '%s - %s' % (report.plant_id.plant_code or report.plant_id.name or _('Day Report'), report.report_date)
        return records

    @api.depends('docket_ids', 'docket_ids.state', 'docket_ids.quantity_produced')
    def _compute_totals(self):
        for report in self:
            report.total_jobs = len(report.docket_ids)
            report.completed_jobs = len(report.docket_ids.filtered(lambda d: d.state == 'delivered'))
            report.pending_jobs = report.total_jobs - report.completed_jobs
            report.total_quantity = sum(report.docket_ids.mapped('quantity_produced'))

    @api.model
    def _get_previous_day_bounds(self, target_date):
        """Return (start, end) datetime strings for the given date."""
        if isinstance(target_date, str):
            target_date = fields.Date.to_date(target_date)
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=1)
        return fields.Datetime.to_string(start_dt), fields.Datetime.to_string(end_dt)

    @api.model
    def _prepare_day_report_vals(self, plant, operator, report_date, docket_ids, generated_automatically):
        return {
            'plant_id': plant.id,
            'operator_user_id': operator.id,
            'report_date': report_date,
            'generated_automatically': generated_automatically,
            'docket_ids': [(6, 0, docket_ids)],
        }

    @api.model
    def _create_day_report_for_plant(self, plant, report_date, generated_automatically=True):
        operator = plant.operator_user_id
        if not operator:
            return False

        existing = self.search([
            ('plant_id', '=', plant.id),
            ('operator_user_id', '=', operator.id),
            ('report_date', '=', report_date),
        ], limit=1)
        if existing:
            return existing

        start_dt, end_dt = self._get_previous_day_bounds(report_date)
        dockets_domain = [
            ('subcontractor_plant_id', '=', plant.id),
            ('docket_date', '>=', start_dt),
            ('docket_date', '<', end_dt),
        ]
        dockets = self.env['rmc.docket'].sudo().search(dockets_domain)
        # Always create the report so subcontractor sees daily visibility, even if no dockets were completed.
        vals = self._prepare_day_report_vals(plant, operator, report_date, dockets.ids, generated_automatically)
        report = self.create(vals)
        if dockets:
            dockets.sudo().write({'operator_day_report_id': report.id})
        return report

    @api.model
    def cron_generate_day_reports(self):
        report_date = fields.Date.today() - timedelta(days=1)
        plants = self.env['rmc.subcontractor.plant'].sudo().search([
            ('operator_portal_enabled', '=', True),
            ('operator_user_id', '!=', False),
        ])
        created_count = 0
        for plant in plants:
            try:
                report = self.sudo()._create_day_report_for_plant(plant, report_date, generated_automatically=True)
                if report and report.generated_automatically:
                    created_count += 1
            except Exception as exc:
                _logger.exception("Failed generating day report for plant %s: %s", plant.id, exc)
        if created_count:
            _logger.info("Auto generated %s operator day reports for %s", created_count, report_date)
        return True
