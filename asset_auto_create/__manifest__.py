# -*- coding: utf-8 -*-
{
    'name': 'Asset Auto Create',
    'version': '19.0.1.0.0',
    'summary': 'Auto-create accounting assets from posted vendor bills when opted-in.',
    'description': 'Vendor-bill-driven asset creation using the default Odoo asset engine.',
    'author': 'SP Nextgen Automation',
    'website': 'www.samarterpeak.com',
    'license': 'LGPL-3',
    'depends': ['account', 'account_asset'],
    'data': [
        'views/account_move_view.xml',
    ],
    'installable': True,
    'application': False,
}
