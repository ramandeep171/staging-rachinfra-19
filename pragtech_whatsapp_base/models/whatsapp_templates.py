import logging
import requests
import json
import re
from odoo import fields, models, _, api
import base64
import json
_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError

class WhatsappTemplates(models.Model):
    _name = 'whatsapp.templates'
    _description = "Template"
    _rec_name = "name"

    def _get_default(self):
        language_id = self.env['res.lang'].search([('code', '=', 'en_US')])
        return language_id.id

    name = fields.Char(string='Name')
    languages = fields.Many2one('res.lang', string='Template Languages', default=_get_default)
    category = fields.Char(string='Category')
    header = fields.Selection([('none', 'None'),('text', 'Text'), ('media_image', 'Media:Image'), ('media_document', 'Media:Document'), ('media_video', 'Media:Video'), ('location', 'Location')],
                              default="none", string='Template Header')
    body = fields.Text(string='Body')
    state = fields.Selection([('draft', 'Draft'), ('post', 'Posted')], string="State", default="draft", required=True)
    namespace = fields.Char(string='Namespace')
    sample_url = fields.Char(string="Header Url")
    sample_message = fields.Text(string="Sample Message")
    header_text = fields.Char(string="Header Text")
    template_type = fields.Selection(
        [('simple', 'Simple Template'), ('add_sign', 'Add Signature'), ('add_chatter_msg', 'Add Chater Message'), ('add_order_product_details', 'Add Product Details'),
         ('add_order_info', 'Add Order infor')], string="Template Type", default="add_sign", required=True)
    footer = fields.Text(string="Footer")
    approval_state = fields.Char(string="Approval State")
    interactive_actions = fields.Selection([('none', 'None'), ('call_to_action', 'Call To Action'), ('quick_replies', 'Quick Replies')], default='none',
                                           string='Interactive Actions')
    whatsapp_call_to_action_ids = fields.One2many('whatsapp.template.call.to.action', 'whatsapp_template_id', string='Call To Action')
    template_id = fields.Char(string='Template Id')
    provider = fields.Selection([('whatsapp_chat_api', '1msg'), ('meta', 'Meta')], string="Provider")
    default_template = fields.Boolean(string='Default Template')
    quick_reply1 = fields.Char(string='Quick Reply1')
    quick_reply2 = fields.Char(string='Quick Reply2')
    quick_reply3 = fields.Char(string='Quick Reply3')
    send_template = fields.Boolean(string='Send Template')
    model_id = fields.Many2one('ir.model', 'Applies to', help="The type of document this template can be used with")
    whatsapp_instance_id = fields.Many2one('whatsapp.instance', string='Whatsapp instance', ondelete='restrict')
    gupshup_sample_message = fields.Text(string="Gupshup Sample Message")
    gupshup_template_labels = fields.Char(string='Template Labels')

    header_attachment_ids = fields.Many2many(
        'ir.attachment', string="Static Attachment",
        copy=False)

    parameter_mapping_ids = fields.One2many('whatsapp.template.mapping', 'template_id', string="Parameter Mappings")

    button_ids = fields.One2many('whatsapp.template.button', 'template_id', string="CTA Buttons")

    status = fields.Selection([
        ('draft', 'Draft'),
        ('imported', 'Import'),
        ('exported', 'Export')], string="Status", default='draft', copy=False, tracking=True)

    @api.constrains('header_text')
    def _check_header_text_parameter(self):
        for record in self:
            if not record.header_text:
                continue

            # Find all parameters like {{1}}, {{2}}, etc.
            matches = re.findall(r'\{\{\s*(\d+)\s*\}\}', record.header_text)

            if len(matches) > 1:
                raise ValidationError("Only one parameter is allowed in Header Text, and it must be {{1}}.")

            if matches and matches[0] != '1':
                raise ValidationError("Only {{1}} is allowed as a parameter in Header Text.")

    @api.constrains('body')
    def _check_max_10_parameters_and_sequential(self):
        for record in self:
            if not record.body:
                continue

            # Extract parameters like {{1}}, {{2}}, etc.
            matches = re.findall(r'\{\{\s*(\d+)\s*\}\}', record.body)
            if not matches:
                continue

            param_numbers = sorted(set(int(num) for num in matches))

            # Check max 10
            if len(param_numbers) > 10:
                raise ValidationError("You can only use up to 10 parameters ({{1}} to {{10}}).")

            # Check sequential (no gaps)
            expected_sequence = list(range(1, len(param_numbers) + 1))
            if param_numbers != expected_sequence:
                raise ValidationError(
                    "Parameters must be sequential starting from {{1}}. "
                    f"Found: {param_numbers}, Expected: {expected_sequence}"
                )

    @api.constrains('footer')
    def _check_footer_for_parameters(self):
        for rec in self:
            if rec.footer and re.search(r'\{\{\s*\d+\s*\}\}', rec.footer):
                raise ValidationError("Footer cannot contain parameters.")

    def _prepare_parameter_mappings(self, body, header_text=None):
        """Extract parameters from header_text and body, return One2many command list"""
        mappings = []
        existing_mappings = {}

        if self.id:
            for mapping in self.parameter_mapping_ids:
                param_num = re.search(r'\{\{\s*(\d+)\s*\}\}', mapping.parameter_name)
                if param_num:
                    key = (mapping.line_type, param_num.group(1))
                    existing_mappings[key] = mapping

        # Handle header_text parameter
        if header_text:
            header_match = re.search(r'\{\{\s*(\d+)\s*\}\}', header_text)
            if header_match:
                param = header_match.group(1)
                key = ('header', param)
                mapping_vals = {
                    'parameter_name': f'Header_{{{{{param}}}}}',
                    'sequence': 1,
                    'sample_value': f'Sample for header parameter {param}',
                    'line_type': 'header',
                }
                if key in existing_mappings:
                    existing = existing_mappings[key]
                    for field in ['field_id', 'sample_value', 'final_path']:
                        value = getattr(existing, field)
                        if value:
                            if field == 'field_id':
                                mapping_vals[f'{field}'] = value.id
                            else:
                                mapping_vals[field] = value
                mappings.append((0, 0, mapping_vals))

        # Handle body parameters
        if body:
            matches = re.findall(r'\{\{\s*(\d+)\s*\}\}', body)
            unique_params = sorted(set(matches), key=lambda x: int(x))

            for seq, param in enumerate(unique_params, start=1):
                key = ('body', param)
                mapping_vals = {
                    'parameter_name': f'Body_{{{{{param}}}}}',
                    'sequence': seq,
                    'sample_value': f'Sample for body parameter {param}',
                    'line_type': 'body',
                }

                if key in existing_mappings:
                    existing = existing_mappings[key]
                    for field in ['field_id', 'sample_value', 'final_path']:
                        value = getattr(existing, field)
                        if value:
                            if field == 'field_id':
                                mapping_vals[f'{field}'] = value.id
                            else:
                                mapping_vals[field] = value

                mappings.append((0, 0, mapping_vals))

        return [(5, 0, 0)] + mappings if mappings else [(5, 0, 0)]

    @api.onchange('header')
    def _onchange_header(self):
        media_headers = ['media_image', 'media_video', 'media_document', 'location']
        if self.header in media_headers:
            self.header_text = False

    # @api.model
    # def create(self, vals):
    #     if 'name' in vals and vals['name']:
    #         vals['name'] = vals['name'].strip().lower().replace(' ', '_')
    #     record = super(WhatsappTemplates, self).create(vals)
    #     mappings = record._prepare_parameter_mappings(vals.get('body'), vals.get('header_text'))
    #     record.with_context(skip_body_check=True).parameter_mapping_ids = mappings
    #     return record

    @api.model
    def create(self, vals):
        # If creating multiple records at once
        if isinstance(vals, list):
            records = self.browse()
            for val in vals:
                if 'name' in val and val['name']:
                    val['name'] = val['name'].strip().lower().replace(' ', '_')
                record = super(WhatsappTemplates, self).create(val)
                mappings = record._prepare_parameter_mappings(val.get('body'), val.get('header_text'))
                record.with_context(skip_body_check=True).parameter_mapping_ids = mappings
                records |= record
            return records

        # Single record create
        if 'name' in vals and vals['name']:
            vals['name'] = vals['name'].strip().lower().replace(' ', '_')
        record = super(WhatsappTemplates, self).create(vals)
        mappings = record._prepare_parameter_mappings(vals.get('body'), vals.get('header_text'))
        record.with_context(skip_body_check=True).parameter_mapping_ids = mappings
        return record

    def write(self, vals):
        if 'name' in vals and vals['name']:
            vals['name'] = vals['name'].strip().lower().replace(' ', '_')

        if self.env.context.get('skip_body_check'):
            return super(WhatsappTemplates, self).write(vals)

        result = super(WhatsappTemplates, self).write(vals)

        for template in self:
            header_text = vals.get('header_text', template.header_text)
            body = vals.get('body', template.body)
            mappings = template._prepare_parameter_mappings(body, header_text)
            template.with_context(skip_body_check=True).parameter_mapping_ids = mappings

        return result

    def unlink(self):
        # If template is deleted from odoo it will deleted from respective provider
        for record in self:
            if record.provider == 'whatsapp_chat_api' and record.state == 'post':
                url = record.whatsapp_instance_id.whatsapp_endpoint + '/removeTemplate?token=' + record.whatsapp_instance_id.whatsapp_token
                headers = {"Content-Type": "application/json"}
                response = requests.post(url, data=json.dumps({'name': record.name}), headers=headers)
                if response.status_code == 200 or response.status_code == 201:
                    _logger.info("\nDeleted %s template from 1msg" % str(record.name))
        return super(WhatsappTemplates, self).unlink()

    def import_template_from_chat_api(self):
        # Import templates from 1msg if name is exists in odoo then it will add its approval state & namespace
        response = requests.get(self.whatsapp_instance_id.whatsapp_endpoint + '/templates?token=' + self.whatsapp_instance_id.whatsapp_token,
                                headers={"Content-Type": "application/json"})
        if response.status_code == 200:
            for template in response.json()['templates']:
                if template['name'] == self.name:
                    self.namespace = template['namespace']
                    self.approval_state = template.get('status')
                    if template.get('status') == 'approved':
                        self.state = 'post'

    def import_template_from_gupshup(self):
        # Import templates from gupshup if name is exists in odoo then it will add its id,approval state & corresponding details
        headers = {"Content-Type": "application/x-www-form-urlencoded", "apikey": self.whatsapp_instance_id.whatsapp_gupshup_api_key}
        url = "https://api.gupshup.io/sm/api/v1/template/list/" + self.whatsapp_instance_id.whatsapp_gupshup_app_name
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            for template in response.json()['templates']:
                if template['elementName'] == self.name and self.provider == 'gupshup':
                    self.namespace = template['namespace']
                    self.approval_state = template.get('status')
                    self.template_id = template.get('id')
                    if template.get('status') == 'APPROVED':
                        self.state = 'post'

    def action_import_template(self):
        # Select provider & import templates
        if self.provider == 'whatsapp_chat_api':
            self.import_template_from_chat_api()
        elif self.provider == 'gupshup':
            self.import_template_from_gupshup()


    def action_export_template_to_chat_api(self):
        # Export template on 1msg
        template_data = {"category": self.category}
        if self.sample_message:
            if self.header == 'media_image':
                separate_content = self.sample_message.split(",")
                template_data.update({
                    "components": [
                        {
                            "example": {"header_handle": ["https://www.pragtech.co.in/pdf/whatsapp/pos_receipt.jpg"]},
                            "format": "IMAGE",
                            "type": "HEADER"
                        },
                        {
                            "example": {"body_text": [separate_content]},
                            "text": self.body,
                            "type": "BODY"
                        }
                    ],
                })

            elif self.header == 'media_video':
                separate_content = self.sample_message.split(",")
                template_data.update({
                    "components": [
                        {
                            "example": {"header_handle": ["https://www.pragtech.co.in/pdf/whatsapp/pragmatic_core_values.mp4"]},
                            "format": "VIDEO",
                            "type": "HEADER"
                        },
                        {
                            "example": {"body_text": [separate_content]},
                            "text": self.body,
                            "type": "BODY"
                        }
                    ],
                })
            elif self.header == 'media_document':
                separate_content = self.sample_message.split(",")
                template_data.update({
                    "components": [
                        {
                            "example": {"header_handle": [self.sample_url]},
                            "format": "DOCUMENT",
                            "type": "HEADER"
                        },
                        {
                            "example": {"body_text": [separate_content]},
                            "text": self.body,
                            "type": "BODY"
                        }
                    ],
                })
            elif self.header == 'text':
                if self.header_text:
                    template_data.update({
                        "components": [
                            {
                                "format": "TEXT",
                                "text": self.header_text,
                                "type": "HEADER"
                            },
                            {
                                "text": self.body,
                                "type": "BODY"
                            }
                        ],
                    })
                else:
                    template_data.update({
                        "components": [
                            {
                                "text": self.body,
                                "type": "BODY"
                            }
                        ],
                    })
        else:
            template_data.update({
                "components": [
                    {
                        "example": {"header_handle": [self.sample_url]},
                        "format": "DOCUMENT",
                        "type": "HEADER"
                    },
                    {
                        "example": {
                            "body_text": [[]]
                        },
                        "text": self.body,
                        "type": "BODY"
                    }
                ],
            })
        template_data.update({"language": self.languages.iso_code, "name": self.name})
        if self.quick_reply1:
            template_data.get('components').append({"buttons": [{'text': self.quick_reply1, 'type': 'QUICK_REPLY'}], "type": "BUTTONS"})
        if self.footer:
            template_data.get('components').append({"text": self.footer, "type": "FOOTER"})
        url = f"{self.whatsapp_instance_id.whatsapp_endpoint}{'/addTemplate'}?token={self.whatsapp_instance_id.whatsapp_token}"
        headers = {'Content-type': 'application/json'}
        add_template_response = requests.post(url, data=json.dumps(template_data), headers=headers)
        if add_template_response.status_code == 201 or add_template_response.status_code == 200:
            json_add_template_response = add_template_response.json()
            if not json_add_template_response.get('message') and not json_add_template_response.get('error'):
                _logger.info("\nAdd templates successfully in 1msg add_template_response from whatsapp templates form view %s" % str(json_add_template_response))
                self.state = "post"
                if json_add_template_response.get('status'):
                    if json_add_template_response.get('status') == 'submitted' and json_add_template_response.get('namespace'):
                        self.namespace = json_add_template_response['namespace']
                    self.approval_state = json_add_template_response['status']
            else:
                if json_add_template_response and json_add_template_response.get('message'):
                    message = str(json_add_template_response.get('message'))
                    raise UserError(_('%s') % message)
        else:
            if add_template_response.text:
                json_add_template_response = add_template_response.json()
                if json_add_template_response and json_add_template_response.get('message'):
                    raise UserError(_("'%s'", str(json_add_template_response.get('message'))))
        return True

    def action_export_template_to_gupshup(self):
        # Export template on gupshup
        return True

    def action_export_template(self):
        # Export template if template have signature then open wizard & add current instance signature else export templates
        if self.send_template:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Message',
                'res_model': 'export.template.wizard',
                'view_mode': 'form',
                'view_id': self.env['ir.model.data']._xmlid_to_res_id('pragtech_whatsapp_base.export_template_wizard_form'),
                'target': 'new',
                'nodestroy': True,
            }
        else:
            self.whatsapp_instance_id.confirm_export_template(self)

    def action_view_gupshup_template(self):
        context = dict(self.env.context)
        context['default_template_labels'] = self.gupshup_template_labels
        context['default_template_category'] = self.category
        context['default_template_type'] = self.header
        context['default_languages'] = self.languages.name
        context['default_element_name'] = self.name
        context['default_template_format'] = self.body
        context['default_interactive_actions'] = self.interactive_actions
        context['default_quick_reply1'] = self.quick_reply1
        context['default_sample_message'] = self.gupshup_sample_message
        if self.sample_url:
            context['default_add_sample_media_message'] = 'Download the document from the Sample URL and upload it to gupshup'
            context['default_sample_url'] = self.sample_url

        return {
            'type': 'ir.actions.act_window',
            'name': 'View Gupshup Template1333',
            'res_model': 'whatsapp.gupshup.templates',
            'view_mode': 'form',
            'view_id': self.env['ir.model.data']._xmlid_to_res_id('pragtech_whatsapp_base.whatsapp_gupshup_templates_wizard_form'),
            'target': 'new',
            'nodestroy': True,
            'context': context,
        }

    def action_export_template_to_meta(self):
        for template in self:
            if template.status != 'draft':
                raise UserError(_("The template '%s' is not in the Draft state.") % template.name)

            if not template.category:
                raise UserError(_("Please select a template category for '%s'.") % template.name)

            if template.provider != 'meta':
                raise UserError(_("Template '%s' can only be exported to the Meta provider.") % template.name)

            if not template.whatsapp_instance_id:
                raise UserError(_("Please select a WhatsApp instance before exporting template '%s'.") % template.name)

            if not template.whatsapp_instance_id.meta_whatsapp_business_account_id or not template.whatsapp_instance_id.whatsapp_meta_api_token:
                raise UserError(
                    _("WhatsApp Business Account ID and Access Token are required for template '%s'.") % template.name)

            # ✅ Check if body is filled
            if not template.body:
                raise UserError(_("The Body content is required for template '%s'.") % template.name)

            # ✅ Check if header is text type and header_text is empty
            if template.header == 'text' and not template.header_text:
                raise UserError(_("Header Text is required when header type is Text in template '%s'.") % template.name)

            business_account_id = template.whatsapp_instance_id.meta_whatsapp_business_account_id
            access_token = template.whatsapp_instance_id.whatsapp_meta_api_token
            api_url = f"https://graph.facebook.com/v18.0/{business_account_id}/message_templates"

            components = []

            # Header
            if template.header != 'none':
                header_component = {
                    "type": "HEADER",
                    "format": template._get_meta_header_format(),
                }

                if template.header == 'text' and template.header_text:
                    header_component["text"] = template.header_text  # ✅ REQUIRED for 'TEXT'
                    if '{{1}}' in template.header_text:
                        header_component["example"] = {
                            "header_text": [template._get_header_parameter_example()]
                        }

                elif template.header in ['media_image', 'media_video', 'media_document']:
                    if template.header_attachment_ids:
                        attachment = template.header_attachment_ids[0]
                        whatspp_instance = template.whatsapp_instance_id.id
                        # First, upload the attachment (image, video, document) to Meta
                        file_handle = template._upload_demo_document(whatspp_instance,attachment)
                        header_component["example"] = {
                            "header_handle": [file_handle]
                        }

                components.append(header_component)

            # Body
            if template.body:
                body_component = {
                    "type": "BODY",
                    "text": template.body
                }

                body_params = template._extract_parameters_from_body()
                if body_params:
                    example_values = []
                    for param in body_params:
                        mapping = template.parameter_mapping_ids.filtered(
                            lambda m: m.line_type == 'body' and m.parameter_name == f'Body_{{{{{param}}}}}'
                        )
                        example_values.append(
                            mapping.sample_value if mapping and mapping.sample_value else f"Sample for body parameter {param}"
                        )

                    if example_values:
                        body_component["example"] = {
                            "body_text": [example_values]
                        }

                components.append(body_component)

            # Footer
            if template.footer:
                components.append({
                    "type": "FOOTER",
                    "text": template.footer
                })

            # Buttons
            if template.button_ids:
                button_component = {
                    "type": "BUTTONS",
                    "buttons": []
                }

                for button in template.button_ids:
                    if button.type == 'visit_website':
                        btn = {
                            "type": "URL",
                            "text": button.text,
                            "url": button.url or ""
                        }
                        if button.url_type == 'dynamic':
                            btn["example"] = button.url or "https://example.com"
                        button_component["buttons"].append(btn)

                    elif button.type == 'call_phone':
                        button_component["buttons"].append({
                            "type": "PHONE_NUMBER",
                            "text": button.text,
                            "phone_number": button.phone_number or ""
                        })

                if button_component["buttons"]:
                    components.append(button_component)

            # Language Fallback
            language_code = (template.languages.code or 'en_US')

            payload = {
                "name": template.name,
                "category": template.category or "MARKETING",
                "language": language_code,
                "components": components
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {access_token}'
            }

            try:
                _logger.info(f"Exporting template to Meta with payload: {json.dumps(payload)}")
                response = requests.post(api_url, headers=headers, data=json.dumps(payload))
                response.raise_for_status()
                result = response.json()

                if 'id' in result:
                    template.write({
                        'template_id': result['id'],
                        'state': 'post',
                        'status': 'exported',
                        'approval_state': result['status'],
                    })
                else:
                    raise UserError(_("Failed to export template: No template ID received."))

            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response:
                    try:
                        error_data = e.response.json()
                        if 'error' in error_data and 'message' in error_data['error']:
                            error_msg = error_data['error']['message']
                    except Exception:
                        pass

                _logger.error(f"Meta WhatsApp API Error: {error_msg}")
                raise UserError(_("Failed to export template: %s") % error_msg)

    def _get_meta_header_format(self):
        """Convert Odoo header type to Meta format"""
        mapping = {
            'text': 'TEXT',
            'media_image': 'IMAGE',
            'media_document': 'DOCUMENT',
            'media_video': 'VIDEO',
            'location': 'LOCATION'
        }
        return mapping.get(self.header, 'TEXT')

    def _extract_parameters_from_body(self):
        """Extract parameter numbers from body text"""
        if not self.body:
            return []
        import re
        matches = re.findall(r'\{\{\s*(\d+)\s*\}\}', self.body)
        return sorted(set(matches), key=lambda x: int(x))

    def _get_header_parameter_example(self):
        """Get example value for header parameter"""
        header_param = self.parameter_mapping_ids.filtered(
            lambda m: m.line_type == 'header'
        )
        return header_param.sample_value if header_param and header_param.sample_value else "Header Example"

    def _upload_demo_document(self, instance, attachment):
        """
        This method uploads a media file (image, video, document) to Meta's WhatsApp API
        using the direct API call and returns a file handle that can be used in the template header.
        """
        if not attachment:
            raise UserError(_("No attachment found to upload."))

        whatsapp_instance = self.env['whatsapp.instance'].sudo().search([('id', '=', instance)])
        app_uid = whatsapp_instance.meta_whatsapp_app_id
        token = whatsapp_instance.whatsapp_meta_api_token

        # app_uid = self.wa_account_id.app_uid
        file_data = base64.b64decode(attachment.datas) if attachment.datas else None
        if not file_data:
            raise UserError(_("Attachment data is missing or corrupt."))

        # Prepare the upload API request
        upload_url = f"https://graph.facebook.com/v18.0/{app_uid}/uploads"
        params = {
            'access_token': token,
            'file_size': len(file_data),  # Attach file size
            'file_type': attachment.mimetype,  # Attach file MIME type
        }

        # Step 1: Open upload session (Initiate the upload session)
        try:
            response = requests.post(upload_url, data=params)
            response.raise_for_status()
            upload_session_data = response.json()

            upload_session_id = upload_session_data.get('id')
            if not upload_session_id:
                raise UserError(_("Failed to initiate upload session."))

            # Step 2: Upload the file content to Meta
            upload_file_url = f"https://graph.facebook.com/v18.0/{upload_session_id}/data"
            file_upload_response = requests.post(
                upload_file_url,
                params=params,
                headers={'file_offset': '0'},
                data=file_data
            )
            file_upload_response.raise_for_status()
            upload_file_data = file_upload_response.json()

            # Step 3: Extract the file handle
            file_handle = upload_file_data.get('h')
            if not file_handle:
                raise UserError(_("Failed to upload the document. Please try again."))

            return file_handle

        except requests.exceptions.RequestException as e:
            # Handle any exception and log the error
            error_msg = str(e)
            if hasattr(e, 'response') and e.response:
                try:
                    error_data = e.response.json()
                    if 'error' in error_data and 'message' in error_data['error']:
                        error_msg = error_data['error']['message']
                except Exception:
                    pass
            _logger.error(f"Meta WhatsApp API Error during file upload: {error_msg}")
            raise UserError(_("Failed to upload document: %s") % error_msg)

    @api.model
    def fetch_whatsapp_template_statuses(self):
        # Fetch active WhatsApp instances
        instances = self.env['whatsapp.instance'].sudo().search([('status', '=', 'enable')])
        if not instances:
            _logger.warning("No active WhatsApp instance found.")
            return

        for instance in instances:
            access_token = instance.whatsapp_meta_api_token
            phone_number_id = instance.meta_whatsapp_business_account_id

            if not access_token or not phone_number_id:
                _logger.warning("Access token or phone number ID missing in WhatsApp instance: %s", instance.name)
                continue

            url = f"https://graph.facebook.com/v17.0/{phone_number_id}/message_templates"
            headers = {
                "Authorization": f"Bearer {access_token}",
            }

            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    templates = response.json().get("data", [])
                    if not templates:
                        _logger.info("No templates found for instance %s", instance.name)
                    for tpl in templates:
                        # Search for existing template based on template_id
                        existing = self.search([('template_id', '=', tpl.get('id'))], limit=1)
                        values = {
                            'name': tpl.get('name'),
                            'approval_state': tpl.get('status'),
                            'template_id': tpl.get('id'),  # Ensure template_id is also set
                        }
                        if existing:
                            # Update the existing template
                            existing.write(values)
                            _logger.info("Updated existing template: %s", tpl.get('name'))
                    _logger.info("Fetched and updated templates from Meta for instance: %s", instance.name)
                else:
                    _logger.error("Failed to fetch templates for instance %s: %s", instance.name, response.text)
            except Exception as e:
                _logger.exception("Error fetching template statuses for instance %s: %s", instance.name, e)
