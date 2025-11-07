{
    'name': 'Email CC Automation',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': "Automatically add global CC recipients to emails for Invoices, Sales, Purchases, and Stock transfers.",
    'description': """
        This module extends Odoo’s email workflow by letting administrators configure global CC recipients for key business documents.  
        It ensures important contacts are always copied on outgoing emails (Invoices, Quotations, Orders, RFQs, Shipments), with easy setup and automatic fallback rules.
    """,
    'author': 'BJIT Limited',
    'depends': [
        'base_setup',
        'mail',
        'account',
        'sale',
        'sale_management',
        'stock',
        'purchase',
    ],
    'live_test_url': 'https://email-cc.app-odoo.bjitgroup.org/app/preview',
    'data': [
        'security/ir.model.access.csv',
        'views/inherited_account_move_send_wizard_form.xml',
        'views/inherited_mail_compose_message_form.xml',
        'views/validate_picking_email_wizard.xml',
        'views/inherited_stock_picking_view.xml',
        'views/inherited_res_config_settings_views.xml',
    ],
    'images': [
        'static/description/banner.gif',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
