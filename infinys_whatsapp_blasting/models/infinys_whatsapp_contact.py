import logging
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

class WhatsappContact(models.Model):
    _name = 'infinys.whatsapp.contact'
    _description = 'WhatsApp Contact'
    _rec_name = 'name'
    _order = 'name asc, company_name asc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Linked Contact',
        ondelete='cascade',
        index=True,
        help='Contacts are mirrored from the base Contacts app to keep a single source of truth.',
    )

    name = fields.Char(related='partner_id.name', string='Name', readonly=False, store=True)
    full_name = fields.Char(string='Full Name', compute='_compute_full_name', store=True, readonly=True)
    title = fields.Char(string='Title')
    whatsapp_number = fields.Char(related='partner_id.phone', string='WhatsApp Number', readonly=False, store=True, index=True)
    company_name = fields.Char(related='partner_id.company_name', string='Company Name', readonly=False, store=True)
    job_position = fields.Char(related='partner_id.function', string='Job Position', readonly=False, store=True)
    description = fields.Html(related='partner_id.comment', string='Description', readonly=False, store=True)
    country_id = fields.Many2one('res.country', related='partner_id.country_id', string='Country', readonly=False, store=True)
    email = fields.Char(related='partner_id.email', string='Email', readonly=False, store=True)
    is_active = fields.Boolean(related='partner_id.active', string='Active', readonly=False, store=True)
    is_manual = fields.Boolean(string='Manual Entry', default=True, help="Indicates if this contact was added manually.")
    tags_id = fields.Many2many('res.partner.category', related='partner_id.category_id', string='Tags', readonly=False)
    last_sent_date = fields.Datetime(string='Last Sent Date', readonly=True)
    
    mailinglist_ids = fields.Many2many(
        comodel_name='infinys.whatsapp.mailinglist',
        relation='infinys_whatsapp_contact_mailinglist_rel',
        column1='contact_id',
        column2='mailinglist_id',
        string='Mailing Lists'
    )
    
    is_new_user = fields.Boolean(
        string='New User', 
        default=True,
        help="Indicates if this contact is a new user who has not been previously contacted."
    )

    total_messages_sent = fields.Integer(string='Messages Sent', default=0)
    total_received_messages = fields.Integer(string='Received Messages', default=0)
    
    incoming_message_ids = fields.One2many(
        comodel_name='infinys.whatsapp.incoming',
        inverse_name='contact_id', 
        string='Incoming Messages', 
        readonly=True
    )

    outgoing_message_ids = fields.One2many(
        comodel_name='infinys.whatsapp.sent',
        inverse_name='contact_id', 
        string='Outgoing Messages', 
        readonly=True
    )
    
    opt_out = fields.Boolean(string='Opt-Out', default=False, help="If checked, this contact will not receive any mass messages.")

    _sql_constraints = [
        ('whatsapp_number_uniq', 'unique (whatsapp_number)', "This WhatsApp number already exists!")
    ]

    @api.depends('whatsapp_number')
    def get_total_messages_sent(self):
       for record in self:
           record.total_messages_sent = 0 #self.env['infinys.whatsapp.message'].search_count([('from_contact_id', '=', record.id)])
           _logger.debug(f"Total messages sent for {record.name} ({record.whatsapp_number}): {record.total_messages_sent}")

    @api.depends('whatsapp_number')
    def get_total_received_messages(self):
       for record in self:
           record.total_received_messages = self.env['infinys.whatsapp.incoming'].search_count([('contact_id', '=', record.id)])
           _logger.debug(f"Total messages received for {record.name} ({record.whatsapp_number}): {record.total_received_messages}")

    @api.onchange('whatsapp_number')
    def _check_whatsapp_number(self):
        for record in self:
            if record.whatsapp_number:
                number_str = str(record.whatsapp_number)
                number_str = number_str.replace(" ", "").replace("-", "").replace("+", "")
                record.whatsapp_number = number_str.strip()

                record.company_name = record.company_name
                record.job_position = record.job_position
                record.description = record.description
            
    @api.depends('partner_id.name', 'title')
    def _compute_full_name(self):
        for record in self:
            base_name = record.partner_id.display_name or record.partner_id.name or record.name
            prefix = record.title or ""
            record.full_name = f"{prefix} {base_name}" if prefix and base_name else (base_name or '')

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure a partner exists for every WhatsApp contact so data stays aligned with Contacts app."""
        Partner = self.env['res.partner']
        default_country = self.env['res.country'].search([('code', '=', 'ID')], limit=1)
        for vals in vals_list:
            if not vals.get('partner_id') and not self.env.context.get('skip_partner_creation'):
                partner_vals = {
                    'name': vals.get('name') or vals.get('full_name') or _("WhatsApp Contact"),
                    'phone': vals.get('whatsapp_number'),
                    'company_name': vals.get('company_name'),
                    'function': vals.get('job_position'),
                    'comment': vals.get('description'),
                    'country_id': vals.get('country_id') or (default_country.id if default_country else False),
                    'email': vals.get('email'),
                    'category_id': vals.get('tags_id'),
                    'active': vals.get('is_active', True),
                }
                partner = Partner.with_context(skip_partner_sync=True).create(partner_vals)
                vals['partner_id'] = partner.id
        records = super().create(vals_list)
        return records

    def init(self):
        """Link legacy WhatsApp contacts to partners when upgrading."""
        contacts = self.with_context(active_test=False).search([('partner_id', '=', False)])
        if not contacts:
            return
        Partner = self.env['res.partner']
        for contact in contacts:
            partner_vals = {
                'name': contact.name or contact.full_name or _("WhatsApp Contact"),
                'mobile': contact.whatsapp_number,
                'phone': contact.whatsapp_number,
                'company_name': contact.company_name,
                'function': contact.job_position,
                'comment': contact.description,
                'country_id': contact.country_id.id,
                'email': contact.email,
                'category_id': [(6, 0, contact.tags_id.ids)],
                'active': contact.is_active,
            }
            partner = Partner.with_context(skip_partner_sync=True).create(partner_vals)
            contact.partner_id = partner.id
