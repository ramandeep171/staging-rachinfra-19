# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

# ---------- MASTER: TEMPLATE ----------
class SpxChecklistTemplate(models.Model):
    _name = 'spx.checklist.template'
    _description = 'Maintenance Checklist Template'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    periodicity = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('15', '15 Days'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('custom', 'Custom'),
    ], string="Periodicity", default='daily', required=True)
    # Time-based scheduling fields
    last_done_date = fields.Date(string="Last Done Date")
    next_due_date = fields.Date(compute='_compute_next_due_date', store=True)
    equipment_category_id = fields.Many2one('maintenance.equipment.category', string="Equipment Category")
    equipment_id = fields.Many2one('maintenance.equipment', string="Specific Equipment")
    active = fields.Boolean(default=True)
    item_ids = fields.One2many('spx.checklist.template.item', 'template_id', string="Items")

    # Trigger configuration
    trigger_type = fields.Selection([
        ('time', 'Time-based'),
        ('usage', 'Usage-based'),
    ], default='time', required=True, string="Trigger Type")

    # Usage-based fields
    usage_metric = fields.Selection([
        ('km', 'Kilometers'),
        ('hours', 'Running Hours'),
    ], string="Usage Metric")
    usage_interval = fields.Float(string="Repeat Every", help="e.g. 10000 km, or 250 hours")
    usage_start_at = fields.Float(string="Start At", help="First due after this meter value")
    usage_last_done = fields.Float(string="Last Done At")
    usage_next_due = fields.Float(string="Next Due At", compute="_compute_next_due", store=True)

    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle (for km)")

    _name_uniq = models.Constraint(
        'unique(name)',
        'Template name must be unique.',
    )

    # usage scheduling is computed on the template model
    @api.depends('usage_interval', 'usage_start_at', 'usage_last_done', 'trigger_type')
    def _compute_next_due(self):
        for t in self:
            if t.trigger_type != 'usage' or not t.usage_interval:
                t.usage_next_due = 0.0
            else:
                base = t.usage_last_done or t.usage_start_at or 0.0
                t.usage_next_due = base + t.usage_interval

    @api.depends('trigger_type', 'periodicity', 'last_done_date')
    def _compute_next_due_date(self):
        """Compute next due date for time-based templates."""
        for t in self:
            if t.trigger_type != 'time' or not t.periodicity:
                t.next_due_date = False
                continue
            base = t.last_done_date or fields.Date.context_today(t)
            days = {'daily': 1, 'weekly': 7, '15': 15, 'monthly': 30, 'quarterly': 90}.get(t.periodicity, 0)
            if days:
                try:
                    t.next_due_date = fields.Date.to_date(base) + relativedelta(days=days)
                except Exception:
                    t.next_due_date = base

    # --------- core: create request + checklist, then email PDF ----------
    def _spawn_preventive_request(self):
        Req = self.env['maintenance.request']
        Chk = self.env['spx.checklist']
        today = fields.Date.context_today(self)
        created = []

        for t in self:
            if not (t.equipment_id or t.vehicle_id):
                continue

            # avoid duplicate open requests for this template
            if getattr(t, 'one_open_per_template', False):
                existing = Req.search([('origin_template_id', '=', t.id), ('stage_id.done', '=', False)], limit=1)
                if existing:
                    continue

            req = Req.create({
                'name': _("%s - Preventive (%s)") % (t.name, today),
                'equipment_id': t.equipment_id.id or False,
                'maintenance_type': 'preventive',
                'priority': '1',
                'origin_template_id': t.id,
            })
            chk = Chk.create_from_template(t, req)

            # advance last_done to avoid same-day repeats
            t.last_done_date = today
            created.append((req, chk))

            # send email with checklist PDF if enabled
            if getattr(t, 'email_on_create', False):
                t._email_visit_with_pdf(req, chk)

        return created

    def _email_visit_with_pdf(self, req, chk):
        """Render Checklist PDF and email to selected partners + engineer (if set)."""
        partners = getattr(self, 'email_partner_ids', False) or self.env['res.partner']
        if getattr(self, 'engineer_id', False) and self.engineer_id and getattr(self.engineer_id, 'work_contact_id', False):
            partners |= self.engineer_id.work_contact_id

        if not partners:
            return

        report = self.env.ref('spx_jobcard_core.report_spx_checklist')
        try:
            pdf_content, _ = report._render_qweb_pdf(res_ids=[chk.id])
        except Exception:
            return
        filename = "%s_%s.pdf" % (chk.display_name or 'Checklist', fields.Date.context_today(self))

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'raw': pdf_content,
            'res_model': 'maintenance.request',
            'res_id': req.id,
            'mimetype': 'application/pdf',
        })

        mail_vals = {
            'subject': getattr(self, 'email_subject', False) or _('Maintenance Visit'),
            'body_html': getattr(self, 'email_body', False) or "<p>Please find the attached checklist.</p>",
            'email_from': self.env.user.email_formatted,
            'recipient_ids': [(6, 0, partners.ids)],
            'attachment_ids': [(4, attachment.id)],
        }
        self.env['mail.mail'].create(mail_vals).send()

    @api.model
    def cron_time_based_preventive(self):
        """Daily: time-based due templates → create request + checklist + email PDF if enabled."""
        today = fields.Date.context_today(self)
        to_run = self.search([
            ('active', '=', True),
            ('trigger_type', '=', 'time'),
            ('next_due_date', '!=', False),
            ('next_due_date', '<=', today),
        ])
        to_run._spawn_preventive_request()


