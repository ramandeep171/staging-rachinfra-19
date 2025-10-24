# -*- coding: utf-8 -*-
{
    'name': 'Portal B2B Multi Category',
    'version': '19.0.1.0.0',
    'author': 'SmarterPeak',
    'summary': 'Extends customer portal with multi-category dashboards and role-based access',
    'depends': ['portal', 'sale_management', 'stock', 'account', 'rmc_management_system'],
    'data': [
        'security/ir.model.access.csv',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'portal_b2b_multicategory/static/src/js/portal_dashboard.js',
            'portal_b2b_multicategory/static/src/scss/portal_dashboard.scss',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
