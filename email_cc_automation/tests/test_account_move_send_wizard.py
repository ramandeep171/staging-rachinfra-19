# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged
from odoo import fields

@tagged('post_install', '-at_install')
class TestAccountMoveSendWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICPSudo = cls.env['ir.config_parameter'].sudo()
        # keep config clean for deterministic behavior
        cls.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '0')
        cls.ICPSudo.set_param('email_cc_automation.custom_partner_ids', '')

        # CC partner
        cls.partner_cc = cls.env['res.partner'].create({'name': 'CC', 'email': 'cc@example.com'})

        # Invoicer user (fallback rule 2)
        cls.user_invoicer = cls.env['res.users'].create({
            'name': 'Invoicer',
            'login': 'invoicer',
            'email': 'inv@example.com',
        })
        cls.user_invoicer.partner_id.email = 'inv_user@example.com'

        # Customer + product (needed to post invoice)
        cls.partner_customer = cls.env['res.partner'].create({'name': 'Customer', 'email': 'cust@example.com'})
        cls.product = cls.env['product.product'].create({'name': 'Test Product', 'lst_price': 1.0})

        # Create minimal invoice and POST it (wizard requires posted move)
        cls.move = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner_customer.id,
            'invoice_date': fields.Date.today(),
            'invoice_user_id': cls.user_invoicer.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': cls.product.id,
                'quantity': 1.0,
                'price_unit': 1.0,
                'name': 'Line',
            })],
        })
        cls.move.action_post()

    def test_default_get_cc_from_settings(self):
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '1')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', str(self.partner_cc.id))
        wiz = self.env['account.move.send.wizard'].with_context(
            # Odoo 18 default_get expects active_ids
            active_ids=[self.move.id]
        ).create({})
        # Should inject settings partners as cc_email_partner_ids (rule 1)
        self.assertEqual(wiz.cc_email_partner_ids.ids, [self.partner_cc.id])
        # _get_sending_settings should carry IDs
        s = wiz._get_sending_settings()
        self.assertEqual(s.get('cc_email_partner_ids'), [self.partner_cc.id])

    def test_default_get_cc_fallback_invoice_user(self):
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '0')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', '')
        wiz = self.env['account.move.send.wizard'].with_context(
            active_ids=[self.move.id]
        ).create({})
        # Fallback to invoice_user partner (rule 2)
        self.assertEqual(wiz.cc_email_partner_ids.ids, [self.user_invoicer.partner_id.id])

    def test__get_mail_params_injects_email_cc(self):
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '1')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', str(self.partner_cc.id))
        wiz = self.env['account.move.send.wizard'].with_context(
            active_ids=[self.move.id]
        ).create({})

        # Start from wizard settings…
        move_data = wiz._get_sending_settings() or {}
        # …and ensure core-required keys exist for Odoo 18:
        move_data.setdefault('mail_attachments_widget', [])          # avoid None iteration
        move_data.setdefault('author_partner_id', self.env.user.partner_id.id)

        # (Your extension reads cc ids from move_data)
        move_data['cc_email_partner_ids'] = [self.partner_cc.id]

        params = wiz._get_mail_params(self.move, move_data)
        self.assertIn('email_cc', params)
        self.assertEqual(params['email_cc'], 'cc@example.com')
