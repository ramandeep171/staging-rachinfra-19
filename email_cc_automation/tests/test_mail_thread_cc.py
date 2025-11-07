# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged

@tagged('post_install', '-at_install')
class TestMailThreadCC(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_doc = cls.env['res.partner'].create({
            'name': 'Doc Partner',
            'email': 'doc@example.com',
        })
        cls.partner_recipient = cls.env['res.partner'].create({
            'name': 'Recipient',
            'email': 'to@example.com',
        })
        cls.partner_cc = cls.env['res.partner'].create({
            'name': 'CC Partner',
            'email': 'cc@example.com',
        })

    def test_notify_supports_email_cc(self):
        # call message_notify on a record that inherits mail.thread (res.partner does)
        record = self.partner_doc

        # we only check that:
        #  - a message is created
        #  - a notification to the recipient exists
        #  - if mail.message has an "email_cc" field, it equals what we passed
        msg = record.message_notify(
            partner_ids=[self.partner_recipient.id],
            body="Hello world",
            subject="Notif with CC",
            email_layout_xmlid="mail.mail_notification_light",
            email_cc="cc@example.com",
            # reduce side effects in tests
            email_add_signature=False,
        )

        # 1) message was created
        self.assertTrue(msg and msg.id, "Expected a mail.message to be created")

        # 2) notification link exists to recipient (even if no mail.mail is generated)
        notif_partners = msg.notification_ids.mapped('res_partner_id')
        self.assertIn(
            self.partner_recipient,
            notif_partners,
            "Expected a mail.notification to be created for the recipient",
        )

        # 3) only assert email_cc if that field exists on this Odoo build
        if 'email_cc' in msg._fields:
            self.assertEqual(
                msg.email_cc, "cc@example.com",
                "Expected email_cc to be stored on the message"
            )
        if msg.mail_ids:
            self.assertTrue(
                all(mail.email_cc == "cc@example.com" for mail in msg.mail_ids),
                "Outgoing emails should carry the provided CC recipients",
            )
