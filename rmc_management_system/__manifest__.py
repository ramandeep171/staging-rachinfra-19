{
    'name': 'RMC Management System',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Complete Ready-Mix Concrete Management System',
    'description': """
        Comprehensive RMC Management System for RACH INFRA PVT. LTD.

        Features:
        - Order Management with Customer Cement Options
        - Subcontractor Management and Assignment
        - Quality Control and Batch Tracking
        - Weighbridge Integration
        - Consolidated Reporting
        - Ticket Management System
        - Workorder Management
        - Material Balance Tracking
    """,
    'author': 'RACH INFRA PVT. LTD.',
    'website': 'https://rachinfra.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'base_setup',
        'sale',
        'purchase',
        'stock',
        'helpdesk',
        'crm',
        'quality',
        'quality_control',  # Added for menu_quality_root
        'fleet',
        'account',
        'project',
        'industry_fsm',
        'spx_jobcard_core',
        'product',
        'uom',
        'mrp',
        'mail',
        'portal',
        'website',
    ],
    'data': [
        # Security
        'security/rmc_security.xml',
        'security/ir.model.access.csv',
        'security/rmc_portal_security.xml',

        # Data
        'data/rmc_data.xml',
        'data/helpdesk_team_data.xml',
        'data/helpdesk_stage_data.xml',
        'data/sequence_helpdesk_regenerated.xml',
        'data/sequence_helpdesk_divert.xml',
        'data/sequence_delivery_track.xml',
        'data/rmc_plant_checks_data.xml',
        # Cube test data
        'data/sequence_cube_test.xml',
        'data/cube_test_cron.xml',
        # Reports (load early so they exist even if later views fail)
        'report/quality_cube_test_report.xml',
        'report/rmc_reporting_reports.xml',
        'report/rmc_universal_guide.xml',
        # Reporting
        'data/rmc_reporting_mail_templates.xml',
        'data/rmc_reporting_cron.xml',
        'data/rmc_reporting_server_actions.xml',
        'data/rmc_portal_cron.xml',
        'data/operator_day_report_cron.xml',

        # Views
        # Load root menu first so parent xmlid exists
        'views/rmc_root_menu.xml',
        'views/workorder_views.xml',
        'views/rmc_material_balance_views.xml',
        'views/rmc_batch_views.xml',
        'views/rmc_docket_views.xml',
        'views/rmc_docket_batches_views.xml',
        # Removed unused: recipe, weighbridge, quality views
        'views/rmc_subcontractor_views.xml',
        'views/rmc_subcontractor_extended_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/rmc_fleet_subcontractor_views.xml',
        # Cube test views
        'views/quality_cube_test_views.xml',
        'views/cube_test_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/rmc_delivery_track_views.xml',
        'views/rmc_field_service_task_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/res_partner_views.xml',
        'views/rmc_report_views.xml',
        'views/rmc_plant_check_views.xml',
        'views/rmc_truck_loading_views.xml',
        # Add Cube Tests menu also under Quality app
        'views/quality_app_menus.xml',
        'views/mrp_bom_views.xml',
        # (removed duplicate rmc_delivery_track_views.xml)
        # Load actions first, then menus that reference them
        'views/rmc_delivery_variance_views.xml',
        'views/rmc_app_menus.xml',
        'views/rmc_portal_views.xml',
        'views/rmc_menus.xml',
        'views/account_move_views.xml',
        'views/product_category_views.xml',
        'security/rmc_plant_checks_security.xml',
        'views/res_config_settings_views.xml',
        # Reports
        'views/invoice_report.xml',
        'views/portal_templates.xml',
    ],
    'post_init_hook': 'post_init',
    'demo': [
        'demo/rmc_demo.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
