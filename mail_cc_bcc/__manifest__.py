# -*- coding: utf-8 -*-
{
    'name': 'Mail CC & BCC',
    'version': '19.0.1.0.0',
    'summary': 'Add CC and BCC functionality to Odoo emails',
    'description': """
        Mail CC & BCC Module
        ====================
        This module extends Odoo's mail functionality to support CC and BCC recipients.

        Features:
        ---------
        * Add CC (Carbon Copy) recipients to emails
        * Add BCC (Blind Carbon Copy) recipients to emails
        * CC/BCC fields available in mail composer
        * Proper email routing for CC/BCC recipients
    """,
    'category': 'Discuss',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/mail_compose_message_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
