# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged, new_test_user
from odoo.tests import Form


@tagged('post_install', '-at_install')
class TestMailCompose(TransactionCase):

    def setUp(self):
        super().setUp()
        self.icp = self.env['ir.config_parameter'].sudo()
        self.cc1 = self.env['res.partner'].create({'name': 'CC1', 'email': 'cc1@ex.com'})
        self.cc2 = self.env['res.partner'].create({'name': 'CC2', 'email': 'cc2@ex.com'})
        self.sales_user = new_test_user(self.env, login='sales', groups='base.group_user')
        self.sales_user.partner_id.email = 'sales_partner@ex.com'
        self.customer = self.env['res.partner'].create({'name': 'Cust', 'email': 'c@ex.com'})
        self.order = self.env['sale.order'].create({'partner_id': self.customer.id, 'user_id': self.sales_user.id})

    def test_default_cc_from_settings(self):
        self.icp.set_param('email_cc_automation.enable_custom_partner', 'true')
        self.icp.set_param('email_cc_automation.custom_partner_ids', f"{self.cc1.id},{self.cc2.id}")
        wiz = self.env['mail.compose.message'].with_context(
            default_model='sale.order',
            default_res_ids=[self.order.id],
        ).create({})
        self.assertEqual(set(wiz.cc_email_partner_ids.ids), {self.cc1.id, self.cc2.id})

    def test_fallback_salesperson_when_disabled(self):
        self.icp.set_param('email_cc_automation.enable_custom_partner', '0')
        self.icp.set_param('email_cc_automation.custom_partner_ids', '')
        wiz = self.env['mail.compose.message'].with_context(
            default_model='sale.order',
            default_res_ids=[self.order.id],
        ).create({})
        self.assertEqual(wiz.cc_email_partner_ids.ids, [self.sales_user.partner_id.id])

    def test_prepare_mail_values_renders_email_cc_bcc(self):
        wiz = self.env['mail.compose.message'].with_context(
            default_model='sale.order',
            default_res_ids=[self.order.id],
        ).create({
            'cc_email_partner_ids': [(6, 0, [self.cc1.id, self.cc2.id])],
        })
        values = wiz._prepare_mail_values_rendered([self.order.id])
        self.assertEqual(values[self.order.id].get('email_cc'), 'cc1@ex.com,cc2@ex.com')
