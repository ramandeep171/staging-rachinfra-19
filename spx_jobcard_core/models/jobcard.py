# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    spx_kind = fields.Selection([
        ("preventive", "Preventive"),
        ("corrective", "Corrective"),
        ("emergency", "Emergency Breakdown"),
    ], string="Request Kind", default="corrective",
       help="Explicit classification for this request.")
    
    # Spare parts lines
    spare_line_ids = fields.One2many('maintenance.request.spare', 'request_id', string='Spare Parts')
    # Link to generated spare picking
    spare_picking_id = fields.Many2one('stock.picking', string='Spare Picking', readonly=True)
    spare_picking_count = fields.Integer('Picking Count', compute='_compute_spare_picking_count')
    
    @api.depends('spare_picking_id', 'spare_line_ids.picking_id')
    def _compute_spare_picking_count(self):
        for rec in self:
            picking_ids = set(rec.spare_line_ids.mapped('picking_id').ids)
            if rec.spare_picking_id:
                picking_ids.add(rec.spare_picking_id.id)
            rec.spare_picking_count = len(picking_ids)

    @api.model_create_multi
    def create(self, vals_list):
        """Create maintenance.request records and auto-create an emergency Job Card when needed.
        Uses equipment.x_preferred_vendor_id if available.
        """
        recs = super().create(vals_list)
        Job = self.env["maintenance.jobcard"]

        for req in recs:
            if req.spx_kind == "emergency":
                vendor_id = False
                eq = req.equipment_id
                if eq and ('x_preferred_vendor_id' in eq._fields) and eq.x_preferred_vendor_id:
                    vendor_id = eq.x_preferred_vendor_id.id

                Job.create({
                    'request_id': req.id,
                    'type': 'emergency',
                    'priority': '3',
                    'vendor_id': vendor_id,
                })
        return recs

    def action_open_or_create_jobcard(self):
        self.ensure_one()
        Job = self.env["maintenance.jobcard"]
        existing = Job.search([('request_id', '=', self.id)], limit=1)
        if not existing:
            vendor_id = False
            eq = self.equipment_id
            if eq and ('x_preferred_vendor_id' in eq._fields) and eq.x_preferred_vendor_id:
                vendor_id = eq.x_preferred_vendor_id.id

            existing = Job.create({
                'request_id': self.id,
                'type': self.spx_kind or 'corrective',
                'priority': '1',
                'vendor_id': vendor_id,
            })
        return {
            "name": _("Job Card"),
            "type": "ir.actions.act_window",
            "res_model": "maintenance.jobcard",
            "view_mode": "form",
            "res_id": existing.id,
            "target": "current",
        }

    def _get_internal_locations(self, company):
        Location = self.env['stock.location']
        src = Location.search([('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])], limit=1)
        dst = Location.search([('name', '=', 'Maintenance'), ('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])], limit=1)
        if not dst:
            dst = Location.create({'name': 'Maintenance', 'usage': 'internal', 'company_id': company.id})
        return src, dst

    def action_create_spare_picking(self):
        """Create an internal picking for spare parts linked to this maintenance request.
        It will find-or-create a picking type named 'Maintenance Spare part Issue' (code 'internal').
        """
        Picking = self.env['stock.picking']
        PickingType = self.env['stock.picking.type']
        Move = self.env['stock.move']

        for rec in self:
            company = rec.company_id or self.env.company
            # find or create picking type constrained by company
            ptype = PickingType.search([
                ('name', '=', 'Maintenance Spare part Issue'),
                ('code', '=', 'internal'),
                ('company_id', 'in', [company.id, False]),
            ], limit=1)
            src, dst = rec._get_internal_locations(company)
            if not ptype:
                # create a picking type for maintenance spare issues
                # sequence_code is mandatory in some deployments, set a stable code
                ptype = PickingType.create({
                    'name': 'Maintenance Spare part Issue',
                    'code': 'internal',
                    'sequence_code': 'SPARE_ISSUE',
                    'default_location_src_id': src.id if src else False,
                    'default_location_dest_id': dst.id if dst else False,
                    'company_id': company.id,
                })
            else:
                # ensure existing picking type has a sequence_code (required in some setups)
                if not ptype.sequence_code:
                    try:
                        ptype.sequence_code = 'SPARE_ISSUE'
                    except Exception:
                        # if write fails due to access rights, ignore and proceed
                        pass

            # determine partner for the picking: prefer vendor on request if available,
            # otherwise fall back to equipment's preferred vendor
            partner_id = False
            if 'vendor_id' in rec._fields and rec.vendor_id:
                partner_id = rec.vendor_id.id
            else:
                eq = rec.equipment_id
                if eq and ('x_preferred_vendor_id' in eq._fields) and eq.x_preferred_vendor_id:
                    partner_id = eq.x_preferred_vendor_id.id
            # reuse existing draft picking, otherwise create a fresh one (so closed pickings stay untouched)
            picking = rec.spare_picking_id
            reused = False
            if picking and picking.state == 'draft':
                reused = True
                # keep locations/picking type as-is to avoid unexpected changes; just refresh lines
                picking.move_ids.unlink()
                pending_lines = rec.spare_line_ids.filtered(lambda l: (not l.picking_id or l.picking_id.id == picking.id) and l.qty > 0)
                if not pending_lines:
                    raise UserError(_('No pending spare lines to issue. Add a new spare line first.'))
            else:
                pending_lines = rec.spare_line_ids.filtered(lambda l: not l.picking_id and l.qty > 0)
                if not pending_lines:
                    raise UserError(_('No pending spare lines to issue. Add a new spare line first.'))
                picking_vals = {
                    'picking_type_id': ptype.id,
                    'location_id': ptype.default_location_src_id.id if ptype.default_location_src_id else (src.id if src else False),
                    'location_dest_id': ptype.default_location_dest_id.id if ptype.default_location_dest_id else (dst.id if dst else False),
                    'origin': _('Maintenance Request %s') % (rec.name or rec.id),
                    'partner_id': partner_id,
                    'company_id': company.id,
                }
                picking = Picking.create(picking_vals)

            # Create moves from spare lines
            if pending_lines:
                for line in pending_lines:
                    Move.create({
                        'description_picking_manual': line.description or line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.qty,
                        'product_uom': line.uom_id.id if line.uom_id else line.product_id.uom_id.id,
                        'picking_id': picking.id,
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'company_id': picking.company_id.id,
                    })
                pending_lines.write({'picking_id': picking.id})

            # link and post a message
            rec.spare_picking_id = picking.id
            if reused:
                rec.message_post(body=_('Spare issue picking %s updated from spare lines.') % (picking.display_name,))
            else:
                rec.message_post(body=_('Spare issue picking %s created.') % (picking.display_name,))

        return True
    
    def action_view_spare_picking(self):
        self.ensure_one()
        picking_ids = set(self.spare_line_ids.mapped('picking_id').ids)
        if self.spare_picking_id:
            picking_ids.add(self.spare_picking_id.id)
        if not picking_ids:
            return
        if len(picking_ids) == 1:
            return {
                'name': _('Spare Picking'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'view_mode': 'form',
                'res_id': list(picking_ids)[0],
                'target': 'current',
            }
        return {
            'name': _('Spare Pickings'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', list(picking_ids))],
            'target': 'current',
        }



class MaintenanceJobCard(models.Model):
    _name = "maintenance.jobcard"
    _description = "Maintenance Job Card"
    _order = "create_date desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Job Card", readonly=True, copy=False, default="/")
    request_id = fields.Many2one("maintenance.request", required=True, ondelete="cascade", index=True)
    equipment_id = fields.Many2one("maintenance.equipment", related="request_id.equipment_id",
                                   store=True, readonly=True)
    vehicle_id = fields.Many2one("fleet.vehicle", string="Vehicle",
                                 compute="_compute_vehicle", store=True, readonly=False)
    type = fields.Selection([("preventive", "Preventive"),
                             ("corrective", "Corrective"),
                             ("emergency", "Emergency")],
                             default="corrective", tracking=True, required=True)
    priority = fields.Selection([("0", "Low"), ("1", "Normal"), ("2", "High"), ("3", "Critical")],
                                default="1", tracking=True)
    vendor_id = fields.Many2one("res.partner", domain=[("is_company", "=", True)], tracking=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("in_progress", "In Progress"),
        ("waiting_vendor", "Waiting Vendor"),
        ("done", "Done"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    start_datetime = fields.Datetime("Start")
    end_datetime = fields.Datetime("End")
    downtime_hours = fields.Float("Downtime (hours)", compute="_compute_downtime", store=True)
    # Snapshot of equipment capacity (editable so you can override per case)
    capacity_cum_per_hr = fields.Float(
        string="Rated Capacity (cum/hr)",
        help="Snapshot from Equipment. Used to compute Production Loss.",
    )

    # Auto compute from downtime * capacity
    production_loss_cum = fields.Float(
        string="Production Loss (cum)",
        compute="_compute_production_loss",
        store=True,
    )
    loto_applied = fields.Boolean("LOTO Applied")
    loto_supervisor_id = fields.Many2one("res.users", string="LOTO Supervisor")
    loto_responsibility = fields.Selection(
        [
            ('contractor', 'Contractor Fault'),
            ('client', 'Client Responsibility'),
            ('third_party', 'Third Party'),
            ('govt', 'Government/NGT'),
        ],
        string="LOTO Responsibility",
        default='contractor',
        tracking=True,
    )
    note = fields.Text("Notes")

    # SLA
    sla_hours = fields.Float("SLA (hours)", help="Target resolution time from start.")
    is_sla_breached = fields.Boolean("SLA Breached", compute="_compute_sla_breach", store=True)

    cost_line_ids = fields.One2many("maintenance.jobcard.cost.line", "jobcard_id", string="Cost Lines")

    # Link multiple requests to a single job card (UI helper)
    request_ids = fields.Many2many(
        "maintenance.request",
        "jobcard_request_rel",
        "jobcard_id", "request_id",
        string="Maintenance Requests"
    )

    # Spare issues (One2many to spare line model)
    spare_line_ids = fields.One2many("maintenance.jobcard.spare", "jobcard_id", string="Spare Issues")
    # Link to generated spare picking for jobcard
    spare_picking_id = fields.Many2one('stock.picking', string='Spare Picking', readonly=True)
    spare_picking_count = fields.Integer('Picking Count', compute='_compute_spare_picking_count')

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id',
                                  store=True, readonly=True)
    # Count of vendor bills linked to this jobcard (via account.move.jobcard_id)
    bill_count = fields.Integer(string='Bills', compute='_compute_bill_count')

    @api.onchange('request_id')
    def _onchange_request_id_prefill(self):
        for rec in self:
            request = rec.request_id
            if not request:
                continue
            equipment = request.equipment_id
            if request.company_id:
                rec.company_id = request.company_id
            if (not rec.vendor_id and equipment and
                    'x_preferred_vendor_id' in equipment._fields and equipment.x_preferred_vendor_id):
                rec.vendor_id = equipment.x_preferred_vendor_id.id
            if (not rec.capacity_cum_per_hr and equipment and
                    'x_capacity_cum_per_hr' in equipment._fields and equipment.x_capacity_cum_per_hr):
                rec.capacity_cum_per_hr = equipment.x_capacity_cum_per_hr

    @api.constrains('loto_applied', 'loto_responsibility')
    def _check_loto_responsibility(self):
        for rec in self:
            if rec.loto_applied and not rec.loto_responsibility:
                raise ValidationError(_("Specify LOTO responsibility when LOTO is applied."))

    @api.depends('equipment_id')
    def _compute_vehicle(self):
        for rec in self:
            vid = False
            if rec.equipment_id and 'vehicle_id' in rec.equipment_id._fields:
                vid = rec.equipment_id.vehicle_id.id
            rec.vehicle_id = vid

    @api.depends('start_datetime', 'end_datetime', 'state')
    def _compute_downtime(self):
        for rec in self:
            if rec.state == 'done' and rec.start_datetime and rec.end_datetime:
                delta = fields.Datetime.to_datetime(rec.end_datetime) - fields.Datetime.to_datetime(rec.start_datetime)
                rec.downtime_hours = round(delta.total_seconds() / 3600.0, 2)
            else:
                rec.downtime_hours = 0.0

    @api.depends('sla_hours', 'state', 'start_datetime', 'end_datetime')
    def _compute_sla_breach(self):
        now = fields.Datetime.now()
        for rec in self:
            breached = False
            if rec.sla_hours and rec.start_datetime:
                end_dt = rec.end_datetime if rec.state == 'done' else now
                hrs = (fields.Datetime.to_datetime(end_dt) - fields.Datetime.to_datetime(rec.start_datetime)).total_seconds() / 3600.0
                breached = hrs > rec.sla_hours
            rec.is_sla_breached = bool(breached)

    @api.depends('downtime_hours', 'capacity_cum_per_hr')
    def _compute_production_loss(self):
        for rec in self:
            cap = rec.capacity_cum_per_hr or 0.0
            rec.production_loss_cum = round((rec.downtime_hours or 0.0) * cap, 2)

    def _compute_bill_count(self):
        for rec in self:
            rec.bill_count = self.env['account.move'].search_count([('jobcard_id', '=', rec.id)])

    @api.depends('spare_picking_id')
    def _compute_spare_picking_count(self):
        for rec in self:
            rec.spare_picking_count = 1 if rec.spare_picking_id else 0

    def action_create_spare_picking_jc(self):
        """Create an internal picking for spare parts from this Job Card.
        Uses or creates a picking type named 'Maintenance Spare part Issue'.
        Links each created move to the picking and records picking_id on spare lines.
        """
        self.ensure_one()
        Picking = self.env['stock.picking']
        PickingType = self.env['stock.picking.type']
        Move = self.env['stock.move']

        # find or create picking type
        company = self.company_id or self.env.company
        ptype = PickingType.search([
            ('name', '=', 'Maintenance Spare part Issue'),
            ('code', '=', 'internal'),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        # compute internal source/dest locations: prefer the request helper if available
        if hasattr(self, 'request_id') and self.request_id and hasattr(self.request_id, '_get_internal_locations'):
            src, dst = self.request_id._get_internal_locations(company)
        else:
            # fallback: search or create Maintenance location like in MaintenanceRequest
            Location = self.env['stock.location']
            src = Location.search([('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])], limit=1)
            dst = Location.search([('name', '=', 'Maintenance'), ('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])], limit=1)
            if not dst:
                dst = Location.create({'name': 'Maintenance', 'usage': 'internal', 'company_id': company.id})
        if not ptype:
            ptype = PickingType.create({
                'name': 'Maintenance Spare part Issue',
                'code': 'internal',
                'sequence_code': 'SPARE_ISSUE',
                'default_location_src_id': src.id if src else False,
                'default_location_dest_id': dst.id if dst else False,
                'company_id': company.id,
            })
        else:
            if not ptype.sequence_code:
                try:
                    ptype.sequence_code = 'SPARE_ISSUE'
                except Exception:
                    pass

        picking_vals = {
            'picking_type_id': ptype.id,
            'location_id': ptype.default_location_src_id.id if ptype.default_location_src_id else (src.id if src else False),
            'location_dest_id': ptype.default_location_dest_id.id if ptype.default_location_dest_id else (dst.id if dst else False),
            'origin': _('Job Card %s') % (self.name or self.id),
            'partner_id': self.vendor_id.id if 'vendor_id' in self._fields and self.vendor_id else False,
            'company_id': company.id,
        }
        picking = Picking.create(picking_vals)

        # create moves from spare lines and link each line
        for line in self.spare_line_ids:
            if not line.product_id or line.qty <= 0:
                continue
            mv = Move.create({
                'description_picking_manual': line.description or line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.uom_id.id if line.uom_id else line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
                'company_id': picking.company_id.id,
            })
            try:
                line.picking_id = picking.id
            except Exception:
                # ignore if write not permitted for some users
                pass

        self.spare_picking_id = picking.id
        self.message_post(body=_('Spare issue picking %s created from Job Card.') % (picking.name or picking.id,))
        return True

    def action_view_spare_picking_jc(self):
        self.ensure_one()
        if not self.spare_picking_id:
            return
        return {
            'name': _('Spare Picking'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.spare_picking_id.id,
            'target': 'current',
        }

    @api.constrains('state', 'type', 'loto_applied')
    def _check_loto_before_done(self):
        for rec in self:
            if rec.state == 'done' and rec.type in ('corrective', 'emergency') and not rec.loto_applied:
                raise ValidationError(_("LOTO must be applied before closing corrective/emergency Job Cards."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('maintenance.jobcard') or '/'
            # if capacity not provided, pull from equipment (via request)
            eq = None
            if not vals.get('capacity_cum_per_hr') and vals.get('request_id'):
                req = self.env['maintenance.request'].browse(vals['request_id'])
                eq = req.equipment_id
                if req.company_id and not vals.get('company_id'):
                    vals['company_id'] = req.company_id.id
            if eq and ('x_capacity_cum_per_hr' in eq._fields) and eq.x_capacity_cum_per_hr:
                vals.setdefault('capacity_cum_per_hr', eq.x_capacity_cum_per_hr)
            if eq and ('x_preferred_vendor_id' in eq._fields) and eq.x_preferred_vendor_id and not vals.get('vendor_id'):
                vals['vendor_id'] = eq.x_preferred_vendor_id.id
        return super().create(vals_list)

    def write(self, vals):
        # Prevent changing the request_id after creation, but allow harmless writes
        # that set the same request or set it when it's currently empty.
        if 'request_id' in vals:
            new_req = vals.get('request_id')
            # vals may contain falsy values; normalize to id if tuple/list not expected here
            for rec in self:
                # if record already has a request and the new value is different -> forbid
                if rec.request_id and new_req and rec.request_id.id != new_req:
                    raise ValidationError(_("Cannot change the Maintenance Request of a Job Card."))
        res = super(MaintenanceJobCard, self).write(vals)
        # also when user links a different request later, update snapshot (optional)
        for rec in self:
            if 'request_id' in vals and rec.request_id and rec.request_id.equipment_id:
                eq = rec.request_id.equipment_id
                if ('x_capacity_cum_per_hr' in eq._fields) and eq.x_capacity_cum_per_hr and not rec.capacity_cum_per_hr:
                    rec.capacity_cum_per_hr = eq.x_capacity_cum_per_hr
                if ('x_preferred_vendor_id' in eq._fields) and eq.x_preferred_vendor_id and not rec.vendor_id:
                    rec.vendor_id = eq.x_preferred_vendor_id.id
            if 'request_id' in vals and rec.request_id and rec.request_id.company_id:
                rec.company_id = rec.request_id.company_id
        return res

    # ---------- Header buttons ----------
    def action_start(self):
        for rec in self.filtered(lambda r: r.state == 'draft'):
            if not rec.start_datetime:
                rec.start_datetime = fields.Datetime.now()
            rec.state = 'in_progress'
        return True

    def action_waiting_vendor(self):
        for rec in self.filtered(lambda r: r.state == 'in_progress'):
            rec.state = 'waiting_vendor'
        return True

    # ---------------- SOP HARD-GATE HELPERS ----------------
    def _spx_labour_employees(self):
        """Return employees referenced by labour cost lines on this job card."""
        return self.cost_line_ids.filtered(
            lambda l: l.line_type == 'labour' and l.employee_id
        ).mapped('employee_id')

    def _spx_has_sop_models(self):
        """Return name of a present SOP-like model, or False."""
        for name in ['asset.sop.assignment', 'asset.sop.ack', 'sop.assignment', 'asset.sop.protocol.ack']:
            if name in self.env:
                return name
        return False

    def _spx_employees_missing_sop(self):
        """
        Return hr.employee recordset of employees missing SOP acknowledgement
        for this job card's equipment. If no SOP module or no labour employees,
        return empty recordset.
        """
        model_name = self._spx_has_sop_models()
        if not model_name:
            return self.env['hr.employee']  # no SOP app => no gate

        employees = self._spx_labour_employees()
        if not employees:
            return self.env['hr.employee']  # no labour on card => no gate

        Ack = self.env[model_name].sudo()
        eq = self.equipment_id
        missing = self.env['hr.employee']

        for emp in employees:
            dom = [('employee_id', '=', emp.id)]
            if 'equipment_id' in Ack._fields and eq:
                dom.append(('equipment_id', '=', eq.id))
            elif 'asset_id' in Ack._fields and eq:
                dom.append(('asset_id', '=', eq.id))
            if 'state' in Ack._fields:
                dom.append(('state', 'in', ['ack', 'acknowledged', 'done']))
            rec = Ack.search(dom, limit=1)
            if not rec:
                missing |= emp
        return missing

    def action_done(self):
        for rec in self:
            # check labour employees
            labour_emps = rec.cost_line_ids.filtered(
                lambda l: l.line_type == 'labour' and l.employee_id
            ).mapped('employee_id')

            if labour_emps:
                sop_model = False
                for name in ['asset.sop.assignment', 'asset.sop.ack', 'sop.assignment', 'asset.sop.protocol.ack']:
                    if name in self.env:
                        sop_model = self.env[name]
                        break

                if not sop_model:
                    raise ValidationError(_("SOP module not installed. Cannot mark Done."))

                missing = self.env['hr.employee']
                for emp in labour_emps:
                    dom = [('employee_id', '=', emp.id)]
                    # if equipment/asset field present, filter on it
                    if 'equipment_id' in sop_model._fields and rec.equipment_id:
                        dom.append(('equipment_id', '=', rec.equipment_id.id))
                    if 'asset_id' in sop_model._fields and rec.equipment_id:
                        dom.append(('asset_id', '=', rec.equipment_id.id))
                    if 'state' in sop_model._fields:
                        dom.append(('state', 'in', ['ack','acknowledged','done']))
                    ack = sop_model.search(dom, limit=1)
                    if not ack:
                        missing |= emp

                if missing:
                    raise ValidationError(
                        _("SOP Hard Gate: Cannot mark Done.\nEmployees missing SOP ack: %s") % ", ".join(missing.mapped('name'))
                    )

        # agar sab ok hai, mark selected job cards done (no parent action to call)
        for rec in self.filtered(lambda r: r.state in ('in_progress', 'waiting_vendor', 'draft')):
            if not rec.end_datetime:
                rec.end_datetime = fields.Datetime.now()
            rec.state = 'done'
        return True

    def action_cancel(self):
        for rec in self.filtered(lambda r: r.state != 'done'):
            rec.state = 'cancel'
        return True

    def action_view_vendor_bills(self):
        self.ensure_one()
        domain = [('jobcard_id', '=', self.id), ('move_type', '=', 'in_invoice')]
        return {
            'name': _('Vendor Bills'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            # use 'list' (current client view type) instead of 'tree'
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'default_jobcard_id': self.id},
        }

    # block unlink when done (audit)
    def unlink(self):
        if any(rec.state == 'done' for rec in self):
            raise ValidationError(_("Done Job Cards cannot be deleted."))
        return super().unlink()

class MaintenanceJobCardCostLine(models.Model):
    _name = "maintenance.jobcard.cost.line"
    _description = "Job Card Cost Line"

    jobcard_id = fields.Many2one("maintenance.jobcard", required=True, ondelete="cascade")
    line_type = fields.Selection([
        ("store_issue", "Store Issue"),
        ("vendor", "Vendor"),
        ("labour", "Labour"),
    ], string="Line Type", required=True, default="store_issue")

    # --- Labour specific fields ---
    employee_id = fields.Many2one(
        "hr.employee", string="Employee",
        domain="[('company_id','=',company_id)]"
    )
    timesheet_hours = fields.Float(string="Hours")

    # common
    product_id = fields.Many2one("product.product", string="Product/Service")
    description = fields.Char(string="Description")
    qty = fields.Float(string="Qty", default=1.0)
    uom_id = fields.Many2one("uom.uom", string="UoM")
    unit_cost = fields.Float(string="Unit Cost")
    amount_total = fields.Float(string="Amount", compute="_compute_amount", store=True)
    vendor_bill_id = fields.Many2one("account.move", string="Vendor Bill")
    company_id = fields.Many2one(related="jobcard_id.company_id", store=True, readonly=True)

    @api.depends('qty', 'unit_cost', 'line_type', 'timesheet_hours')
    def _compute_amount(self):
        for rec in self:
            if rec.line_type == 'labour':
                rec.amount_total = (rec.timesheet_hours or 0.0) * (rec.unit_cost or 0.0)
            else:
                rec.amount_total = (rec.qty or 0.0) * (rec.unit_cost or 0.0)

    @api.constrains('line_type', 'employee_id', 'timesheet_hours', 'product_id', 'vendor_bill_id')
    def _check_line_type_rules(self):
        for rec in self:
            if rec.line_type == 'labour':
                if not rec.employee_id:
                    raise ValidationError(_("Please select Employee on Labour line."))
                if rec.timesheet_hours <= 0:
                    raise ValidationError(_("Hours must be > 0 on Labour line."))
                if rec.vendor_bill_id:
                    raise ValidationError(_("Labour line cannot be linked to a Vendor Bill."))
            if rec.line_type == 'store_issue' and not rec.product_id:
                raise ValidationError(_("Store Issue lines must have a Product."))
            # vendor: product optional; allowed

    @api.onchange('line_type')
    def _onchange_line_type_reset(self):
        for rec in self:
            if rec.line_type != 'labour':
                rec.employee_id = False
                rec.timesheet_hours = 0.0
            if rec.line_type != 'vendor':
                rec.vendor_bill_id = False