class SpxChecklistTemplateItem(models.Model):
    _name = 'spx.checklist.template.item'
    _description = 'Checklist Template Item'
    _order = 'sequence, id'

    template_id = fields.Many2one('spx.checklist.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    required = fields.Boolean(string="Required", default=True)
    need_photo = fields.Boolean(string="Need Photo")
    notes_help = fields.Char(string="Operator Hint", translate=True)


# ---------- TRANSACTION: FILLED CHECKLIST ----------
class SpxChecklist(models.Model):
    _name = 'spx.checklist'
    _description = 'Filled Maintenance Checklist'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    display_name = fields.Char(compute='_compute_display_name', store=False)
    template_id = fields.Many2one('spx.checklist.template', required=True, ondelete='restrict')
    request_id = fields.Many2one('maintenance.request', string="Maintenance Request")
    jobcard_id = fields.Many2one('maintenance.jobcard', string="Job Card")
    equipment_id = fields.Many2one('maintenance.equipment', required=True)
    periodicity = fields.Selection(related='template_id.periodicity', store=False)
    line_ids = fields.One2many('spx.checklist.line', 'checklist_id', string="Lines")
    passed = fields.Boolean(string="All Passed?", compute='_compute_passed', store=True)
    remarks = fields.Text()

    @api.depends('template_id', 'equipment_id', 'request_id', 'jobcard_id')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.template_id.name or _('Checklist')]
            if rec.equipment_id:
                parts.append(rec.equipment_id.display_name)
            if rec.jobcard_id:
                parts.append(_('JC %s') % (rec.jobcard_id.name,))
            elif rec.request_id:
                parts.append(_('REQ %s') % (rec.request_id.name,))
            rec.display_name = " - ".join(parts)

    @api.depends('line_ids.state')
    def _compute_passed(self):
        for rec in self:
            # pass only if all required lines are 'ok'
            required = rec.line_ids.filtered(lambda l: l.required)
            rec.passed = bool(required and all(l.state == 'ok' for l in required))

    @api.model
    def create_from_template(self, template, target):
        """Utility to spawn a checklist from template onto a target (request or jobcard)."""
        if not template or not target:
            raise ValidationError(_("Checklist spawn: missing template or target."))
        vals = {
            'template_id': template.id,
            'equipment_id': getattr(target, 'equipment_id', False) and target.equipment_id.id or False,
        }
        # link to request/jobcard
        if target._name == 'maintenance.request':
            vals['request_id'] = target.id
        elif target._name == 'maintenance.jobcard':
            vals['jobcard_id'] = target.id

        # create parent
        chk = self.create(vals)
        # create lines
        lines = []
        for it in template.item_ids:
            lines.append((0, 0, {
                'sequence': it.sequence,
                'name': it.name,
                'required': it.required,
                'need_photo': it.need_photo,
                'notes_help': it.notes_help,
            }))
        chk.write({'line_ids': lines})
        return chk


    # (usage scheduling compute moved to the template class)


class SpxChecklistLine(models.Model):
    _name = 'spx.checklist.line'
    _description = 'Checklist Line'
    _order = 'sequence, id'

    checklist_id = fields.Many2one('spx.checklist', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    required = fields.Boolean(default=True)
    need_photo = fields.Boolean()
    state = fields.Selection([
        ('ok', 'OK'),
        ('fail', 'Fail'),
        ('na', 'N/A'),
    ], string="Result")
    photo = fields.Binary(string="Photo")
    notes = fields.Char(string="Remarks")
    notes_help = fields.Char(string="Hint")

    @api.constrains('state', 'required', 'need_photo', 'photo')
    def _check_required_rules(self):
        for rec in self:
            if rec.required and rec.state != 'ok':
                # allow saving, block validation at Done on Job Card/Request
                pass
            if rec.need_photo and rec.state == 'fail' and not rec.photo:
                raise ValidationError(_("Photo is required when item fails."))


# ---------- WIZARD: APPLY TEMPLATE ----------
class SpxChecklistApplyWizard(models.TransientModel):
    _name = 'spx.checklist.apply.wizard'
    _description = 'Apply Checklist Template'

    template_id = fields.Many2one('spx.checklist.template', string='Template', required=True)

    def action_apply(self):
        """Apply selected template to the target in context: either request_id or jobcard_id."""
        self.ensure_one()
        env = self.env
        template = self.template_id
        # Determine target from context
        if self._context.get('request_id'):
            target = env['maintenance.request'].browse(self._context['request_id'])
        elif self._context.get('jobcard_id'):
            target = env['maintenance.jobcard'].browse(self._context['jobcard_id'])
        else:
            raise ValidationError(_("No target found to apply the template."))
        return env['spx.checklist'].create_from_template(template, target)
