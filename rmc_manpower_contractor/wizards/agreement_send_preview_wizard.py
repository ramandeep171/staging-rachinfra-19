# -*- coding: utf-8 -*-
import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AgreementSendPreviewWizard(models.TransientModel):
    _name = 'rmc.agreement.send.preview.wizard'
    _description = 'Agreement Preview Before Signature'

    agreement_id = fields.Many2one(
        'rmc.contract.agreement',
        string='Agreement',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    pdf_preview = fields.Binary(
        string='Contract Preview',
        readonly=True
    )
    pdf_filename = fields.Char(string='Filename', readonly=True)

    validity_start = fields.Date(string='Valid From')
    validity_end = fields.Date(string='Valid Until')
    mgq_target = fields.Float(string='MGQ Target (m³)')
    part_a_fixed = fields.Monetary(string='Part-A Fixed')
    part_b_variable = fields.Monetary(string='Part-B Variable')
    notes = fields.Html(string='Notes')
    currency_id = fields.Many2one(
        related='agreement_id.currency_id',
        string='Currency',
        readonly=True
    )
    sign_template_id = fields.Many2one(
        'sign.template',
        string='Sign Template'
    )

    def _prepare_agreement_values(self):
        self.ensure_one()
        return {
            'validity_start': self.validity_start,
            'validity_end': self.validity_end,
            'mgq_target': self.mgq_target,
            'part_a_fixed': self.part_a_fixed,
            'part_b_variable': self.part_b_variable,
            'notes': self.notes,
            'sign_template_id': self.sign_template_id.id if self.sign_template_id else False,
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        agreement = self.env['rmc.contract.agreement'].browse(self.env.context.get('active_id'))
        if not agreement:
            raise UserError(_('No agreement selected.'))

        agreement._ensure_sign_template()

        pdf_bytes, filename = agreement._generate_contract_pdf()
        res.update({
            'agreement_id': agreement.id,
            'validity_start': agreement.validity_start,
            'validity_end': agreement.validity_end,
            'mgq_target': agreement.mgq_target,
            'part_a_fixed': agreement.part_a_fixed,
            'part_b_variable': agreement.part_b_variable,
            'notes': agreement.notes,
            'pdf_preview': base64.b64encode(pdf_bytes).decode('utf-8'),
            'pdf_filename': filename,
            'sign_template_id': agreement.sign_template_id.id,
        })
        return res

    def _apply_changes(self):
        self.ensure_one()
        values = self._prepare_agreement_values()
        # do not reset sign template if empty; respect existing value
        if not self.sign_template_id:
            values.pop('sign_template_id', None)
        template_was_updated = 'sign_template_id' in values
        self.agreement_id.write(values)
        if template_was_updated:
            self.agreement_id._sync_signers_with_template()

    def _refresh_preview(self):
        self.ensure_one()
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.write({
            'pdf_preview': base64.b64encode(pdf_bytes).decode('utf-8'),
            'pdf_filename': filename,
        })

    def action_apply_changes(self):
        self.ensure_one()
        self._apply_changes()
        self._refresh_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_send(self):
        self.ensure_one()
        self._apply_changes()
        self.agreement_id._ensure_sign_template()
        if not self.agreement_id.sign_template_id:
            raise UserError(_('Please select a Sign Template before sending for signature.'))
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.agreement_id._refresh_sign_template(pdf_bytes, filename)
        action = self.agreement_id.action_send_for_sign()
        return action

    def action_prepare_in_sign_app(self):
        self.ensure_one()
        self._apply_changes()
        self.agreement_id._ensure_sign_template()
        if not self.agreement_id.sign_template_id:
            raise UserError(_('Please select a Sign Template before preparing the Sign request.'))
        pdf_bytes, filename = self.agreement_id._generate_contract_pdf()
        self.agreement_id._refresh_sign_template(pdf_bytes, filename)
        return self.agreement_id.action_push_to_sign_app()
