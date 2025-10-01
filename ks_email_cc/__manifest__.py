{
    "name": "Email Cc and Bcc",
    "summary": "Email Cc and Bcc app allows a user to send mail in mail composer keeping partners or emails directly in Cc and Bcc.",
    "description": "Email Cc and Bcc app allows a user to send mail in mail composer keeping partners or emails directly in Cc and Bcc.",
    "author": "SP Nexgen Automind",
    "website": "https://smarterpeak.com/",
    "category": "Tools",
    "license": "LGPL-3",
    "version": "19.0.1.0.0",
    "maintainer": "SP Nexgen Automind",
    "support": "support@smarterpeak.com",
    "installable": True,
    "application": True,
    "sequence": 1,
    "depends": ["base", "web", "mail"],
    "assets": {
        "web.assets_backend": [
            "ks_email_cc/static/src/js/ks_message_inherit.js",
            "ks_email_cc/static/src/js/ks_thread_inherit.js",
            "ks_email_cc/static/src/xml/ks_templates_inherit.xml",
        ],
    },
    "data": [
        "wizard/ks_message_compose_inherit.xml",
        "views/ks_res_company_inherit.xml",
    ],
    "images": [
        "static/description/email_cc_banner.gif",
    ],
}
