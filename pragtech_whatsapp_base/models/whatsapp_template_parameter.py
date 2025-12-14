from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from werkzeug.urls import url_join

class WhatsappTemplateMapping(models.Model):
    _name = 'whatsapp.template.mapping'
    _description = "WhatsApp Template Parameter Mapping"
    _order = "sequence, id"

    template_id = fields.Many2one('whatsapp.templates', string='Template', ondelete='cascade')
    parameter_name = fields.Char(string='Parameter Name', required=True)

    line_type = fields.Selection([
        ('header', 'Header'),
        ('location', 'Location'),
        ('url', 'URL'),
        ('body', 'Body')], string="Parameter location", required=True)

    field_id = fields.Many2one(
        'ir.model.fields',
        string='Field',
        domain="[('model_id', '=', parent.model_id)]",
        ondelete='cascade',
        help="Main field to use for this parameter"
    )
    related_field_id = fields.Many2one(
        'ir.model.fields',
        string='Related Field (for Relational Types)',
        domain="[('model_id.model', '=', related_model_name)]",
        help="Select a sub-field if the above field is a relational type"
    )
    sequence = fields.Integer(string='Sequence', default=10)
    sample_value = fields.Char(string='Sample Value')

    # Field type to store the type of `field_id`
    field_type = fields.Char(
        string='Field Type',
        compute='_compute_field_type',
        store=False
    )

    final_path = fields.Char(
        string='Final Path',
        compute='_compute_final_path',
        store=True,
        readonly=False
    )

    related_model_name = fields.Char(
        compute='_compute_related_model_name',
        string="Related Model Technical Name",
        store=False
    )

    @api.depends('field_id')
    def _compute_field_type(self):
        for rec in self:
            if rec.field_id:
                rec.field_type = rec.field_id.ttype
            else:
                rec.field_type = ''

    @api.depends('field_id', 'related_field_id')
    def _compute_final_path(self):
        for rec in self:
            base = rec.field_id.name if rec.field_id else ''
            suffix = '.' + rec.related_field_id.name if rec.related_field_id else ''
            rec.final_path = base + suffix if base else ''

    @api.depends('field_id')
    def _compute_related_model_name(self):
        for rec in self:
            rec.related_model_name = ''
            if rec.field_id.id and rec.field_id.ttype in ['many2one', 'one2many', 'many2many']:
                rec.related_model_name = rec.field_id.relation