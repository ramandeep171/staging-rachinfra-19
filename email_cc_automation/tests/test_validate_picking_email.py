# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

@tagged('post_install', '-at_install')
class TestValidatePickingEmailWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICPSudo = cls.env['ir.config_parameter'].sudo()
        cls.user_picker = cls.env['res.users'].create({'name': 'Picker', 'login': 'picker', 'email': 'picker@ex.com'})
        cls.user_picker.partner_id.email = 'picker_partner@ex.com'
        cls.partner_cc = cls.env['res.partner'].create({'name': 'Ship CC', 'email': 'shipcc@ex.com'})
        cls.customer = cls.env['res.partner'].create({'name': 'Ship To', 'email': 'shipto@ex.com'})
        # Minimal picking
        cls.picking = cls.env['stock.picking'].create({
            'partner_id': cls.customer.id,
            'picking_type_id': cls.env.ref('stock.picking_type_out').id,
            'user_id': cls.user_picker.id,
        })

    def test_validate_picking_default_cc_from_settings(self):
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '1')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', str(self.partner_cc.id))
        wiz = self.env['validate.picking.email.wizard'].with_context(default_picking_id=self.picking.id).create({})
        self.assertEqual(wiz.cc_partner_ids.ids, [self.partner_cc.id])

    def test_validate_picking_fallback_user_and_existing_cc(self):
        self.ICPSudo.set_param('email_cc_automation.enable_custom_partner', '0')
        self.ICPSudo.set_param('email_cc_automation.custom_partner_ids', '')
        # Store some next CC on picking already
        extra = self.env['res.partner'].create({'name': 'Extra', 'email': 'extra@ex.com'})
        self.picking.next_cc_partner_ids = [(6, 0, [extra.id])]
        wiz = self.env['validate.picking.email.wizard'].with_context(default_picking_id=self.picking.id).create({})
        self.assertEqual(set(wiz.cc_partner_ids.ids), {extra.id, self.user_picker.partner_id.id})

    def test_action_save_cc_persists_on_picking(self):
        wiz = self.env['validate.picking.email.wizard'].with_context(default_picking_id=self.picking.id).create({
            'cc_partner_ids': [(6, 0, [self.partner_cc.id])],
        })
        wiz.action_save_cc()
        self.assertEqual(self.picking.next_cc_partner_ids.ids, [self.partner_cc.id])
