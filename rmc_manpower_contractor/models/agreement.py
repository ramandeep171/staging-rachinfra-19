# -*- coding: utf-8 -*-
"""
RMC Contract Agreement Model
Main model for contractor lifecycle management
"""

import base64
import logging
from datetime import datetime, timedelta, time

import pytz

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

class RmcContractAgreement(models.Model):
    _name = 'rmc.contract.agreement'
    _description = 'RMC Contract Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    # Basic Information
    name = fields.Char(
        string='Agreement Reference',
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New'),
        tracking=True
    )
    contractor_id = fields.Many2one(
        'res.partner',
        string='Contractor',
        required=True,
        # domain="[('supplier_rank', '>', 0)]",
        tracking=True
    )
    contract_type = fields.Selection([
        ('driver_transport', 'Transport/Driver Contract'),
        ('pump_ops', 'Workforce Supply & Operations Agreement'),
        ('accounts_audit', 'Accounts & Auditor Manpower')
    ], string='Contract Type', required=True, tracking=True)
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('offer', 'Offer Sent'),
        ('negotiation', 'Under Negotiation'),
        ('registration', 'Registration'),
        ('verification', 'Verification'),
        ('sign_pending', 'Pending Signature'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('expired', 'Expired')
    ], string='Status', default='draft', required=True, tracking=True)

    # Sign Integration
    sign_template_id = fields.Many2one(
        'sign.template',
        string='Sign Template',
        help='Odoo Sign template to use for this agreement'
    )
    sign_request_id = fields.Many2one(
        'sign.request',
        string='Sign Request',
        readonly=True,
        copy=False
    )
    sign_state = fields.Selection(
        related='sign_request_id.state',
        string='Signature Status',
        store=True
    )
    is_agreement_signed = fields.Boolean(
        string='Is Signed',
        compute='_compute_is_signed',
        store=True
    )

    # Website/Portal
    dynamic_web_path = fields.Char(
        string='Web Path',
        compute='_compute_web_path',
        store=True
    )

    # Validity Period
    validity_start = fields.Date(string='Valid From', tracking=True)
    validity_end = fields.Date(string='Valid Until', tracking=True)

    # Financial Fields - Wage Matrix
    mgq_target = fields.Float(
        string='MGQ Target (m³)',
        help='Minimum Guaranteed Quantity target for the month',
        digits='Product Unit of Measure'
    )
    part_a_fixed = fields.Monetary(
        string='Part-A Fixed Amount',
        currency_field='currency_id',
        help='Fixed monthly payment component'
    )
    part_b_variable = fields.Monetary(
        string='Part-B Variable Amount',
        currency_field='currency_id',
        help='Variable payment linked to MGQ achievement'
    )
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        compute='_compute_total_amount',
        inverse='_inverse_total_amount',
        store=True,
        help='Sum of Part-A fixed and Part-B variable components'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # Manpower Matrix (One2many)
    manpower_matrix_ids = fields.One2many(
        'rmc.manpower.matrix',
        'agreement_id',
        string='Manpower Matrix',
        help='Designation-wise headcount and rates'
    )

    # Performance Metrics
    performance_score = fields.Float(
        string='Performance Score',
        digits=(5, 2),
        compute='_compute_performance',
        store=True,
        tracking=True
    )
    stars = fields.Selection([
        ('1', '⭐'),
        ('2', '⭐⭐'),
        ('3', '⭐⭐⭐'),
        ('4', '⭐⭐⭐⭐'),
        ('5', '⭐⭐⭐⭐⭐')
    ], string='Star Rating', compute='_compute_stars', store=True)

    # Type-Specific KPIs
    avg_diesel_efficiency = fields.Float(
        string='Avg Diesel Efficiency (km/l or m³/l)',
        digits=(5, 2),
        compute='_compute_diesel_kpi',
        store=True
    )
    maintenance_compliance = fields.Float(
        string='Maintenance Compliance (%)',
        digits=(5, 2),
        compute='_compute_maintenance_kpi',
        store=True
    )
    attendance_compliance = fields.Float(
        string='Attendance Compliance (%)',
        digits=(5, 2),
        compute='_compute_attendance_kpi',
        store=True
    )

    @api.depends('part_a_fixed', 'part_b_variable')
    def _compute_total_amount(self):
        for agreement in self:
            agreement.total_amount = (agreement.part_a_fixed or 0.0) + (agreement.part_b_variable or 0.0)

    def _inverse_total_amount(self):
        for agreement in self:
            total = agreement.total_amount or 0.0
            part_a = agreement.part_a_fixed or 0.0
            part_b = total - part_a
            agreement.part_b_variable = part_b if part_b > 0 else 0.0

    # Pending Items
    pending_items_count = fields.Integer(
        string='Pending Items',
        compute='_compute_pending_items',
        store=True
    )
    
    # Payment Hold Logic
    payment_hold = fields.Boolean(
        string='Payment on Hold',
        compute='_compute_payment_hold',
        store=True,
        tracking=True
    )
    payment_hold_reason = fields.Text(
        string='Hold Reason',
        compute='_compute_payment_hold'
    )

    # Related Records (One2many)
    diesel_log_ids = fields.One2many(
        'rmc.diesel.log',
        'agreement_id',
        string='Diesel Logs'
    )
    maintenance_check_ids = fields.One2many(
        'rmc.maintenance.check',
        'agreement_id',
        string='Maintenance Checks'
    )
    attendance_compliance_ids = fields.One2many(
        'rmc.attendance.compliance',
        'agreement_id',
        string='Attendance Records'
    )
    vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        'rmc_agreement_vehicle_rel',
        'agreement_id',
        'vehicle_id',
        string='Fleet Vehicles',
        compute='_compute_assignment_resources',
        store=True,
        help='Fleet vehicles assigned to this agreement and used for diesel logging.'
    )
    fleet_vehicle_count = fields.Integer(
        string='Fleet Vehicles',
        compute='_compute_counts',
        store=True
    )
    vehicle_diesel_log_ids = fields.Many2many(
        'diesel.log',
        string='Vehicle Diesel Logs',
        compute='_compute_vehicle_diesel_logs',
        help='Diesel log entries captured on fleet vehicles assigned to this agreement.'
    )
    equipment_ids = fields.Many2many(
        'maintenance.equipment',
        string='Assigned Equipment',
        compute='_compute_equipment_resources',
        store=True,
        help='Maintenance equipment assigned to employees linked to this agreement.'
    )
    equipment_request_ids = fields.Many2many(
        'maintenance.request',
        string='Equipment Maintenance Requests',
        compute='_compute_equipment_resources',
        help='Maintenance requests belonging to equipment assigned on this agreement.'
    )
    equipment_count = fields.Integer(
        string='Equipment',
        compute='_compute_counts',
        store=True
    )
    equipment_request_count = fields.Integer(
        string='Equipment Requests',
        compute='_compute_counts',
        store=True
    )
    employee_attendance_ids = fields.Many2many(
        'hr.attendance',
        string='Employee Attendance',
        compute='_compute_employee_attendance',
        help='HR attendance entries corresponding to agreement employees.'
    )
    employee_attendance_count = fields.Integer(
        string='Attendance Records',
        compute='_compute_counts'
    )
    activity_start_date = fields.Date(
        string='Activity Start Date',
        compute='_compute_activity_start_date'
    )
    driver_ids = fields.Many2many(
        'hr.employee',
        'rmc_agreement_employee_rel',
        'agreement_id',
        'employee_id',
        string='Assigned Employees',
        compute='_compute_assignment_resources',
        store=True,
        help='Employees (drivers/operators) linked to this agreement for attendance and KPI tracking.'
    )
    signer_ids = fields.One2many(
        'rmc.agreement.signer',
        'agreement_id',
        string='Agreement Signers',
        help='Optional overrides for sign template roles. Leave blank to use defaults.'
    )

    @api.depends(
        'manpower_matrix_ids.employee_id',
        'manpower_matrix_ids.employee_id.car_ids',
        'manpower_matrix_ids.vehicle_id'
    )
    def _compute_assignment_resources(self):
        for agreement in self:
            employees = agreement.manpower_matrix_ids.mapped('employee_id').filtered(lambda e: e)
            matrix_vehicles = agreement.manpower_matrix_ids.mapped('vehicle_id')
            employee_vehicles = employees.mapped('car_ids')
            vehicles = (matrix_vehicles | employee_vehicles).filtered(lambda v: v)
            agreement.driver_ids = employees
            agreement.vehicle_ids = vehicles

    def _get_activity_start_datetime(self):
        self.ensure_one()
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        dt_local = None
        if self.validity_start:
            dt_local = user_tz.localize(datetime.combine(self.validity_start, time.min))
        elif self.sign_request_id and self.sign_request_id.completion_date:
            dt_local = user_tz.localize(datetime.combine(self.sign_request_id.completion_date, time.min))
        else:
            base_dt = self.create_date or fields.Datetime.now()
            dt_local = fields.Datetime.context_timestamp(self, base_dt)
        if dt_local.tzinfo is None:
            dt_local = user_tz.localize(dt_local)
        dt_utc = dt_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return dt_utc

    @api.depends(
        'driver_ids',
        'manpower_matrix_ids.employee_id',
        'manpower_matrix_ids.employee_id.equipment_ids'
    )
    def _compute_equipment_resources(self):
        Equipment = self.env['maintenance.equipment']
        Request = self.env['maintenance.request']
        for agreement in self:
            employees = (agreement.driver_ids | agreement.manpower_matrix_ids.mapped('employee_id')).filtered(lambda e: e)
            if employees:
                start_dt = agreement._get_activity_start_datetime()
                domain = [('employee_id', 'in', employees.ids)]
                if 'assignment_date' in Equipment._fields:
                    domain += ['|', ('assignment_date', '=', False), ('assignment_date', '>=', start_dt.date())]
                if 'agreement_id' in Equipment._fields:
                    domain.append(('agreement_id', '=', agreement.id))
                equipments = Equipment.search(domain)
            else:
                equipments = Equipment.browse()
            agreement.equipment_ids = equipments
            if equipments:
                start_dt = agreement._get_activity_start_datetime()
                domain = [('equipment_id', 'in', equipments.ids)]
                if 'request_date' in Request._fields:
                    domain += ['|', ('request_date', '=', False), ('request_date', '>=', start_dt.date())]
                if 'agreement_id' in Request._fields:
                    domain.append(('agreement_id', '=', agreement.id))
                requests = Request.search(domain)
            else:
                requests = Request.browse()
            agreement.equipment_request_ids = requests

    @api.depends('driver_ids', 'manpower_matrix_ids.employee_id')
    def _compute_employee_attendance(self):
        Attendance = self.env['hr.attendance']
        for agreement in self:
            employees = (agreement.driver_ids | agreement.manpower_matrix_ids.mapped('employee_id')).filtered(lambda e: e)
            if employees:
                start_dt = agreement._get_activity_start_datetime()
                attendances = Attendance.search([('employee_id', 'in', employees.ids)])
                attendances = attendances.filtered(lambda a: (a.check_in and a.check_in >= start_dt) or (a.check_out and a.check_out >= start_dt))
            else:
                attendances = Attendance.browse()
            agreement.employee_attendance_ids = attendances

    def _compute_vehicle_diesel_logs(self):
        for agreement in self:
            logs = self.env['diesel.log']
            if agreement.vehicle_ids:
                domain = [('vehicle_id', 'in', agreement.vehicle_ids.ids)]
                start_dt = agreement._get_activity_start_datetime()
                if 'date' in logs._fields:
                    domain += ['|', ('date', '=', False), ('date', '>=', start_dt.date())]
                logs = logs.search(domain)
            else:
                logs = logs.browse()
            agreement.vehicle_diesel_log_ids = logs

    def _generate_contract_pdf(self):
        self.ensure_one()
        self._ensure_clause_defaults()
        report = self.env.ref('rmc_manpower_contractor.action_report_agreement_contract')
        pdf_bytes, _ = report._render_qweb_pdf(report.report_name, res_ids=[self.id])
        filename = f"{self.name or 'agreement'}.pdf"
        return pdf_bytes, filename

    def _refresh_sign_template(self, pdf_bytes, filename):
        self.ensure_one()
        if not self.sign_template_id:
            raise UserError(_('Please configure a Sign Template before sending for signature.'))

        template = self.sign_template_id
        template_sudo = template.sudo()
        template_sudo.write({
            'authorized_ids': [(4, self.env.user.id)],
            'favorited_ids': [(4, self.env.user.id)],
        })
        if template_sudo.has_sign_requests:
            authorized_ids = template_sudo.authorized_ids.ids
            favorited_ids = template_sudo.favorited_ids.ids
            if self.env.user.id not in authorized_ids:
                authorized_ids.append(self.env.user.id)
            if self.env.user.id not in favorited_ids:
                favorited_ids.append(self.env.user.id)
            copy_vals = {
                'name': '%s - %s' % (
                    self.name or _('Agreement'),
                    _('Signature Template Copy')
                ),
                'authorized_ids': [(6, 0, authorized_ids)],
                'favorited_ids': [(6, 0, favorited_ids)],
            }
            template_sudo = template_sudo.copy(copy_vals)
            template_sudo.write({
                'authorized_ids': [(4, self.env.user.id)],
                'favorited_ids': [(4, self.env.user.id)],
            })
            self.sign_template_id = template_sudo.id
            template = template_sudo

        existing_documents = template_sudo.document_ids.sorted('sequence')
        document_blueprints = []
        for document in existing_documents:
            document_blueprints.append({
                'sequence': document.sequence,
                'items': document.sign_item_ids.copy_data(),
            })

        existing_documents.unlink()

        encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        template_sudo.update_from_attachment_data([{
            'name': filename,
            'datas': encoded_pdf,
        }])

        new_documents = template_sudo.document_ids.sorted('sequence')
        SignItem = self.env['sign.item'].sudo()
        for blueprint, new_document in zip(document_blueprints, new_documents):
            item_vals_list = blueprint.get('items') or []
            if item_vals_list:
                for item_vals in item_vals_list:
                    item_vals['document_id'] = new_document.id
                SignItem.create(item_vals_list)
            if blueprint.get('sequence') is not None:
                new_document.sequence = blueprint['sequence']

        if not template_sudo.sign_item_ids:
            seed_template = self._get_sign_template_seed()
            if seed_template and seed_template != template:
                seed_documents = seed_template.document_ids.sorted('sequence')
                for index, new_document in enumerate(new_documents):
                    if not seed_documents:
                        break
                    source_document = seed_documents[min(index, len(seed_documents) - 1)]
                    seed_item_vals = source_document.sign_item_ids.copy_data()
                    if seed_item_vals:
                        for seed_vals in seed_item_vals:
                            seed_vals['document_id'] = new_document.id
                        SignItem.create(seed_item_vals)

        template_sudo.write({'name': filename})
        template_sudo._invalidate_cache(fnames=['document_ids', 'sign_item_ids'])
        self._ensure_signature_blocks()
        self._sync_signers_with_template()

    def _default_partner_for_role(self, role):
        self.ensure_one()
        contractor_partner = self.contractor_id
        company_partner = self.env.company.partner_id

        role_name = (role.name or '').lower()
        if contractor_partner and any(keyword in role_name for keyword in ['contractor', 'customer', 'supplier']):
            return contractor_partner
        if company_partner and any(keyword in role_name for keyword in ['company', 'internal', 'manager']):
            return company_partner

        return contractor_partner or company_partner

    def _get_sign_template_seed(self):
        """Return a sign.template record that can be used as a seed for duplication."""
        self.ensure_one()
        template = self.env.ref(
            'rmc_manpower_contractor.sign_template_rmc_contractor',
            raise_if_not_found=False
        )
        if template:
            return template

        domain = [
            ('active', '=', True),
            '|', ('company_id', '=', False),
            ('company_id', '=', self.company_id.id if self.company_id else self.env.company.id),
        ]
        return self.env['sign.template'].search(domain, order='id desc', limit=1)

    def _sync_signers_with_template(self):
        """Align signer overrides with the currently selected sign template."""
        for agreement in self:
            template = agreement.sign_template_id.sudo()
            if not template:
                agreement.signer_ids = [(5, 0, 0)]
                continue

            commands = [(5, 0, 0)]
            roles_added = set()
            sequence_counter = 10
            for item in template.sign_item_ids:
                role = item.responsible_id
                if not role or role.id in roles_added:
                    continue
                roles_added.add(role.id)
                default_partner = agreement._default_partner_for_role(role)
                commands.append((0, 0, {
                    'role_id': role.id,
                    'partner_id': default_partner.id if default_partner else False,
                    'sequence': sequence_counter,
                }))
                sequence_counter += 10
            agreement.signer_ids = commands

    def _get_or_create_role(self, xmlid, name):
        role = self.env.ref(xmlid, raise_if_not_found=False)
        if role:
            return role.sudo()
        role = self.env['sign.item.role'].sudo().search([('name', '=', name)], limit=1)
        if role:
            return role
        return self.env['sign.item.role'].sudo().create({'name': name})

    def _ensure_signature_blocks(self):
        """
        Make sure the sign template has signature + date fields for company and contractor.
        """
        SignItem = self.env['sign.item'].sudo()
        signature_type = self.env.ref('sign.sign_item_type_signature', raise_if_not_found=False)
        date_type = self.env.ref('sign.sign_item_type_date', raise_if_not_found=False)
        if not signature_type or not date_type:
            return

        for agreement in self:
            template = agreement.sign_template_id
            if not template or not template.document_ids:
                continue
            template_sudo = template.sudo()
            sign_items_sudo = template_sudo.sign_item_ids

            company_role = self._get_or_create_role(
                'rmc_manpower_contractor.sign_role_rmc_company',
                _('Company Signatory')
            )
            contractor_role = self._get_or_create_role(
                'rmc_manpower_contractor.sign_role_rmc_contractor',
                _('Contractor Signatory')
            )
            allowed_roles = company_role | contractor_role

            target_document = template_sudo.document_ids.sorted('sequence')[-1]
            target_page = target_document.num_pages or max(sign_items_sudo.mapped('page') or [1])

            stale_items = sign_items_sudo.filtered(
                lambda item: item.type_id in (signature_type, date_type) and item.responsible_id not in allowed_roles
            )
            if stale_items:
                stale_items.unlink()
                sign_items_sudo = template_sudo.sign_item_ids

            def _ensure_field(role, field_type, name, posx, posy, width, height):
                nonlocal sign_items_sudo
                existing = sign_items_sudo.filtered(
                    lambda item: item.responsible_id == role and item.type_id == field_type
                )
                if len(existing) > 1:
                    existing[1:].unlink()
                    sign_items_sudo = template_sudo.sign_item_ids
                    existing = sign_items_sudo.filtered(
                        lambda item: item.responsible_id == role and item.type_id == field_type
                    )
                existing = existing[:1].sudo()
                vals = {
                    'document_id': target_document.id,
                    'type_id': field_type.id,
                    'responsible_id': role.id if role else False,
                    'name': name,
                    'page': target_page,
                    'posX': posx,
                    'posY': posy,
                    'width': width,
                    'height': height,
                    'alignment': 'left',
                    'required': True,
                }
                if existing:
                    existing.write(vals)
                else:
                    new_item = SignItem.create(vals)
                    sign_items_sudo |= new_item

            # company block (left column)
            _ensure_field(company_role, date_type, _('Company Sign Date'), 0.12, 0.84, 0.24, 0.05)
            _ensure_field(company_role, signature_type, _('Company Signature'), 0.12, 0.90, 0.30, 0.08)
            # contractor block (right column)
            _ensure_field(contractor_role, date_type, _('Contractor Sign Date'), 0.56, 0.84, 0.24, 0.05)
            _ensure_field(contractor_role, signature_type, _('Contractor Signature'), 0.56, 0.90, 0.30, 0.08)
            template_sudo._invalidate_cache(fnames=['sign_item_ids'])

    def _ensure_sign_template(self):
        """
        Ensure each agreement has its own sign template.
        If none is linked yet, duplicate a seed template and assign it.
        """
        for agreement in self:
            if agreement.sign_template_id:
                template = agreement.sign_template_id
                template_sudo = template.sudo()
                template_sudo.write({
                    'authorized_ids': [(4, self.env.user.id)],
                    'favorited_ids': [(4, self.env.user.id)],
                })
                template_sudo._invalidate_cache(fnames=['document_ids', 'sign_item_ids'])
                agreement._ensure_signature_blocks()
                agreement._sync_signers_with_template()
                continue

            seed_template = agreement._get_sign_template_seed()
            if not seed_template:
                raise UserError(
                    _('No Sign Template configured. Please create a base template '
                      'under Sign > Configuration > Templates to seed agreement copies.')
                )

            copy_vals = {
                'name': '%s - %s' % (
                    agreement.name or _('Agreement'),
                    _('Signature Template')
                ),
                'user_id': self.env.user.id,
            }
            target_company = agreement.company_id or self.env.company
            seed_template_sudo = seed_template.sudo()
            new_template = seed_template_sudo.with_company(target_company).copy(copy_vals)

            agreement.with_company(target_company).write({
                'sign_template_id': new_template.id,
            })
            new_template_sudo = new_template.sudo()
            new_template_sudo.write({
                'authorized_ids': [(4, self.env.user.id)],
                'favorited_ids': [(4, self.env.user.id)],
            })
            new_template_sudo._invalidate_cache(fnames=['document_ids', 'sign_item_ids'])
            agreement._ensure_signature_blocks()
            agreement._sync_signers_with_template()

    @api.onchange('sign_template_id')
    def _onchange_sign_template_id(self):
        for agreement in self:
            agreement._sync_signers_with_template()
    breakdown_event_ids = fields.One2many(
        'rmc.breakdown.event',
        'agreement_id',
        string='Breakdown Events'
    )
    inventory_handover_ids = fields.One2many(
        'rmc.inventory.handover',
        'agreement_id',
        string='Inventory Handovers'
    )
    vendor_bill_ids = fields.One2many(
        'account.move',
        'agreement_id',
        string='Vendor Bills',
        domain=[('move_type', '=', 'in_invoice')]
    )

    # Smart Button Counts
    diesel_log_count = fields.Integer(compute='_compute_counts')
    maintenance_check_count = fields.Integer(compute='_compute_counts')
    attendance_compliance_count = fields.Integer(compute='_compute_counts')
    breakdown_event_count = fields.Integer(compute='_compute_counts')
    inventory_handover_count = fields.Integer(compute='_compute_counts')
    vendor_bill_count = fields.Integer(compute='_compute_counts')

    # Analytics
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account'
    )

    # Additional Info
    notes = fields.Html(string='Internal Notes')
    clause_ids = fields.One2many(
        'rmc.agreement.clause',
        'agreement_id',
        string='Clauses',
        copy=True,
        help='Editable clause sections that will appear in the agreement PDF.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Generate sequence and create agreement"""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'rmc.contract.agreement'
                ) or _('New')
        agreements = super(RmcContractAgreement, self).create(vals_list)
        agreements._ensure_clause_defaults()
        return agreements

    def write(self, vals):
        contract_type_changed = 'contract_type' in vals
        res = super().write(vals)
        if contract_type_changed:
            self._ensure_clause_defaults()
        return res

    @api.depends('sign_request_id', 'sign_request_id.state')
    def _compute_is_signed(self):
        """Check if agreement is signed"""
        for record in self:
            record.is_agreement_signed = record.is_signed()

    def is_signed(self):
        """Returns True if agreement has been signed"""
        self.ensure_one()
        if self.sign_request_id and self.sign_request_id.state == 'signed':
            return True
        # Fallback: check for signed document attachment
        signed_docs = self.env['ir.attachment'].search([
            ('res_model', '=', 'rmc.contract.agreement'),
            ('res_id', '=', self.id),
            ('name', 'ilike', 'signed')
        ], limit=1)
        return bool(signed_docs)

    def _compute_web_path(self):
        """Generate dynamic web path for portal access"""
        for record in self:
            if record.id:
                record.dynamic_web_path = f'/contract/agreement/{record.id}'
            else:
                record.dynamic_web_path = False

    @api.depends('diesel_log_ids', 'diesel_log_ids.state',
                 'maintenance_check_ids', 'maintenance_check_ids.state',
                 'attendance_compliance_ids', 'attendance_compliance_ids.state',
                 'contract_type')
    def _compute_pending_items(self):
        """Count pending/unvalidated items based on contract type"""
        for record in self:
            count = 0
            if record.contract_type == 'driver_transport':
                # Diesel is mandatory
                count += record.diesel_log_ids.filtered(
                    lambda x: x.state in ('draft', 'pending_agreement')
                ).mapped('id').__len__()
            elif record.contract_type == 'pump_ops':
                # Maintenance is mandatory
                count += record.maintenance_check_ids.filtered(
                    lambda x: x.state in ('draft', 'pending_agreement')
                ).mapped('id').__len__()
            elif record.contract_type == 'accounts_audit':
                # Attendance is mandatory
                count += record.attendance_compliance_ids.filtered(
                    lambda x: x.state in ('draft', 'pending_agreement')
                ).mapped('id').__len__()
            record.pending_items_count = count

    @api.depends('diesel_log_ids', 'diesel_log_ids.diesel_efficiency',
                 'diesel_log_ids.state')
    def _compute_diesel_kpi(self):
        """Calculate average diesel efficiency from validated logs"""
        for record in self:
            validated_logs = record.diesel_log_ids.filtered(
                lambda x: x.state == 'validated' and x.diesel_efficiency > 0
            )
            if validated_logs:
                record.avg_diesel_efficiency = sum(
                    validated_logs.mapped('diesel_efficiency')
                ) / len(validated_logs)
            else:
                record.avg_diesel_efficiency = 0.0

    @api.depends('maintenance_check_ids', 'maintenance_check_ids.checklist_ok',
                 'maintenance_check_ids.state')
    def _compute_maintenance_kpi(self):
        """Calculate average maintenance compliance from validated checks"""
        for record in self:
            validated_checks = record.maintenance_check_ids.filtered(
                lambda x: x.state == 'validated'
            )
            if validated_checks:
                record.maintenance_compliance = sum(
                    validated_checks.mapped('checklist_ok')
                ) / len(validated_checks)
            else:
                record.maintenance_compliance = 0.0

    @api.depends('attendance_compliance_ids',
                 'attendance_compliance_ids.compliance_percentage',
                 'attendance_compliance_ids.state')
    def _compute_attendance_kpi(self):
        """Calculate average attendance compliance"""
        for record in self:
            validated_attendance = record.attendance_compliance_ids.filtered(
                lambda x: x.state == 'validated'
            )
            if validated_attendance:
                record.attendance_compliance = sum(
                    validated_attendance.mapped('compliance_percentage')
                ) / len(validated_attendance)
            else:
                record.attendance_compliance = 0.0

    @api.depends('avg_diesel_efficiency', 'maintenance_compliance',
                 'attendance_compliance', 'contract_type')
    def _compute_performance(self):
        """
        Compute weighted performance score based on contract type
        Weights from ir.config_parameter
        """
        ICP = self.env['ir.config_parameter'].sudo()
        weight_diesel = float(ICP.get_param('rmc_score.weight_diesel', 0.5))
        weight_maint = float(ICP.get_param('rmc_score.weight_maintenance', 0.3))
        weight_attend = float(ICP.get_param('rmc_score.weight_attendance', 0.2))

        for record in self:
            score = 0.0
            
            if record.contract_type == 'driver_transport':
                # Diesel is primary (normalize to 0-100 assuming 5km/l = 100%)
                diesel_norm = min(record.avg_diesel_efficiency * 20, 100)
                score = diesel_norm * weight_diesel + \
                        record.maintenance_compliance * weight_maint
            elif record.contract_type == 'pump_ops':
                # Maintenance is primary
                score = record.maintenance_compliance * weight_maint + \
                        (record.avg_diesel_efficiency * 20 * weight_diesel if record.avg_diesel_efficiency else 0)
            elif record.contract_type == 'accounts_audit':
                # Attendance is primary
                score = record.attendance_compliance * weight_attend + \
                        record.maintenance_compliance * weight_maint

            record.performance_score = min(score, 100.0)

    @api.depends('performance_score')
    def _compute_stars(self):
        """
        Convert performance score to star rating
        Thresholds from ir.config_parameter
        """
        ICP = self.env['ir.config_parameter'].sudo()
        star_5 = float(ICP.get_param('rmc_score.star_5_threshold', 90))
        star_4 = float(ICP.get_param('rmc_score.star_4_threshold', 75))
        star_3 = float(ICP.get_param('rmc_score.star_3_threshold', 60))
        star_2 = float(ICP.get_param('rmc_score.star_2_threshold', 40))

        for record in self:
            if record.performance_score >= star_5:
                record.stars = '5'
            elif record.performance_score >= star_4:
                record.stars = '4'
            elif record.performance_score >= star_3:
                record.stars = '3'
            elif record.performance_score >= star_2:
                record.stars = '2'
            else:
                record.stars = '1'

    @api.depends('is_agreement_signed', 'pending_items_count', 'contract_type',
                 'diesel_log_ids.state', 'maintenance_check_ids.state',
                 'attendance_compliance_ids.state')
    def _compute_payment_hold(self):
        """
        Determine if payment should be on hold
        Hold conditions:
        1. Agreement not signed
        2. Type-based mandatory KPIs have pending items
        3. Performance score below minimum threshold
        """
        ICP = self.env['ir.config_parameter'].sudo()
        min_score = float(ICP.get_param('rmc_score.min_payment_score', 40))

        for record in self:
            reasons = []
            hold = False

            # Check signature
            if not record.is_signed():
                hold = True
                reasons.append('Agreement not signed')

            # Check pending items
            if record.pending_items_count > 0:
                hold = True
                reasons.append(
                    f'{record.pending_items_count} pending/unvalidated entries'
                )

            # Check type-specific requirements
            if record.contract_type == 'driver_transport':
                if not record.diesel_log_ids.filtered(
                    lambda x: x.state == 'validated'
                ):
                    hold = True
                    reasons.append('No validated diesel logs')
            elif record.contract_type == 'pump_ops':
                if not record.maintenance_check_ids.filtered(
                    lambda x: x.state == 'validated'
                ):
                    hold = True
                    reasons.append('No validated maintenance checks')
            elif record.contract_type == 'accounts_audit':
                if not record.attendance_compliance_ids.filtered(
                    lambda x: x.state == 'validated'
                ):
                    hold = True
                    reasons.append('No validated attendance records')

            # Check minimum performance
            if record.performance_score < min_score:
                hold = True
                reasons.append(
                    f'Performance score {record.performance_score:.1f}% '
                    f'below minimum {min_score}%'
                )

            record.payment_hold = hold
            record.payment_hold_reason = '\n'.join(reasons) if reasons else ''

    @api.depends(
        'diesel_log_ids',
        'diesel_log_ids.vehicle_id',
        'maintenance_check_ids',
        'attendance_compliance_ids',
        'breakdown_event_ids',
        'inventory_handover_ids',
        'vendor_bill_ids',
        'vehicle_ids',
        'vehicle_diesel_log_ids',
        'equipment_ids',
        'equipment_request_ids',
        'employee_attendance_ids'
    )
    def _compute_counts(self):
        """Compute smart button counts"""
        DieselLog = self.env['rmc.diesel.log']
        for record in self:
            logs = record.diesel_log_ids
            ext_count = len(record.vehicle_diesel_log_ids)
            record.diesel_log_count = len(logs) + ext_count
            record.maintenance_check_count = len(record.maintenance_check_ids)
            record.attendance_compliance_count = len(record.attendance_compliance_ids)
            record.breakdown_event_count = len(record.breakdown_event_ids)
            inventory_records = record.inventory_handover_ids.filtered(lambda r: not r.date or r.date >= record.activity_start_date)
            record.inventory_handover_count = len(inventory_records)
            record.vendor_bill_count = len(record.vendor_bill_ids)
            record.fleet_vehicle_count = len(record.vehicle_ids)
            record.equipment_count = len(record.equipment_ids)
            record.equipment_request_count = len(record.equipment_request_ids)
            record.employee_attendance_count = len(record.employee_attendance_ids)

    @api.model
    def _refresh_agreements_for_employees(self, employees):
        """Utility to recompute attendance related data when employees log time."""
        employees = employees.filtered(lambda e: e)
        if not employees:
            return
        agreements = self.search([
            '|',
            ('manpower_matrix_ids.employee_id', 'in', employees.ids),
            ('driver_ids', 'in', employees.ids)
        ])
        if agreements:
            agreements._compute_employee_attendance()
            agreements._compute_counts()

    @api.constrains('validity_start', 'validity_end')
    def _check_validity_dates(self):
        """Ensure validity_end is after validity_start"""
        for record in self:
            if record.validity_start and record.validity_end:
                if record.validity_end < record.validity_start:
                    raise ValidationError(
                        _('Validity end date must be after start date.')
                    )

    @api.constrains('contract_type')
    def _check_contract_type_immutable(self):
        """Contract type cannot be changed after signing"""
        for record in self:
            # Consider the agreement immutable either if it is signed (via sign request
            # or signed document) or if its workflow state has reached 'active'.
            immutable = False
            try:
                immutable = record.is_signed() or record.state == 'active'
            except Exception:
                # defensive: if is_signed fails for any reason, fall back to state check
                immutable = record.state == 'active'

            if immutable and record._origin and record.contract_type != record._origin.contract_type:
                raise ValidationError(
                    _('Cannot change contract type after agreement is signed or activated.')
                )

    def _get_clause_template_commands(self, contract_type):
        ClauseTemplate = self.env['rmc.agreement.clause.template']
        templates = ClauseTemplate.search(
            [('contract_type', '=', contract_type)],
            order='sequence, id'
        )
        commands = []
        for template in templates:
            commands.append((0, 0, {
                'sequence': template.sequence,
                'title': template.title,
                'body_html': template.body_html,
            }))
        return commands

    def _ensure_clause_defaults(self, force=False):
        """
        Ensure default clause set is created for supported contract types.
        Clauses remain editable after creation.
        """
        for agreement in self:
            if agreement.contract_type != 'pump_ops':
                continue
            needs_refresh = force or not agreement.clause_ids
            if not needs_refresh:
                # detect placeholder-only clauses (auto-created but empty)
                placeholder_title = _('New Clause')
                if all((not clause.title or clause.title == placeholder_title) and not clause.body_html for clause in agreement.clause_ids):
                    needs_refresh = True
            if not needs_refresh:
                continue
            if agreement.clause_ids:
                agreement.clause_ids.unlink()
            commands = agreement._get_clause_template_commands(agreement.contract_type)
            if not commands:
                continue
            agreement.write({'clause_ids': commands})

    @api.onchange('contract_type')
    def _onchange_contract_type(self):
        for agreement in self:
            if agreement.contract_type == 'pump_ops' and not agreement.clause_ids:
                agreement.clause_ids = agreement._get_clause_template_commands('pump_ops')

    def action_preview_and_send(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rmc.agreement.send.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_model': self._name,
            }
        }

    def action_send_for_sign(self):
        """
        Prepare (or reuse) the sign request and open it in the Sign app so the
        document can be reviewed/edited before emailing the contractor.
        """
        self.ensure_one()

        sign_request, created = self._create_sign_request(require_email=False, allow_existing=True)
        if not created and sign_request.state == 'signed':
            raise UserError(
                _('The existing sign request is already completed. Create a new agreement to request another signature.')
            )

        if created:
            self.message_post(
                body=_('Sign request prepared in Sign. Review and send to the contractor from the Sign app.'),
                subject=_('Sign Request Prepared')
            )

        return self._action_open_sign_request(sign_request)

    def action_view_sign_request(self):
        self.ensure_one()
        if not self.sign_request_id:
            raise UserError(_('No sign request is linked to this agreement yet.'))
        return self._action_open_sign_request(self.sign_request_id)

    def action_push_to_sign_app(self):
        """
        Create (or reuse) the sign request but do not send emails.
        Returns the form view in the Sign app for manual handling.
        """
        self.ensure_one()
        sign_request, created = self._create_sign_request(require_email=False, allow_existing=True)
        if created:
            self.message_post(
                body=_('Sign request prepared in Sign. Review and send to the contractor from the Sign app.'),
                subject=_('Sign Request Prepared')
            )
        return self._action_open_sign_request(sign_request)

    def _action_open_sign_request(self, sign_request):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sign.request',
            'res_id': sign_request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_sign_request(self, require_email=True, allow_existing=False):
        """
        Shared helper that prepares a sign request from the current agreement.
        Returns a tuple (sign_request, created_bool).
        """
        self.ensure_one()

        self._ensure_sign_template()

        if not self.sign_template_id:
            raise UserError(
                _('Please configure a Sign Template before creating a signature request.')
            )

        if self.sign_request_id:
            if allow_existing:
                return self.sign_request_id, False
            raise UserError(
                _('A sign request already exists for this agreement.')
            )

        if require_email and not self.contractor_id.email:
            raise UserError(
                _('Please set an email address on the contractor before sending for signature.')
            )

        seen = set()
        template_roles = []
        for item in self.sign_template_id.sign_item_ids:
            role = item.responsible_id
            if role and role.id not in seen:
                seen.add(role.id)
                template_roles.append(role)
        if not template_roles:
            raise UserError(
                _('The selected Sign Template does not define any signer roles. Add at least one signer block.')
            )

        signer_map = {signer.role_id.id: signer for signer in self.signer_ids}

        request_items = []
        for idx, role in enumerate(template_roles, start=1):
            partner = False
            sequence = idx

            signer = signer_map.get(role.id)
            if signer:
                partner = signer.partner_id
                sequence = signer.sequence or idx
            if not partner:
                partner = self._default_partner_for_role(role)

            if not partner:
                raise UserError(
                    _('Unable to determine signer partner for role %s. Please adjust the Sign Template or agreement data.') % role.name
                )

            if require_email and not partner.email:
                raise UserError(
                    _('Signer %s must have an email address to receive the signature request.') % partner.display_name
                )

            request_items.append((0, 0, {
                'partner_id': partner.id,
                'role_id': role.id,
                'mail_sent_order': sequence,
            }))

        sign_request = self.env['sign.request'].create({
            'template_id': self.sign_template_id.id,
            'reference': self.name,
            'subject': f'Contract Agreement - {self.name}',
            'request_item_ids': request_items,
        })

        self.sign_request_id = sign_request.id
        self.state = 'sign_pending'

        return sign_request, True

    def action_activate_on_sign(self):
        """
        Called when signature is completed
        - Activate agreement
        - Reconcile pending entries
        - Clear payment hold if conditions met
        """
        self.ensure_one()

        if not self.is_signed():
            raise UserError(_('Agreement must be signed before activation.'))

        self.state = 'active'
        
        # Set validity if not already set
        if not self.validity_start:
            self.validity_start = fields.Date.today()
        if not self.validity_end:
            self.validity_end = fields.Date.today() + timedelta(days=365)

        # Reconcile pending entries - validate those that meet thresholds
        self._reconcile_pending_entries()

        # Recompute performance and payment hold
        self._compute_performance()
        self._compute_payment_hold()

        # Notify stakeholders
        self.message_post(
            body=_('Agreement activated. Payment hold status: %s') % 
                 ('ON HOLD' if self.payment_hold else 'CLEARED'),
            subject=_('Agreement Activated')
        )

        # Create activity for Accounts if payment cleared
        if not self.payment_hold:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.env.ref('account.group_account_invoice').users[0].id if self.env.ref('account.group_account_invoice').users else self.env.user.id,
                summary=_('Agreement ready for billing'),
                note=_('Agreement %s is active and payment hold is cleared.') % self.name
            )

        return True

    def _reconcile_pending_entries(self):
        """
        Validate pending entries that meet minimum thresholds
        """
        self.ensure_one()

        # Diesel logs
        pending_diesel = self.diesel_log_ids.filtered(
            lambda x: x.state == 'pending_agreement'
        )
        for log in pending_diesel:
            if log.diesel_efficiency > 0:  # Simple threshold
                log.state = 'validated'
                log.message_post(
                    body=_('Auto-validated on agreement activation')
                )

        # Maintenance checks
        pending_maint = self.maintenance_check_ids.filtered(
            lambda x: x.state == 'pending_agreement'
        )
        for check in pending_maint:
            if check.checklist_ok >= 50:  # 50% threshold
                check.state = 'validated'
                check.message_post(
                    body=_('Auto-validated on agreement activation')
                )

        # Attendance
        pending_attend = self.attendance_compliance_ids.filtered(
            lambda x: x.state == 'pending_agreement'
        )
        for attend in pending_attend:
            if attend.compliance_percentage >= 70:  # 70% threshold
                attend.state = 'validated'
                attend.message_post(
                    body=_('Auto-validated on agreement activation')
                )

    def compute_performance(self):
        """
        Public method to manually trigger performance computation
        Called by monthly cron
        """
        self._compute_diesel_kpi()
        self._compute_maintenance_kpi()
        self._compute_attendance_kpi()
        self._compute_performance()
        self._compute_stars()
        
        _logger.info(
            f'Performance computed for {self.name}: '
            f'Score={self.performance_score:.2f}, Stars={self.stars}'
        )

    # Smart Button Actions
    def action_view_diesel_logs(self):
        """Open diesel logs for this agreement"""
        self.ensure_one()
        action = self.env.ref('diesel_log.action_diesel_log_list', raise_if_not_found=False)
        if not action:
            action = self.env.ref('rmc_manpower_contractor.action_diesel_log', raise_if_not_found=False)
        if not action:
            raise UserError(_('Diesel log action is missing.'))
        action = action.read()[0]
        start_dt = self._get_activity_start_datetime()
        domain = []
        if self.vehicle_ids:
            domain.append(('vehicle_id', 'in', self.vehicle_ids.ids))
        elif self.driver_ids:
            domain.append(('driver_id', 'in', self.driver_ids.ids))
        if 'date' in self.env['diesel.log']._fields:
            domain += ['|', ('date', '=', False), ('date', '>=', start_dt.date())]
        action['domain'] = domain
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {'active_id': self.id, 'active_model': self._name})
        context = dict(ctx)
        if self.vehicle_ids:
            context.setdefault('default_vehicle_id', self.vehicle_ids.ids[0])
        if self.driver_ids:
            context.setdefault('default_driver_id', self.driver_ids.ids[0])
        action['context'] = context
        return action

    def action_view_equipment(self):
        """Open equipment assigned to agreement employees"""
        self.ensure_one()
        action = self.env.ref('maintenance.hr_equipment_action', raise_if_not_found=False)
        if not action:
            raise UserError(_('Maintenance equipment action is missing.'))
        action = action.read()[0]
        domain = [('id', 'in', self.equipment_ids.ids)] if self.equipment_ids else [('id', '=', False)]
        action['domain'] = domain
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {'active_id': self.id, 'active_model': self._name})
        context = dict(ctx)
        if self.driver_ids:
            context.setdefault('search_default_employee_id', self.driver_ids.ids)
        action['context'] = context
        return action

    def action_view_equipment_requests(self):
        """Open maintenance requests for assigned equipment"""
        self.ensure_one()
        action = self.env.ref('maintenance.hr_equipment_request_action', raise_if_not_found=False)
        if not action:
            raise UserError(_('Maintenance request action is missing.'))
        action = action.read()[0]
        start_dt = self._get_activity_start_datetime()
        domain = [('id', 'in', self.equipment_request_ids.ids)] if self.equipment_request_ids else [('id', '=', False)]
        if 'request_date' in self.env['maintenance.request']._fields:
            domain += ['|', ('request_date', '=', False), ('request_date', '>=', start_dt.date())]
        action['domain'] = domain
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {
                'active_id': self.id,
                'active_model': self._name,
                'uid': self._uid,
                'user': self.env.user,
            })
        context = dict(ctx)
        if self.equipment_ids:
            context.setdefault('search_default_equipment_id', self.equipment_ids.ids)
        context.setdefault('default_user_id', self._uid)
        action['context'] = context
        return action

    def action_new_inventory_handover(self):
        self.ensure_one()
        form_view = self.env.ref('rmc_manpower_contractor.view_inventory_handover_form', raise_if_not_found=False)
        ctx = {
            'default_agreement_id': self.id,
            'default_contractor_id': self.contractor_id.id,
            'default_employee_id': self.driver_ids[:1].id if self.driver_ids else False,
            'default_operation_type': 'contract_issue_product',
        }
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Inventory Request'),
            'res_model': 'rmc.inventory.handover',
            'view_mode': 'form',
            'view_id': form_view.id if form_view else False,
            'target': 'new',
            'context': ctx,
        }

    def action_view_employee_attendance(self):
        """Open HR attendance entries for agreement employees"""
        self.ensure_one()
        action = self.env.ref('hr_attendance.hr_attendance_action', raise_if_not_found=False)
        if not action:
            raise UserError(_('Attendance action is missing.'))
        action = action.read()[0]
        employees = (self.driver_ids | self.manpower_matrix_ids.mapped('employee_id')).filtered(lambda e: e)
        start_dt = self._get_activity_start_datetime()
        if employees:
            domain = ['&', ('employee_id', 'in', employees.ids), '|', ('check_in', '>=', start_dt), ('check_out', '>=', start_dt)]
        else:
            domain = [('employee_id', '=', False)]
        action['domain'] = domain
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {
                'active_id': self.id,
                'active_model': self._name,
                'uid': self._uid,
                'user': self.env.user,
            })
        context = dict(ctx)
        if employees:
            context.setdefault('search_default_employee_id', employees.ids)
        action['context'] = context
        return action

    def _compute_activity_start_date(self):
        for record in self:
            record.activity_start_date = record._get_activity_start_datetime().date()

    def action_view_fleet_vehicles(self):
        """Open fleet vehicles associated with this agreement"""
        self.ensure_one()
        action = self.env.ref('fleet.fleet_vehicle_action', raise_if_not_found=False)
        if not action:
            raise UserError(_('Fleet module action not found.'))
        action = action.read()[0]
        domain = [('id', 'in', self.vehicle_ids.ids)] if self.vehicle_ids else [('id', '=', False)]
        action['domain'] = domain
        ctx = action.get('context') or {}
        if isinstance(ctx, str):
            ctx = safe_eval(ctx, {'active_id': self.id, 'active_model': self._name})
        context = dict(ctx)
        context.setdefault('default_agreement_id', self.id)
        if self.driver_ids:
            context.setdefault('default_driver_id', self.driver_ids[:1].id)
        action['context'] = context
        return action

    def action_view_maintenance_checks(self):
        """Open maintenance checks for this agreement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Maintenance Checks'),
            'res_model': 'rmc.maintenance.check',
            'domain': [('agreement_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_agreement_id': self.id}
        }

    def action_view_attendance(self):
        """Open attendance records for this agreement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Compliance'),
            'res_model': 'rmc.attendance.compliance',
            'domain': [('agreement_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_agreement_id': self.id}
        }

    def action_view_breakdowns(self):
        """Open breakdown events for this agreement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Breakdown Events'),
            'res_model': 'rmc.breakdown.event',
            'domain': [('agreement_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_agreement_id': self.id}
        }

    def action_view_inventory(self):
        """Open inventory handovers for this agreement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Inventory Handovers'),
            'res_model': 'rmc.inventory.handover',
            'domain': [('agreement_id', '=', self.id)],
            'view_mode': 'list,form',
            'context': {'default_agreement_id': self.id}
        }

    def action_view_vendor_bills(self):
        """Open vendor bills for this agreement"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bills'),
            'res_model': 'account.move',
            'domain': [('agreement_id', '=', self.id), ('move_type', '=', 'in_invoice')],
            'view_mode': 'list,form',
            'context': {
                'default_agreement_id': self.id,
                'default_move_type': 'in_invoice',
                'default_partner_id': self.contractor_id.id
            }
        }

    def action_prepare_monthly_bill(self):
        """Open wizard to prepare monthly vendor bill"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prepare Monthly Bill'),
            'res_model': 'rmc.billing.prepare.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_agreement_id': self.id}
        }
