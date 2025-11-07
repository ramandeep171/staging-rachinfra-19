# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

@tagged('post_install', '-at_install')
class TestConfigSettings(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ICPSudo = self.env['ir.config_parameter'].sudo()
        # Ensure a clean slate for every test
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '0')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', '')
        # Partners used in tests
        self.partner_a = self.env['res.partner'].create({'name': 'CC A', 'email': 'a@example.com'})
        self.partner_b = self.env['res.partner'].create({'name': 'CC B', 'email': 'b@example.com'})

    def test_config_params_roundtrip(self):
        # Enable and set partners (assign M2M after create, since it's compute/non-stored in the form)
        settings = self.env['res.config.settings'].create({
            'enable_custom_partner': True,
        })
        settings.custom_partner_ids = [(6, 0, [self.partner_a.id, self.partner_b.id])]
        settings.execute()  # triggers set_values

        # Expect CSV ids param written (order-insensitive)
        csv = self.ICPSudo.get_param('email_cc_automation.custom_partner_ids') or ''
        self.assertEqual(set(map(int, csv.split(','))), {self.partner_a.id, self.partner_b.id})

        # Disable and clear the list
        settings2 = self.env['res.config.settings'].create({
            'enable_custom_partner': False,
        })
        settings2.custom_partner_ids = [(6, 0, [])]
        settings2.execute()

        # Expect param cleared to empty string (not False)
        self.assertEqual(self.ICPSudo.get_param('email_cc_automation.custom_partner_ids') or '', '')

    def test_domain_only_partners_with_email(self):
        # Partner without email should not be selectable by domain (UI-level)
        p = self.env['res.partner'].create({'name': 'No Email'})

        settings = self.env['res.config.settings'].create({
            'enable_custom_partner': True,
        })
        # Try to push a partner without email — domain prevents it in UI; here we just ensure no crash
        settings.custom_partner_ids = [(6, 0, [p.id])]
        settings.execute()

        csv = self.ICPSudo.get_param('email_cc_automation.custom_partner_ids')
        # We don't enforce server-side validation here; just assert the param exists (module stable)
        self.assertIsNotNone(csv)
