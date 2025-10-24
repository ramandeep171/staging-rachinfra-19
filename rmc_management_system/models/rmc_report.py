from odoo import models, fields, tools


class RmcConsolidatedReport(models.Model):
    _name = 'rmc.consolidated.report'
    _description = 'RMC Consolidated Report'
    _auto = False

    date = fields.Date(string='Date')
    customer_id = fields.Many2one('res.partner', string='Customer')
    concrete_grade = fields.Selection([
        ('m7.5', 'M7.5'),
        ('m10', 'M10'),
        ('m15', 'M15'),
        ('m20', 'M20'),
        ('m25', 'M25'),
        ('m30', 'M30'),
        ('m35', 'M35'),
        ('m40', 'M40'),
    ], string='Concrete Grade')

    quantity_delivered = fields.Float(string='Quantity Delivered (M3)')
    customer_provides_cement = fields.Boolean(string='Customer Provides Cement')

    plant_weight = fields.Float(string='Plant Weight (Kg)')
    customer_weight = fields.Float(string='Customer Weight (Kg)')
    weight_variance = fields.Float(string='Weight Variance (Kg)')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        cr = self.env.cr

        # Check if required tables exist
        cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name IN ('rmc_batch', 'rmc_weighbridge')
            """
        )
        table_count = cr.fetchone()[0]

        if table_count < 2:
            cr.execute(
                """
                CREATE OR REPLACE VIEW %s AS (
                    SELECT
                        row_number() OVER () AS id,
                        DATE(so.date_order) AS date,
                        so.partner_id AS customer_id,
                        'm20' AS concrete_grade,
                        0.0 AS quantity_delivered,
                        so.customer_provides_cement,
                        0.0 AS plant_weight,
                        0.0 AS customer_weight,
                        0.0 AS weight_variance
                    FROM sale_order so
                    WHERE so.state = 'sale'
                )
                """
                % self._table
            )
            return

        # Check columns in weighbridge
        cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'rmc_weighbridge'
            AND column_name IN ('plant_net_weight','customer_net_weight','weight_variance')
            """
        )
        column_count = cr.fetchone()[0]

        # Confirm date field on sale_order
        cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'confirmation_date'
            """
        )
        has_conf = cr.fetchone()[0]
        date_field = 'confirmation_date' if has_conf else 'date_order'
        date_expr = "DATE(so.%s)" % date_field

        if column_count >= 3:
            cr.execute(
                """
                CREATE OR REPLACE VIEW %s AS (
                    SELECT
                        row_number() OVER () AS id,
                        %s AS date,
                        so.partner_id AS customer_id,
                        COALESCE(b.concrete_grade, 'm20') AS concrete_grade,
                        COALESCE(SUM(b.quantity_produced), 0.0) AS quantity_delivered,
                        so.customer_provides_cement,
                        COALESCE(AVG(w.plant_net_weight), 0.0) AS plant_weight,
                        COALESCE(AVG(w.customer_net_weight), 0.0) AS customer_weight,
                        COALESCE(AVG(w.weight_variance), 0.0) AS weight_variance
                    FROM sale_order so
                    LEFT JOIN rmc_batch b ON b.sale_order_id = so.id
                    LEFT JOIN rmc_weighbridge w ON w.sale_order_id = so.id
                    WHERE so.state = 'sale'
                    GROUP BY %s, so.partner_id, b.concrete_grade, so.customer_provides_cement
                )
                """
                % (self._table, date_expr, date_expr)
            )
        else:
            cr.execute(
                """
                CREATE OR REPLACE VIEW %s AS (
                    SELECT
                        row_number() OVER () AS id,
                        %s AS date,
                        so.partner_id AS customer_id,
                        COALESCE(b.concrete_grade, 'm20') AS concrete_grade,
                        COALESCE(SUM(b.quantity_produced), 0.0) AS quantity_delivered,
                        so.customer_provides_cement,
                        0.0 AS plant_weight,
                        0.0 AS customer_weight,
                        0.0 AS weight_variance
                    FROM sale_order so
                    LEFT JOIN rmc_batch b ON b.sale_order_id = so.id
                    WHERE so.state = 'sale'
                    GROUP BY %s, so.partner_id, b.concrete_grade, so.customer_provides_cement
                )
                """
                % (self._table, date_expr, date_expr)
            )


class RmcDocketReport(models.Model):
    _name = 'rmc.docket.report'
    _description = 'RMC Docket-wise Report'
    _auto = False

    docket_id = fields.Many2one('rmc.docket', string='Docket', readonly=True)
    docket_number = fields.Char(string='Docket Number', readonly=True)
    docket_date = fields.Datetime(string='Docket Date', readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    customer_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder', readonly=True)
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', readonly=True)
    subcontractor_id = fields.Many2one('rmc.subcontractor', string='Subcontractor', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    quantity_ordered = fields.Float(string='Qty Ordered (M3)', readonly=True)
    quantity_produced = fields.Float(string='Qty Produced (M3)', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_production', 'In Production'),
        ('ready', 'Ready'),
        ('dispatched', 'Dispatched'),
        ('delivered', 'Delivered'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True)

    truck_loading_count = fields.Integer(string='Truck Loadings', readonly=True)
    plant_check_count = fields.Integer(string='Plant Checks', readonly=True)
    batch_count = fields.Integer(string='Batches', readonly=True)
    log_count = fields.Integer(string='Logs', readonly=True)
    invoice_id = fields.Many2one('account.move', string='Customer Invoice', readonly=True)
    vendor_bill_count = fields.Integer(string='Vendor Bills', readonly=True)
    cube_test_count = fields.Integer(string='Cube Tests', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        cr = self.env.cr
        cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    d.id AS docket_id,
                    d.docket_number,
                    d.docket_date,
                    d.sale_order_id,
                    so.partner_id AS customer_id,
                    d.workorder_id,
                    d.helpdesk_ticket_id,
                    d.subcontractor_id,
                    d.product_id,
                    COALESCE(d.quantity_ordered, 0.0) AS quantity_ordered,
                    COALESCE(d.quantity_produced, 0.0) AS quantity_produced,
                    d.state,
                    COALESCE((SELECT COUNT(*) FROM rmc_truck_loading tl WHERE tl.docket_id = d.id), 0) AS truck_loading_count,
                    COALESCE((SELECT COUNT(*) FROM rmc_plant_check pc WHERE pc.docket_id = d.id), 0) AS plant_check_count,
                    COALESCE((SELECT COUNT(*) FROM rmc_docket_batch db WHERE db.docket_id = d.id), 0) AS batch_count,
                    COALESCE((SELECT COUNT(*) FROM mail_message mm WHERE mm.model = 'rmc.docket' AND mm.res_id = d.id), 0) AS log_count,
                    d.invoice_id AS invoice_id,
                    COALESCE((SELECT COUNT(*) FROM account_move am JOIN dropshipping_workorder wo ON wo.id = d.workorder_id WHERE am.move_type = 'in_invoice' AND am.invoice_origin ILIKE wo.name), 0) AS vendor_bill_count,
                    COALESCE((SELECT COUNT(*) FROM quality_cube_test qct WHERE qct.docket_id = d.id), 0) AS cube_test_count
                FROM rmc_docket d
                LEFT JOIN sale_order so ON so.id = d.sale_order_id
            )
            """
            % self._table
        )

    # Drilldown helpers
    def action_open_docket(self):
        self.ensure_one()
        if not self.docket_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'rmc.docket',
            'res_id': self.docket_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_workorder(self):
        self.ensure_one()
        if not self.workorder_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dropshipping.workorder',
            'res_id': self.workorder_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _action_open_many(self, model, domain):
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_open_truck_loadings(self):
        self.ensure_one()
        return self._action_open_many('rmc.truck_loading', [('docket_id', '=', self.docket_id.id)])

    def action_open_plant_checks(self):
        self.ensure_one()
        return self._action_open_many('rmc.plant_check', [('docket_id', '=', self.docket_id.id)])

    def action_open_batches(self):
        self.ensure_one()
        return self._action_open_many('rmc.docket.batch', [('docket_id', '=', self.docket_id.id)])

    def action_open_logs(self):
        self.ensure_one()
        return self._action_open_many('mail.message', [('model', '=', 'rmc.docket'), ('res_id', '=', self.docket_id.id)])

    def action_open_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_vendor_bills(self):
        self.ensure_one()
        # vendor bills inferred via workorder name heuristic
        dom = [('move_type', '=', 'in_invoice')]
        if self.workorder_id:
            dom.append(('invoice_origin', 'ilike', self.workorder_id.name))
        return self._action_open_many('account.move', dom)

    def action_open_cube_tests(self):
        self.ensure_one()
        return self._action_open_many('quality.cube.test', [('docket_id', '=', self.docket_id.id)])


