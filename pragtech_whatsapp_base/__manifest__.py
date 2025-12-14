{
    'name': 'Whatsapp Base',
    'version': '19.0.0.0',
    'category': 'Services',
    'author': 'Pragmatic TechSoft Pvt Ltd.',
    'website': 'pragtech.co.in',
    'summary': 'whatsapp connector whatsapp integration odoo Whatsapp crm Whatsapp lead Whatsapp task Whatsapp sale order Whatsapp purchase order Whatsapp invoice Whatsapp payment reminder Whatsapp pos Whatsapp so Whatsapp point of sale whats app communication',
    'description': """
Whatsapp base is a base module that handles the authentication process for the vendor https://chat-api.com.

Customer needs to install this module first and then they can use its dependent module developed by pragmatic
    """,
    'depends': ['base_setup'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',

        'data/whatsapp_instance_sequence_data.xml',

        'wizard/export_template_wizard_view.xml',
        # 'wizard/connection_wizard.xml',
        'wizard/whatsapp_template_gupshup_wizard_view.xml',

        'views/res_users_view.xml',
        'views/res_partner_views.xml',
        'views/whatsapp_templates_view.xml',
        'views/whatsapp_instance_view.xml',
        'views/whatsapp_message_view.xml',
        'views/whatsapp_template_call_to_action_view.xml',
        'views/res_company_view.xml',

    ],

    'images': ['static/description/gif-Odoo-whatsapp-Basic-Integration.gif'],
    'live_test_url': 'https://www.pragtech.co.in/company/proposal-form.html?id=103&name=odoo-whatsapp-integration',
    'price': 0,
    'currency': 'USD',
    'license': 'OPL-1',
    'application': False,
    'auto_install': False,
    'installable': True,
    'license': 'LGPL-3',
}
