def post_init(cr, registry):
    """Post-init safety net:
    - Ensure Google Maps API key config param exists (legacy behavior)
    - Ensure Workorder Completion report and its QWeb template exist
      even if the XML wasn't loaded previously due to an unrelated error.
    """
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Keep existing behavior: placeholder Google Maps key parameter
    ICP = env['ir.config_parameter'].sudo()
    if not ICP.get_param('google_maps.api_key'):
        ICP.set_param('google_maps.api_key', '')

    # Ensure QWeb template view exists with expected xmlid
    view_xmlid = 'rmc_management_system.report_workorder_completion_tmpl'
    report_xmlid = 'rmc_management_system.report_workorder_completion'

    view = env.ref(view_xmlid, raise_if_not_found=False)
    if not view:
        # Create the QWeb template view minimally
        arch = (
            '<t t-name="rmc_management_system.report_workorder_completion_tmpl">'
            '  <t t-call="web.html_container">'
            '    <t t-foreach="docs" t-as="wo">'
            '      <t t-call="web.external_layout">'
            '        <div class="page">'
            '          <h2>Workorder Completion Summary</h2>'
            '          <p>'
            '            <strong>Customer:</strong> <span t-esc="wo.partner_id.name"/>'
            '            &#160;|&#160; <strong>Sale Order:</strong> <span t-esc="wo.sale_order_id.name"/>'
            '            &#160;|&#160; <strong>Workorder:</strong> <span t-esc="wo.name"/>'
            '          </p>'
            '        </div>'
            '      </t>'
            '    </t>'
            '  </t>'
            '</t>'
        )
        view = env['ir.ui.view'].sudo().create({
            'name': 'report_workorder_completion_tmpl',
            'type': 'qweb',
            'key': 'rmc_management_system.report_workorder_completion_tmpl',
            'arch': arch,
        })
        # Register external id for the view
        env['ir.model.data'].sudo().create({
            'name': 'report_workorder_completion_tmpl',
            'module': 'rmc_management_system',
            'model': 'ir.ui.view',
            'res_id': view.id,
            'noupdate': True,
        })

    # Ensure report action exists with expected xmlid
    report = env.ref(report_xmlid, raise_if_not_found=False)
    if not report:
        report = env['ir.actions.report'].sudo().create({
            'name': 'Workorder Completion Summary',
            'model': 'dropshipping.workorder',
            'report_type': 'qweb-pdf',
            'report_name': 'rmc_management_system.report_workorder_completion_tmpl',
            'print_report_name': "'Workorder_' + (object.name or '') + '_Summary'",
        })
        env['ir.model.data'].sudo().create({
            'name': 'report_workorder_completion',
            'module': 'rmc_management_system',
            'model': 'ir.actions.report',
            'res_id': report.id,
            'noupdate': True,
        })

    return True