class RmcWorkorderReport(models.Model):
    _name = 'rmc.workorder.report'
    _description = 'RMC Workorder-wise Report'
    _auto = False

    workorder_id = fields.Many2one('dropshipping.workorder', string='Workorder', readonly=True)
    name = fields.Char(string='Workorder Number', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    quantity_ordered = fields.Float(string='Qty Ordered', readonly=True)
    quantity_delivered = fields.Float(string='Qty Delivered', readonly=True)
    quantity_remaining = fields.Float(string='Qty Remaining', readonly=True)

    docket_count = fields.Integer(string='Dockets', readonly=True)
    ticket_count = fields.Integer(string='Tickets', readonly=True)
    truck_loading_count = fields.Integer(string='Truck Loadings', readonly=True)
    batch_count = fields.Integer(string='Batches', readonly=True)
    po_count = fields.Integer(string='Purchase Orders', readonly=True)
    vendor_bill_count = fields.Integer(string='Vendor Bills', readonly=True)
    invoice_count = fields.Integer(string='Customer Invoices', readonly=True)
    cube_test_count = fields.Integer(string='Cube Tests', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        cr = self.env.cr
        cr.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'account_move' AND column_name = 'docket_id'
        """)
        has_invoice_docket = cr.fetchone()[0] > 0

        delivered_expr = "COALESCE((SELECT SUM(COALESCE(d.quantity_produced, 0.0)) FROM dockets d WHERE d.workorder_id = wo.id), 0.0)"
        remaining_expr = f"GREATEST(COALESCE(wo.quantity_ordered, 0.0) - {delivered_expr}, 0.0)"
        invoice_count_expr = (
            "COALESCE((SELECT COUNT(DISTINCT am.id) FROM account_move am WHERE am.move_type = 'out_invoice' AND am.docket_id IN (SELECT d.id FROM dockets d WHERE d.workorder_id = wo.id)), 0)"
            if has_invoice_docket
            else "COALESCE((SELECT COUNT(DISTINCT am.id) FROM account_move am WHERE am.move_type = 'out_invoice' AND am.invoice_origin ILIKE wo.name), 0)"
        )

        sql = f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH dockets AS (
                    SELECT d.* FROM rmc_docket d
                )
                SELECT
                    row_number() OVER () AS id,
                    wo.id AS workorder_id,
                    wo.name,
                    wo.date_order,
                    wo.sale_order_id,
                    wo.partner_id,
                    COALESCE(wo.quantity_ordered, 0.0) AS quantity_ordered,
                    {delivered_expr} AS quantity_delivered,
                    {remaining_expr} AS quantity_remaining,
                    COALESCE((SELECT COUNT(*) FROM dockets d WHERE d.workorder_id = wo.id), 0) AS docket_count,
                    COALESCE((SELECT COUNT(*) FROM dropshipping_workorder_ticket t WHERE t.workorder_id = wo.id), 0) AS ticket_count,
                    COALESCE((SELECT COUNT(*) FROM rmc_truck_loading tl WHERE tl.docket_id IN (SELECT d.id FROM dockets d WHERE d.workorder_id = wo.id)), 0) AS truck_loading_count,
                    COALESCE((SELECT COUNT(*) FROM rmc_docket_batch db WHERE db.docket_id IN (SELECT d.id FROM dockets d WHERE d.workorder_id = wo.id)), 0) AS batch_count,
                    COALESCE((SELECT COUNT(*) FROM purchase_order po WHERE po.origin = wo.name), 0) AS po_count,
                    COALESCE((SELECT COUNT(*) FROM account_move am WHERE am.move_type = 'in_invoice' AND (am.invoice_origin ILIKE wo.name)), 0) AS vendor_bill_count,
                    {invoice_count_expr} AS invoice_count,
                    COALESCE((SELECT COUNT(*) FROM quality_cube_test qct WHERE qct.workorder_id = wo.id), 0) AS cube_test_count
                FROM dropshipping_workorder wo
            )
        """
        cr.execute(sql)

    # Drilldown helpers
    def action_open_workorder(self):
        self.ensure_one()
        if not self.workorder_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dropshipping.workorder',
            'res_id': self.workorder_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _action_open_many(self, model, domain):
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_open_dockets(self):
        self.ensure_one()
        return self._action_open_many('rmc.docket', [('workorder_id', '=', self.workorder_id.id)])

    def action_open_tickets(self):
        self.ensure_one()
        return self._action_open_many('dropshipping.workorder.ticket', [('workorder_id', '=', self.workorder_id.id)])

    def action_open_truck_loadings(self):
        self.ensure_one()
        return self._action_open_many('rmc.truck_loading', [('docket_id.workorder_id', '=', self.workorder_id.id)])

    def action_open_batches(self):
        self.ensure_one()
        return self._action_open_many('rmc.docket.batch', [('docket_id.workorder_id', '=', self.workorder_id.id)])

    def action_open_purchase_orders(self):
        self.ensure_one()
        return self._action_open_many('purchase.order', [('origin', '=', self.name)])

    def action_open_vendor_bills(self):
        self.ensure_one()
        return self._action_open_many('account.move', [('move_type', '=', 'in_invoice'), ('invoice_origin', 'ilike', self.name)])

    def action_open_invoices(self):
        self.ensure_one()
        domain = [('move_type', '=', 'out_invoice')]
        if 'docket_id' in self.env['account.move']._fields:
            domain.append(('docket_id.workorder_id', '=', self.workorder_id.id))
        else:
            domain.append(('invoice_origin', 'ilike', self.name))
        return self._action_open_many('account.move', domain)

    def action_open_cube_tests(self):
        self.ensure_one()
        return self._action_open_many('quality.cube.test', [('workorder_id', '=', self.workorder_id.id)])


class RmcSaleOrderReport(models.Model):
    _name = 'rmc.saleorder.report'
    _description = 'RMC Sale Order-wise Report'
    _auto = False

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    name = fields.Char(string='Order', readonly=True)
    date_order = fields.Datetime(string='Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    amount_total = fields.Monetary(string='Amount Total', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    workorder_count = fields.Integer(string='Workorders', readonly=True)
    docket_count = fields.Integer(string='Dockets', readonly=True)
    cube_test_count = fields.Integer(string='Cube Tests', readonly=True)
    trial_mix_count = fields.Integer(string='Trial Mixes', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        cr = self.env.cr

        # Determine which date field to use for sale orders
        cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'confirmation_date'
            """
        )
        has_conf = cr.fetchone()[0] > 0
        date_field = 'confirmation_date' if has_conf else 'date_order'

        # Check if quality_cube_test has a trial_mix_id column to count distinct trial mixes per SO
        cr.execute(
            """
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'quality_cube_test' AND column_name = 'trial_mix_id'
            """
        )
        has_trial_mix_link = cr.fetchone()[0] > 0
        trial_mix_expr = (
            "COALESCE((SELECT COUNT(DISTINCT qct.trial_mix_id) FROM quality_cube_test qct WHERE qct.sale_order_id = so.id AND qct.trial_mix_id IS NOT NULL), 0)"
            if has_trial_mix_link else "0"
        )

        sql = f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    so.id as id,
                    so.id as sale_order_id,
                    so.name as name,
                    so.{date_field} as date_order,
                    so.partner_id,
                    so.amount_total,
                    so.currency_id,
                    COALESCE((SELECT COUNT(*) FROM dropshipping_workorder wo WHERE wo.sale_order_id = so.id), 0) AS workorder_count,
                    COALESCE((SELECT COUNT(*) FROM rmc_docket d WHERE d.sale_order_id = so.id), 0) AS docket_count,
                    COALESCE((SELECT COUNT(*) FROM quality_cube_test qct WHERE qct.sale_order_id = so.id), 0) AS cube_test_count,
                    {trial_mix_expr} AS trial_mix_count
                FROM sale_order so
                WHERE so.state IN ('sale','done')
            )
        """
        cr.execute(sql)

    # Drilldowns
    def action_open_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _action_open_many(self, model, domain):
        return {
            'type': 'ir.actions.act_window',
            'res_model': model,
            'view_mode': 'list,form',
            'domain': domain,
            'target': 'current',
        }

    def action_open_workorders(self):
        self.ensure_one()
        return self._action_open_many('dropshipping.workorder', [('sale_order_id', '=', self.sale_order_id.id)])

    def action_open_dockets(self):
        self.ensure_one()
        return self._action_open_many('rmc.docket', [('sale_order_id', '=', self.sale_order_id.id)])

    def action_open_cube_tests(self):
        self.ensure_one()
        return self._action_open_many('quality.cube.test', [('sale_order_id', '=', self.sale_order_id.id)])

    def action_open_trial_mixes(self):
        self.ensure_one()
        return self._action_open_many('quality.trial.mix', [('sale_order_id', '=', self.sale_order_id.id)])