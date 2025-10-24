# -*- coding: utf-8 -*-
{
    'name': 'Diesel Log',
    'version': '19.0.1.2.0',
    'category': 'Fleet',
    'license': 'LGPL-3',
    
    'depends': ['base', 'fleet', 'mail', 'stock', 'hr_attendance'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/sequence_equipment_log.xml',
        'data/mail_activity_type.xml',
        'views/diesel_log_equipment_views.xml',
        'views/diesel_log_views.xml',
        'views/diesel_log_menus.xml',
        'views/fleet_vehicle_views.xml',
        'views/hr_attendance_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'application': True,
    'installable': True,
}
