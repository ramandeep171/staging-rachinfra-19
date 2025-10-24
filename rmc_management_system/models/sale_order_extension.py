from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
from datetime import timedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ----------------------------
    # RMC fields
    # ----------------------------
    cube_test_condition = fields.Selection([
        ('every_truck', 'Every Truck / Docket / Ticket'),
        ('workorder', 'Workorder Wise'),
        ('every_six', 'Every 6 Docket / Ticket'),
    ], string='Cube Test Condition', default='workorder')
    cube_tests_count = fields.Integer(compute='_compute_cube_tests_count')
    cube_test_user_id = fields.Many2one('res.users', string='Cube Test Assignee')
    cube_test_notes = fields.Text(string='Cube Test Notes')

    is_rmc_order = fields.Boolean(string='RMC Order', compute='_compute_is_rmc_order', store=True)
    customer_provides_cement = fields.Boolean(string='Customer Provides Cement', help='Check if the customer will provide cement for this order')
    workorder_ids = fields.One2many('dropshipping.workorder', 'sale_order_id', string='RMC Workorders')
    workorder_count = fields.Integer(string='Workorder Count', compute='_compute_workorder_count', store=True)

    # ----------------------------
    # Periodic reporting fields
    # ----------------------------
    reporting_enabled = fields.Boolean(string='Periodic Reporting Enabled', default=False)
    reporting_period = fields.Selection([('7', '7 days'), ('15', '15 days')], string='Periodic Window', default='7')
    last_sent_30d = fields.Datetime(string='Last 30-day Summary Sent')
    last_sent_7d = fields.Datetime(string='Last 7-day Summary Sent')
    last_sent_15d = fields.Datetime(string='Last 15-day Summary Sent')

    # ----------------------------
    # Computes / helpers
    # ----------------------------
    @api.depends('order_line.product_id.categ_id.name')
    def _compute_is_rmc_order(self):
        for order in self:
            is_rmc = False
            for line in order.order_line:
                if line.product_id and line.product_id.categ_id:
                    category_name = line.product_id.categ_id.name or ''
                    if 'RMC' in category_name.upper() or 'CONCRETE' in category_name.upper():
                        is_rmc = True
                        break
            order.is_rmc_order = is_rmc

    @api.depends('workorder_ids')
    def _compute_workorder_count(self):
        for order in self:
            order.workorder_count = len(order.workorder_ids)

    def _compute_cube_tests_count(self):
        for order in self:
            order.cube_tests_count = self.env['quality.cube.test'].search_count([('sale_order_id', '=', order.id)])

    # ----------------------------
    # Actions
    # ----------------------------
    def action_create_rmc_workorder(self):
        self.ensure_one()
        if not self.is_rmc_order:
            raise ValidationError(_('This is not an RMC order. Cannot create RMC workorder.'))
        return self._create_rmc_workorder()

    def action_view_workorders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'RMC Workorders',
            'res_model': 'dropshipping.workorder',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }

    def action_view_cube_tests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cube Tests',
            'res_model': 'quality.cube.test',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id, 'default_test_condition': self.cube_test_condition},
        }

    def _create_rmc_workorder(self):
        self.ensure_one()
        rmc_lines = self.order_line.filtered(
            lambda line: line.product_id and line.product_id.categ_id and (
                'RMC' in (line.product_id.categ_id.name or '').upper() or
                'CONCRETE' in (line.product_id.categ_id.name or '').upper())
        )
        if not rmc_lines:
            return False
        total_qty = sum(rmc_lines.mapped('product_uom_qty'))
        main_product = rmc_lines[0].product_id
        workorder_vals = {
            'sale_order_id': self.id,
            'product_id': main_product.id,
            'quantity_ordered': total_qty,
            'total_qty': total_qty,
            'unit_price': rmc_lines[0].price_unit,
            'site_type': 'friendly',
            'state': 'draft',
            'notes': f'Auto-created from Sale Order {self.name}',
        }
        workorder_lines = []
        for line in rmc_lines:
            workorder_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'quantity_ordered': line.product_uom_qty,
                'unit_price': line.price_unit,
            }))
        workorder_vals['workorder_line_ids'] = workorder_lines
        workorder = self.env['dropshipping.workorder'].create(workorder_vals)
        if workorder:
            self._create_helpdesk_ticket_for_workorder(workorder)
        return {
            'type': 'ir.actions.act_window',
            'name': 'RMC Workorder Created',
            'res_model': 'dropshipping.workorder',
            'res_id': workorder.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_helpdesk_ticket_for_workorder(self, workorder):
        helpdesk_vals = {
            'name': f'RMC Workorder: {workorder.name}',
            'description': f'Workorder created for Sale Order {self.name}\nQuantity: {workorder.total_qty} M3\nProduct: {workorder.product_id.name}',
            'partner_id': self.partner_id.id,
            'team_id': self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping').id if self.env.ref('rmc_management_system.helpdesk_team_rmc_dropshipping', raise_if_not_found=False) else False,
            'priority': '2',
        }
        ticket = self.env['helpdesk.ticket'].create(helpdesk_vals)
        workorder.helpdesk_ticket_id = ticket.id
        return ticket

    @api.model_create_multi
    def create(self, vals_list):
        orders = super(SaleOrder, self).create(vals_list)
        for order in orders:
            order._update_material_balances()
        return orders

    def write(self, vals):
        result = super(SaleOrder, self).write(vals)
        if 'order_line' in vals:
            for order in self:
                order._update_material_balances()
        return result

    def _create_initial_workorder_tests(self):
        return True

    def _update_material_balances(self):
        for order in self:
            if order.partner_id:
                for line in order.order_line:
                    if line.product_id and line.product_id.categ_id:
                        categ_name = (line.product_id.categ_id.name or '').lower()
                        material_type = 'other'
                        if 'cement' in categ_name:
                            material_type = 'cement'
                        elif 'sand' in categ_name:
                            material_type = 'sand'
                        elif 'aggregate' in categ_name or 'gravel' in categ_name:
                            material_type = 'aggregate'
                        if not (material_type == 'cement' and order.customer_provides_cement):
                            self.env['rmc.material.balance']._update_balance(order.partner_id, material_type, line.product_uom_qty)

    # ----------------------------
    # Reporting helpers
    # ----------------------------
    def _render_sale_order_summary_pdf(self, window_days):
        self.ensure_one()
        self._ensure_sale_order_summary_report()
        env = self.env
        report = env.ref('rmc_management_system.report_sale_order_summary', raise_if_not_found=False)
        if not report:
            report = env['ir.actions.report'].sudo().search([
                ('report_name', '=', 'rmc_management_system.report_sale_order_summary_tmpl'),
                ('model', '=', 'sale.order'),
                ('report_type', '=', 'qweb-pdf')
            ], limit=1)
        if not report:
            return False, False
        conf_dt = getattr(self, 'confirmation_date', False) or self.date_order
        date_from = (conf_dt - timedelta(days=int(window_days))) if conf_dt else False
        # Render via xmlid + docids list (preferred) and also pass docid in data
        xmlid = 'rmc_management_system.report_sale_order_summary'
        data = {'window_days': window_days, 'date_from': date_from, 'docid': self.id}
        errors = []
        def _as_pdf(result):
            try:
                return result[0] if isinstance(result, tuple) else result
            except Exception:
                return None
        # Attempt 1
        try:
            res = env['ir.actions.report'].sudo()._render_qweb_pdf(xmlid, [self.id], data=data)
            pdf = _as_pdf(res)
            if pdf:
                safe_name = self.name or f"SO-{self.id}"
                fname = f"Sale_Order_{safe_name}_Summary_{window_days}d.pdf"
                return pdf, fname
            else:
                raise ValueError("empty-pdf")
        except Exception as e1:
            errors.append(f"xmlid-list-1:{e1}")
        # Attempt 2 after clearing caches (handles stale template bodies)
        try:
            self.env['ir.ui.view'].clear_caches()
        except Exception:
            pass
        try:
            res = env['ir.actions.report'].sudo()._render_qweb_pdf(xmlid, [self.id], data=data)
            pdf = _as_pdf(res)
            if pdf:
                safe_name = self.name or f"SO-{self.id}"
                fname = f"Sale_Order_{safe_name}_Summary_{window_days}d.pdf"
                return pdf, fname
            else:
                raise ValueError("empty-pdf")
        except Exception as e2:
            errors.append(f"xmlid-list-2:{e2}")
        # If both failed, log aggregated errors
        try:
            self.message_post(body="SO Summary render failed: " + " | ".join(errors))
        except Exception:
            pass
        return False, False

    def _send_sale_order_summary(self, window_days, template_xmlid):
        self.ensure_one()
        partner = self.partner_id
        if not partner or not partner.email:
            self.message_post(body=_('Skipped SO %sd summary: customer email missing.') % window_days)
            return False
        pdf, fname = self._render_sale_order_summary_pdf(window_days)
        if not pdf:
            self.message_post(body=_('Sale Order Summary PDF template not found.'))
            return False
        att = self.env['ir.attachment'].create({
            'name': fname,
            'type': 'binary',
            'datas': base64.b64encode(pdf).decode('utf-8'),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        # Render universal guide and attach as well
        guide_pdf = None
        try:
            res = self.env['ir.actions.report'].sudo()._render_qweb_pdf('rmc_management_system.report_universal_guide', [self.id])
            guide_pdf = res[0] if isinstance(res, tuple) else res
        except Exception:
            guide_pdf = None
        guide_att_id = False
        if guide_pdf:
            guide_att = self.env['ir.attachment'].create({
                'name': 'RMC_Customer_Guide.pdf',
                'type': 'binary',
                'datas': base64.b64encode(guide_pdf).decode('utf-8'),
                'mimetype': 'application/pdf',
                'res_model': self._name,
                'res_id': self.id,
            })
            guide_att_id = guide_att.id
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template:
            # send_mail creates mail.mail and posts in chatter; neutralized DB won't deliver but shows the template in chatter
            template = template.with_context(lang=partner.lang or self.env.user.lang)
            email_vals = {'attachment_ids': [(4, att.id)]}
            if guide_att_id:
                email_vals['attachment_ids'].append((4, guide_att_id))
            template.send_mail(self.id, force_send=False, email_values=email_vals)
        post_attach_ids = [att.id]
        if guide_att_id:
            post_attach_ids.append(guide_att_id)
        self.message_post(body=_('Sale Order %s-day Summary queued via template to %s') % (window_days, partner.email), attachment_ids=post_attach_ids)
        now = fields.Datetime.now()
        if int(window_days) == 30:
            self.last_sent_30d = now
        elif int(window_days) == 7:
            self.last_sent_7d = now
        elif int(window_days) == 15:
            self.last_sent_15d = now
        return True

    def _ensure_sale_order_summary_report(self):
        env = self.env
        minimal_arch = (
            '<t t-name="rmc_management_system.report_sale_order_summary_tmpl">'
            '  <t t-call="web.html_container">'
            '    <t t-set="docid" t-value="(data or {}).get(\'docid\')"/>'
            '    <t t-set="docid_int" t-value="(docid and int(docid)) or False"/>'
            '    <t t-set="window_days" t-value="(data or {}).get(\'window_days\', 30)"/>'
            '    <t t-set="so_list" t-value="docs and docs.sudo().exists() or False"/>'
            '    <t t-if="so_list">'
            '      <t t-foreach="so_list" t-as="so">'
            '        <t t-call="web.external_layout">'
            '          <div class="page">'
            '            <h2>Sale Order Summary (Last <t t-esc="window_days"/> days)</h2>'
            '            <p>'
            '              <strong>Customer:</strong> <span t-esc="so.partner_id.name"/>'
            '              &#160;|&#160; <strong>Sale Order:</strong> <span t-esc="so.name"/>'
            '              &#160;|&#160; <strong>Confirmed:</strong>'
            '              <span t-esc="(so._fields.get(\'confirmation_date\') and so.confirmation_date) or so.date_order"/>'
            '            </p>'
            '            <t t-set="date_from" t-value="(data or {}).get(\'date_from\')"/>'
            '            <t t-set="dockets" t-value="env[\'rmc.docket\'].sudo().search([(\'sale_order_id\',\'=\',so.id), (\'docket_date\',\'>=\', date_from)])"/>'
            '            <t t-set="tl_count" t-value="env[\'rmc.truck_loading\'].sudo().search_count([(\'docket_id.sale_order_id\',\'=\',so.id), (\'docket_id.docket_date\',\'>=\', date_from)])"/>'
            '            <t t-set="dv_approved" t-value="env[\'rmc.delivery_variance\'].sudo().search_count([(\'truck_loading_id.docket_id.sale_order_id\',\'=\',so.id), (\'truck_loading_id.docket_id.docket_date\',\'>=\', date_from), (\'reconciliation_status\',\'in\',[\'approved\',\'reconciled\'])])"/>'
            '            <t t-set="delivered" t-value="sum([d.quantity_produced or 0.0 for d in dockets])"/>'
            '            <p>'
            '              <strong>Delivered Volume:</strong> <t t-esc="delivered"/> m3'
            '              &#160;|&#160; <strong>Dockets:</strong> <t t-esc="len(dockets)"/>'
            '              &#160;|&#160; <strong>Truck Loadings:</strong> <t t-esc="tl_count"/>'
            '              &#160;|&#160; <strong>DV (approved/reconciled):</strong> <t t-esc="dv_approved"/>'
            '            </p>'
            '            <h3>Docket Details</h3>'
            '            <table class="table table-sm">'
            '              <thead>\n                <tr>\n                  <th>Docket</th>\n                  <th>Date</th>\n                  <th>Qty Produced</th>\n                  <th>Status</th>\n                </tr>\n              </thead>'
            '              <tbody>'
            '                <t t-foreach="dockets" t-as="d">'
            '                  <tr>'
            '                    <td t-esc="d.docket_number or \'\'"/>'
            '                    <td t-esc="d.docket_date or \'\'"/>'
            '                    <td t-esc="d.quantity_produced or 0.0"/>'
            '                    <td t-esc="d.state or \'\'"/>'
            '                  </tr>'
            '                </t>'
            '              </tbody>'
            '            </table>'
            '          </div>'
            '        </t>'
            '      </t>'
            '    </t>'
            '    <t t-elif="docid_int">'
            '      <t t-set="so" t-value="env[\'sale.order\'].sudo().browse(docid_int)"/>'
            '      <t t-if="so and so.exists()">'
            '        <t t-call="web.external_layout">'
            '          <div class="page">'
            '            <h2>Sale Order Summary (Last <t t-esc="window_days"/> days)</h2>'
            '            <p>'
            '              <strong>Customer:</strong> <span t-esc="so.partner_id.name"/>'
            '              &#160;|&#160; <strong>Sale Order:</strong> <span t-esc="so.name"/>'
            '              &#160;|&#160; <strong>Confirmed:</strong>'
            '              <span t-esc="(so._fields.get(\'confirmation_date\') and so.confirmation_date) or so.date_order"/>'
            '            </p>'
            '            <t t-set="date_from" t-value="(data or {}).get(\'date_from\')"/>'
            '            <t t-set="dockets" t-value="env[\'rmc.docket\'].sudo().search([(\'sale_order_id\',\'=\',so.id), (\'docket_date\',\'>=\', date_from)])"/>'
            '            <t t-set="tl_count" t-value="env[\'rmc.truck_loading\'].sudo().search_count([(\'docket_id.sale_order_id\',\'=\',so.id), (\'docket_id.docket_date\',\'>=\', date_from)])"/>'
            '            <t t-set="dv_approved" t-value="env[\'rmc.delivery_variance\'].sudo().search_count([(\'truck_loading_id.docket_id.sale_order_id\',\'=\',so.id), (\'truck_loading_id.docket_id.docket_date\',\'>=\', date_from), (\'reconciliation_status\',\'in\',[\'approved\',\'reconciled\'])])"/>'
            '            <t t-set="delivered" t-value="sum([d.quantity_produced or 0.0 for d in dockets])"/>'
            '            <p>'
            '              <strong>Delivered Volume:</strong> <t t-esc="delivered"/> m3'
            '              &#160;|&#160; <strong>Dockets:</strong> <t t-esc="len(dockets)"/>'
            '              &#160;|&#160; <strong>Truck Loadings:</strong> <t t-esc="tl_count"/>'
            '              &#160;|&#160; <strong>DV (approved/reconciled):</strong> <t t-esc="dv_approved"/>'
            '            </p>'
            '          </div>'
            '        </t>'
            '      </t>'
            '      <t t-else="">'
            '        <div class="page"><p>Record not found.</p></div>'
            '      </t>'
            '    </t>'
            '    <t t-else="">'
            '      <div class="page"><p>Record not found.</p></div>'
            '    </t>'
            '  </t>'
            '</t>'
        )
        # Find all views with the target key and enforce safe arch on all to avoid duplicates collisions
        views = env['ir.ui.view'].sudo().search([
            ('type', '=', 'qweb'),
            ('key', '=', 'rmc_management_system.report_sale_order_summary_tmpl'),
        ])
        if views:
            views.sudo().write({'arch_db': minimal_arch})
            tmpl = views[:1]
        else:
            tmpl = env.ref('rmc_management_system.report_sale_order_summary_tmpl', raise_if_not_found=False)
            if not tmpl:
                tmpl = env['ir.ui.view'].sudo().create({
                    'name': 'report_sale_order_summary_tmpl',
                    'type': 'qweb',
                    'key': 'rmc_management_system.report_sale_order_summary_tmpl',
                    'arch_db': minimal_arch,
                })
                imd = env['ir.model.data'].sudo().search([('module', '=', 'rmc_management_system'), ('name', '=', 'report_sale_order_summary_tmpl')], limit=1)
                if imd:
                    imd.sudo().write({'model': 'ir.ui.view', 'res_id': tmpl.id, 'noupdate': True})
                else:
                    env['ir.model.data'].sudo().create({'module': 'rmc_management_system', 'name': 'report_sale_order_summary_tmpl', 'model': 'ir.ui.view', 'res_id': tmpl.id, 'noupdate': True})
        try:
            env['ir.ui.view'].clear_caches()
        except Exception:
            pass

        report = env.ref('rmc_management_system.report_sale_order_summary', raise_if_not_found=False)
        if not report:
            report = env['ir.actions.report'].sudo().create({
                'name': 'Sale Order Summary',
                'model': 'sale.order',
                'report_type': 'qweb-pdf',
                'report_name': 'rmc_management_system.report_sale_order_summary_tmpl',
                'report_file': 'rmc_management_system.report_sale_order_summary_tmpl',
                'print_report_name': "'SO_' + (object.name or '') + '_Summary'",
            })
        imd2 = env['ir.model.data'].sudo().search([('module', '=', 'rmc_management_system'), ('name', '=', 'report_sale_order_summary')], limit=1)
        if imd2:
            imd2.sudo().write({'model': 'ir.actions.report', 'res_id': report.id, 'noupdate': True})
        else:
            env['ir.model.data'].sudo().create({'module': 'rmc_management_system', 'name': 'report_sale_order_summary', 'model': 'ir.actions.report', 'res_id': report.id, 'noupdate': True})
        rvals = {}
        if report.model != 'sale.order':
            rvals['model'] = 'sale.order'
        if report.report_type != 'qweb-pdf':
            rvals['report_type'] = 'qweb-pdf'
        if report.report_name != 'rmc_management_system.report_sale_order_summary_tmpl':
            rvals['report_name'] = 'rmc_management_system.report_sale_order_summary_tmpl'
        if report.report_file != 'rmc_management_system.report_sale_order_summary_tmpl':
            rvals['report_file'] = 'rmc_management_system.report_sale_order_summary_tmpl'
        # Clear any invalid attachment expression that could raise safe_eval errors (e.g., 'a')
        try:
            if getattr(report, 'attachment_use', False) or getattr(report, 'attachment', False):
                # Only keep a safe print_report_name; disable attachment storage
                rvals['attachment_use'] = False
                rvals['attachment'] = False
        except Exception:
            # In case fields differ by edition, ignore
            pass
        if hasattr(report, 'report_sudo') and not getattr(report, 'report_sudo'):
            rvals['report_sudo'] = True
        if rvals:
            report.sudo().write(rvals)

    # ----------------------------
    # UI actions to trigger summary
    # ----------------------------
    def _action_send_summary(self, period):
        self.ensure_one()
        period = int(period)
        tmpl = 'rmc_management_system.mail_tmpl_so_summary_7' if period == 7 \
            else 'rmc_management_system.mail_tmpl_so_summary_15' if period == 15 \
            else 'rmc_management_system.mail_tmpl_so_summary_30'
        return self._send_sale_order_summary(period, tmpl)

    def action_send_summary_7(self):
        for so in self:
            so._action_send_summary(7)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_send_summary_15(self):
        for so in self:
            so._action_send_summary(15)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_send_summary_30(self):
        for so in self:
            so._action_send_summary(30)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def test_send_summary_7(self):
        self.ensure_one()
        so = self
        so.message_post(body='TEST: starting summary send')
        try:
            ok = so.sudo()._send_sale_order_summary(7, 'rmc_management_system.mail_tmpl_so_summary_7')
            so.message_post(body=f'TEST: summary send returned {ok}')
        except Exception as e:
            so.message_post(body=f'TEST: summary error: {e}')

