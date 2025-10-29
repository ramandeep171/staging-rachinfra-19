# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime
import base64
import logging

_logger = logging.getLogger(__name__)

class RmcBillingPrepareWizard(models.TransientModel):
    _name = 'rmc.billing.prepare.wizard'
    _description = 'RMC Monthly Billing Preparation Wizard'

    agreement_id = fields.Many2one('rmc.contract.agreement', string='Agreement', required=True, readonly=True)
    contractor_id = fields.Many2one(related='agreement_id.contractor_id', string='Contractor', readonly=True)
    period_start = fields.Date(string='Period Start', required=True, default=lambda self: fields.Date.today().replace(day=1))
    period_end = fields.Date(string='Period End', required=True)
    
    # Part-A (Fixed)
    part_a_amount = fields.Monetary(string='Part-A Fixed', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Part-B (Variable)
    mgq_achieved = fields.Float(string='MGQ Achieved (m³)', digits='Product Unit of Measure')
    mgq_target = fields.Float(related='agreement_id.mgq_target', string='MGQ Target', readonly=True)
    mgq_achievement_pct = fields.Float(string='MGQ Achievement %', compute='_compute_mgq', store=True, digits=(5, 2))
    part_b_amount = fields.Monetary(string='Part-B Variable', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Breakdown deductions (Clause 9)
    breakdown_deduction = fields.Monetary(string='Breakdown Deductions', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Performance bonus/penalty
    performance_score = fields.Float(related='agreement_id.performance_score', string='Performance Score', readonly=True)
    stars = fields.Selection(related='agreement_id.stars', string='Stars', readonly=True)
    bonus_penalty_pct = fields.Float(string='Bonus/Penalty %', compute='_compute_bonus_penalty', store=True, help='Positive = bonus, Negative = penalty')
    bonus_penalty_amount = fields.Monetary(string='Bonus/Penalty Amount', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    # Inventory variance
    inventory_variance = fields.Monetary(string='Inventory Variance', compute='_compute_billing_amounts', store=True, currency_field='currency_id', help='Material shortage/excess')
    
    # Total
    subtotal = fields.Monetary(string='Subtotal (before TDS)', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    tds_amount = fields.Monetary(string='TDS 194C (2%)', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    total_amount = fields.Monetary(string='Net Payable', compute='_compute_billing_amounts', store=True, currency_field='currency_id')
    
    currency_id = fields.Many2one(related='agreement_id.currency_id', string='Currency', readonly=True)
    
    # Supporting reports
    attach_attendance = fields.Boolean(string='Attach Attendance Report', default=True)
    attach_diesel = fields.Boolean(string='Attach Diesel Report', default=True)
    attach_maintenance = fields.Boolean(string='Attach Maintenance Report', default=True)
    attach_breakdown = fields.Boolean(string='Attach Breakdown Report', default=True)
    
    # Approval state
    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('supervisor', 'Awaiting Supervisor'),
        ('manager', 'Awaiting Manager'),
        ('finance', 'Awaiting Finance'),
        ('accounts', 'Awaiting Accounts'),
        ('approved', 'Approved')
    ], string='Approval Status', default='draft', required=True)
    
    state = fields.Selection([('prepare', 'Prepare'), ('review', 'Review'), ('done', 'Done')], default='prepare', required=True)
    notes = fields.Text(string='Notes')

    @api.depends('mgq_achieved', 'mgq_target')
    def _compute_mgq(self):
        for wizard in self:
            if wizard.mgq_target > 0:
                wizard.mgq_achievement_pct = (wizard.mgq_achieved / wizard.mgq_target) * 100
            else:
                wizard.mgq_achievement_pct = 0.0

    @api.depends('performance_score', 'stars')
    def _compute_bonus_penalty(self):
        """
        Star-based bonus/penalty
        5 stars: +10%
        4 stars: +5%
        3 stars: 0%
        2 stars: -5%
        1 star: -10%
        """
        ICP = self.env['ir.config_parameter'].sudo()
        bonus_5 = float(ICP.get_param('rmc_billing.bonus_5_star', 10.0))
        bonus_4 = float(ICP.get_param('rmc_billing.bonus_4_star', 5.0))
        penalty_2 = float(ICP.get_param('rmc_billing.penalty_2_star', -5.0))
        penalty_1 = float(ICP.get_param('rmc_billing.penalty_1_star', -10.0))
        
        for wizard in self:
            if wizard.stars == '5':
                wizard.bonus_penalty_pct = bonus_5
            elif wizard.stars == '4':
                wizard.bonus_penalty_pct = bonus_4
            elif wizard.stars == '3':
                wizard.bonus_penalty_pct = 0.0
            elif wizard.stars == '2':
                wizard.bonus_penalty_pct = penalty_2
            elif wizard.stars == '1':
                wizard.bonus_penalty_pct = penalty_1
            else:
                wizard.bonus_penalty_pct = 0.0

    @api.depends('agreement_id.manpower_matrix_ids', 'mgq_achievement_pct', 'bonus_penalty_pct', 'period_start', 'period_end')
    def _compute_billing_amounts(self):
        for wizard in self:
            # Part-A: Sum of all Part-A entries in manpower matrix
            part_a_lines = wizard.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_a')
            wizard.part_a_amount = sum(part_a_lines.mapped('total_amount'))
            
            # Part-B: Variable component based on MGQ achievement
            part_b_lines = wizard.agreement_id.manpower_matrix_ids.filtered(lambda x: x.remark == 'part_b')
            part_b_base = sum(part_b_lines.mapped('total_amount'))
            
            # Apply MGQ achievement factor (if MGQ < 100%, reduce Part-B proportionally)
            if wizard.mgq_achievement_pct >= 100:
                wizard.part_b_amount = part_b_base
            else:
                wizard.part_b_amount = part_b_base * (wizard.mgq_achievement_pct / 100.0)
            
            # Breakdown deductions (Clause 9)
            breakdown_events = wizard.env['rmc.breakdown.event'].search([
                ('agreement_id', '=', wizard.agreement_id.id),
                ('start_time', '>=', wizard.period_start),
                ('start_time', '<=', wizard.period_end),
                ('state', 'in', ('confirmed', 'closed'))
            ])
            wizard.breakdown_deduction = sum(breakdown_events.mapped('deduction_amount'))
            
            # Inventory variance
            inventory_items = wizard.env['rmc.inventory.handover'].search([
                ('agreement_id', '=', wizard.agreement_id.id),
                ('date', '>=', wizard.period_start),
                ('date', '<=', wizard.period_end),
                ('state', '!=', 'reconciled')
            ])
            wizard.inventory_variance = sum(inventory_items.mapped('variance_value'))
            
            # Bonus/Penalty
            base_for_bonus = wizard.part_a_amount + wizard.part_b_amount
            wizard.bonus_penalty_amount = base_for_bonus * (wizard.bonus_penalty_pct / 100.0)
            
            # Subtotal
            wizard.subtotal = (wizard.part_a_amount + wizard.part_b_amount - 
                              wizard.breakdown_deduction + wizard.bonus_penalty_amount + 
                              wizard.inventory_variance)
            
            # TDS 194C @ 2% (Indian tax on contractor payments)
            wizard.tds_amount = wizard.subtotal * 0.02
            
            # Total
            wizard.total_amount = wizard.subtotal - wizard.tds_amount

    @api.constrains('period_start', 'period_end')
    def _check_periods(self):
        for wizard in self:
            if wizard.period_end < wizard.period_start:
                raise ValidationError(_('Period end must be after period start.'))

    def action_compute(self):
        """Recompute all amounts"""
        self._compute_billing_amounts()
        self.state = 'review'
        return {'type': 'ir.actions.act_window_close'}

    def action_create_bill(self):
        """
        Create vendor bill with all line items and attachments
        Apply multi-level approval chain
        """
        self.ensure_one()
        
        # Pre-flight checks
        if self.agreement_id.payment_hold:
            raise ValidationError(
                _('Cannot create bill: Payment on hold.\n\n%s') % 
                self.agreement_id.payment_hold_reason
            )
        
        if not self.agreement_id.is_signed():
            raise ValidationError(_('Cannot create bill: Agreement not signed.'))
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.contractor_id.id,
            'agreement_id': self.agreement_id.id,
            'invoice_date': fields.Date.today(),
            'date': fields.Date.today(),
            'ref': f'{self.agreement_id.name} - {self.period_start.strftime("%B %Y")}',
            'narration': f'Monthly billing for period {self.period_start} to {self.period_end}\n{self.notes or ""}',
        }
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Create invoice lines
        self._create_invoice_lines(bill)
        
        # Attach supporting reports
        self._attach_reports(bill)
        
        # Reconcile inventory
        self._reconcile_inventory()
        
        # Post message
        bill.message_post(
            body=_(
                'Bill prepared by billing wizard.<br/>'
                'Part-A: %s<br/>'
                'Part-B: %s<br/>'
                'Breakdown Deduction: %s<br/>'
                'Bonus/Penalty: %s<br/>'
                'Inventory Variance: %s<br/>'
                'TDS: %s<br/>'
                '<b>Total: %s</b>'
            ) % (
                self.part_a_amount, self.part_b_amount, self.breakdown_deduction,
                self.bonus_penalty_amount, self.inventory_variance,
                self.tds_amount, self.total_amount
            ),
            subject=_('Monthly Bill Created')
        )
        
        # Create approval activities
        self._create_approval_chain(bill)
        
        self.state = 'done'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_invoice_lines(self, bill):
        """Create detailed invoice lines"""
        InvoiceLine = self.env['account.move.line']
        
        # Get default expense account
        expense_account = self.env['ir.property']._get('property_account_expense_categ_id', 'product.category')
        if not expense_account:
            expense_account = self.env['account.account'].search([
                ('account_type', '=', 'expense'),
                ('company_id', '=', bill.company_id.id)
            ], limit=1)
        
        # Part-A (Fixed)
        if self.part_a_amount > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'Part-A Fixed Manpower Cost ({self.period_start.strftime("%B %Y")})',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.part_a_amount,
                'analytic_distribution': {self.agreement_id.analytic_account_id.id: 100} if self.agreement_id.analytic_account_id else False,
            })
        
        # Part-B (Variable)
        if self.part_b_amount > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'Part-B Variable Manpower Cost (MGQ: {self.mgq_achievement_pct:.1f}%)',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.part_b_amount,
                'analytic_distribution': {self.agreement_id.analytic_account_id.id: 100} if self.agreement_id.analytic_account_id else False,
            })
        
        # Breakdown Deduction
        if self.breakdown_deduction > 0:
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': 'Clause 9 Breakdown Deduction',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': -self.breakdown_deduction,
            })
        
        # Bonus/Penalty
        if self.bonus_penalty_amount != 0:
            label = 'Performance Bonus' if self.bonus_penalty_amount > 0 else 'Performance Penalty'
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': f'{label} ({self.stars} stars, {self.bonus_penalty_pct:+.1f}%)',
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.bonus_penalty_amount,
            })
        
        # Inventory Variance
        if self.inventory_variance != 0:
            label = 'Material Shortage' if self.inventory_variance > 0 else 'Material Excess Credit'
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': label,
                'account_id': expense_account.id,
                'quantity': 1,
                'price_unit': self.inventory_variance,
            })
        
        # TDS 194C
        if self.tds_amount > 0:
            tds_account = self.env['account.account'].search([
                ('code', '=like', '2062%'),  # TDS Payable account
                ('company_id', '=', bill.company_id.id)
            ], limit=1)
            if not tds_account:
                tds_account = expense_account
            
            InvoiceLine.with_context(check_move_validity=False).create({
                'move_id': bill.id,
                'name': 'TDS 194C @ 2% (Contractor Payment)',
                'account_id': tds_account.id,
                'quantity': 1,
                'price_unit': -self.tds_amount,
            })

    def _attach_reports(self, bill):
        """Attach supporting PDF reports to the bill"""
        Attachment = self.env['ir.attachment']
        
        # Attendance Report
        if self.attach_attendance:
            attendance_data = self.env['rmc.attendance.compliance'].search([
                ('agreement_id', '=', self.agreement_id.id),
                ('date', '>=', self.period_start),
                ('date', '<=', self.period_end)
            ])
            if attendance_data:
                # Generate simple HTML report
                html_content = self._generate_attendance_html(attendance_data)
                pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
                    [html_content],
                    landscape=False
                )
                Attachment.create({
                    'name': f'Attendance_Report_{self.period_start.strftime("%Y%m")}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'account.move',
                    'res_id': bill.id,
                    'mimetype': 'application/pdf'
                })
        
        # Diesel Report
        if self.attach_diesel:
            diesel_data = self.env['rmc.diesel.log'].search([
                ('agreement_id', '=', self.agreement_id.id),
                ('date', '>=', self.period_start),
                ('date', '<=', self.period_end)
            ])
            if diesel_data:
                html_content = self._generate_diesel_html(diesel_data)
                pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
                    [html_content],
                    landscape=False
                )
                Attachment.create({
                    'name': f'Diesel_Report_{self.period_start.strftime("%Y%m")}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'account.move',
                    'res_id': bill.id,
                    'mimetype': 'application/pdf'
                })
        
        # Maintenance Report
        if self.attach_maintenance:
            maint_data = self.env['rmc.maintenance.check'].search([
                ('agreement_id', '=', self.agreement_id.id),
                ('date', '>=', self.period_start),
                ('date', '<=', self.period_end)
            ])
            if maint_data:
                html_content = self._generate_maintenance_html(maint_data)
                pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
                    [html_content],
                    landscape=False
                )
                Attachment.create({
                    'name': f'Maintenance_Report_{self.period_start.strftime("%Y%m")}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'account.move',
                    'res_id': bill.id,
                    'mimetype': 'application/pdf'
                })
        
        # Breakdown Report
        if self.attach_breakdown:
            breakdown_data = self.env['rmc.breakdown.event'].search([
                ('agreement_id', '=', self.agreement_id.id),
                ('start_time', '>=', self.period_start),
                ('start_time', '<=', self.period_end)
            ])
            if breakdown_data:
                html_content = self._generate_breakdown_html(breakdown_data)
                pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
                    [html_content],
                    landscape=False
                )
                Attachment.create({
                    'name': f'Breakdown_Report_{self.period_start.strftime("%Y%m")}.pdf',
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': 'account.move',
                    'res_id': bill.id,
                    'mimetype': 'application/pdf'
                })

    def _reconcile_inventory(self):
        """Reconcile all inventory handovers for the period"""
        inventory_items = self.env['rmc.inventory.handover'].search([
            ('agreement_id', '=', self.agreement_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
            ('state', '!=', 'reconciled')
        ])
        for item in inventory_items:
            item.monthly_reconcile_inventory()

    def _create_approval_chain(self, bill):
        """Create multi-level approval activities"""
        # Supervisor approval
        supervisor_group = self.env.ref('rmc_manpower_contractor.group_rmc_supervisor', raise_if_not_found=False)
        if supervisor_group and supervisor_group.users:
            bill.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=supervisor_group.users[0].id,
                summary=_('Approve Monthly Bill - Supervisor'),
                note=_('Please review and approve monthly contractor bill for %s') % self.agreement_id.name
            )

    def _generate_attendance_html(self, data):
        """Generate HTML for attendance report"""
        html = f"""
        <html>
        <head><style>table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid black;padding:5px;}}</style></head>
        <body>
        <h2>Attendance Report - {self.agreement_id.name}</h2>
        <p>Period: {self.period_start} to {self.period_end}</p>
        <table>
        <tr><th>Date</th><th>Expected</th><th>Present</th><th>Compliance %</th></tr>
        """
        for rec in data:
            html += f"<tr><td>{rec.date}</td><td>{rec.headcount_expected}</td><td>{rec.headcount_present}</td><td>{rec.compliance_percentage:.1f}%</td></tr>"
        html += "</table></body></html>"
        return html

    def _generate_diesel_html(self, data):
        """Generate HTML for diesel report"""
        html = f"""
        <html>
        <head><style>table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid black;padding:5px;}}</style></head>
        <body>
        <h2>Diesel Log Report - {self.agreement_id.name}</h2>
        <p>Period: {self.period_start} to {self.period_end}</p>
        <table>
        <tr><th>Date</th><th>Issued (L)</th><th>Work Done</th><th>Efficiency</th></tr>
        """
        for rec in data:
            html += f"<tr><td>{rec.date}</td><td>{rec.issued_ltr:.2f}</td><td>{rec.work_done_m3 or rec.work_done_km:.2f}</td><td>{rec.diesel_efficiency:.2f} {rec.efficiency_unit}</td></tr>"
        html += "</table></body></html>"
        return html

    def _generate_maintenance_html(self, data):
        """Generate HTML for maintenance report"""
        html = f"""
        <html>
        <head><style>table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid black;padding:5px;}}</style></head>
        <body>
        <h2>Maintenance Report - {self.agreement_id.name}</h2>
        <p>Period: {self.period_start} to {self.period_end}</p>
        <table>
        <tr><th>Date</th><th>Machine</th><th>Checklist %</th><th>Repaired</th><th>Cost</th></tr>
        """
        for rec in data:
            html += f"<tr><td>{rec.date}</td><td>{rec.machine_id}</td><td>{rec.checklist_ok:.1f}%</td><td>{'Yes' if rec.repaired else 'No'}</td><td>{rec.cost:.2f}</td></tr>"
        html += "</table></body></html>"
        return html

    def _generate_breakdown_html(self, data):
        """Generate HTML for breakdown report"""
        html = f"""
        <html>
        <head><style>table{{width:100%;border-collapse:collapse;}}th,td{{border:1px solid black;padding:5px;}}</style></head>
        <body>
        <h2>Breakdown Events Report - {self.agreement_id.name}</h2>
        <p>Period: {self.period_start} to {self.period_end}</p>
        <table>
        <tr><th>Event</th><th>Type</th><th>Downtime (hrs)</th><th>Responsibility</th><th>Deduction</th></tr>
        """
        for rec in data:
            html += f"<tr><td>{rec.name}</td><td>{rec.event_type}</td><td>{rec.downtime_hr:.2f}</td><td>{rec.responsibility}</td><td>{rec.deduction_amount:.2f}</td></tr>"
        html += "</table></body></html>"
        return html
