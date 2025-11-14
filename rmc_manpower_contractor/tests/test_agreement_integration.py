# -*- coding: utf-8 -*-
import base64

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta

@tagged('post_install', '-at_install')
class TestAgreementIntegration(TransactionCase):

    def setUp(self):
        super(TestAgreementIntegration, self).setUp()
        self.Agreement = self.env['rmc.contract.agreement']
        self.DieselLog = self.env['rmc.diesel.log']
        self.Maintenance = self.env['rmc.maintenance.check']
        self.Attendance = self.env['rmc.attendance.compliance']
        
        self.contractor = self.env['res.partner'].create({
            'name': 'Test Contractor',
            'supplier_rank': 1,
        })
        
        self.agreement = self.Agreement.create({
            'name': 'TEST-001',
            'contractor_id': self.contractor.id,
            'contract_type': 'driver_transport',
            'validity_start': datetime.now().date(),
            'validity_end': datetime.now().date() + timedelta(days=365),
            'mgq_target': 1000.0,
            'part_a_fixed': 50000.0,
            'part_b_variable': 30000.0,
        })
        payable_type = self.env.ref('account.data_account_type_payable')
        self.liquidity_type = self.env.ref('account.data_account_type_liquidity')
        self.retention_account = self.env['account.account'].search([
            ('code', '=', '210950'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not self.retention_account:
            self.retention_account = self.env['account.account'].create({
                'name': 'Retention Payable',
                'code': '210950',
                'user_type_id': payable_type.id,
                'company_id': self.env.company.id,
                'reconcile': True,
            })
        self.general_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not self.general_journal:
            self.general_journal = self.env['account.journal'].create({
                'name': 'General - Test',
                'code': 'GENR',
                'type': 'general',
                'company_id': self.env.company.id,
            })
        self.bank_journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', self.env.company.id),
            ('default_account_id', '!=', False),
        ], limit=1)
        if not self.bank_journal:
            bank_account = self.env['account.account'].create({
                'name': 'Retention Bank',
                'code': 'RBK%s' % str(self.env.company.id).zfill(2),
                'user_type_id': self.liquidity_type.id,
                'company_id': self.env.company.id,
                'reconcile': True,
            })
            self.bank_journal = self.env['account.journal'].create({
                'name': 'Retention Bank',
                'code': 'RBK1',
                'type': 'bank',
                'company_id': self.env.company.id,
                'default_account_id': bank_account.id,
            })
        self.bank_account = self.bank_journal.default_account_id
        if not self.bank_account.reconcile:
            self.bank_account.reconcile = True
        manual_in_method = self.env.ref('account.account_payment_method_manual_in')
        if not self.bank_journal.inbound_payment_method_line_ids:
            self.bank_journal.write({
                'inbound_payment_method_line_ids': [(0, 0, {
                    'name': manual_in_method.name,
                    'payment_method_id': manual_in_method.id,
                })]
            })
        self.inbound_method_line = self.bank_journal.inbound_payment_method_line_ids[:1]

    def _get_purchase_journal(self):
        journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            payable_account = self.env['account.account'].search([
                ('internal_type', '=', 'payable'),
                ('deprecated', '=', False),
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            journal = self.env['account.journal'].create({
                'name': 'Vendor Bills - Test',
                'code': 'VBTS',
                'type': 'purchase',
                'company_id': self.env.company.id,
                'default_account_id': payable_account.id,
            })
        return journal

    def _get_expense_account(self):
        account = self.env['account.account'].search([
            ('internal_type', '=', 'expense'),
            ('deprecated', '=', False),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not account:
            account = self.env['account.account'].create({
                'name': 'Retention Expense',
                'code': 'XRET',
                'user_type_id': self.env.ref('account.data_account_type_expenses').id,
                'company_id': self.env.company.id,
            })
        return account

    def _create_vendor_bill(
        self,
        amount,
        link_agreement=True,
        analytic_account=None,
        partner=None,
        agreement=None,
        invoice_date=None,
    ):
        journal = self._get_purchase_journal()
        expense_account = self._get_expense_account()
        partner = partner or self.contractor
        agreement = agreement or self.agreement
        invoice_date = invoice_date or fields.Date.today()
        line_vals = {
            'name': 'Retention Test Line',
            'quantity': 1.0,
            'price_unit': amount,
            'account_id': expense_account.id,
        }
        if analytic_account:
            line_vals['analytic_distribution'] = {analytic_account.id: 100}
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': invoice_date,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, line_vals)],
        }
        if link_agreement:
            bill_vals['agreement_id'] = agreement.id
        bill = self.env['account.move'].create(bill_vals)
        return bill

    def _register_payment_for_bill(self, bill, amount=None):
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=bill.ids,
        ).create({
            'journal_id': self.bank_journal.id,
            'payment_date': fields.Date.today(),
            'payment_method_line_id': self.inbound_method_line.id,
            'amount': amount or bill.amount_residual,
        })
        wizard.action_create_payments()

    def _run_retention_cron(self):
        self.env['rmc.agreement.retention'].cron_release_due_entries()

    def _assert_retention_released(self, bill):
        self.assertTrue(bill.retention_entry_ids, 'Retention entry missing on bill.')
        entry = bill.retention_entry_ids[0]
        self.assertEqual(entry.release_state, 'released', 'Retention entry should be released.')
        self.assertTrue(entry.release_move_id, 'Release journal entry missing.')
        retention_line = entry.retention_move_line_id
        self.assertTrue(retention_line and retention_line.reconciled, 'Retention hold line should be reconciled.')
        release_move = entry.release_move_id
        self.assertEqual(release_move.journal_id.type, 'general', 'Release move must use General Journal.')
        liquidity_lines = release_move.line_ids.filtered(lambda l: l.account_id.user_type_id == self.liquidity_type)
        self.assertTrue(liquidity_lines, 'Release move should credit a liquidity account.')
        release_messages = bill.message_ids.filtered(lambda m: 'Retention released on' in (m.body or ''))
        self.assertTrue(release_messages, 'Bill should log a release message.')

    def test_01_unsigned_agreement_blocks_validation(self):
        """Test that unsigned agreement blocks operational record validation"""
        diesel = self.DieselLog.create({
            'agreement_id': self.agreement.id,
            'date': datetime.now().date(),
            'opening_ltr': 100,
            'issued_ltr': 50,
            'closing_ltr': 50,
            'work_done_km': 200,
        })
        
        self.assertEqual(diesel.state, 'pending_agreement', 
                        'Diesel log should be pending when agreement unsigned')

    def test_02_payment_hold_when_unsigned(self):
        """Test payment hold is active when agreement is unsigned"""
        self.agreement._compute_payment_hold()
        self.assertTrue(self.agreement.payment_hold, 
                       'Payment should be on hold for unsigned agreement')
        self.assertIn('not signed', self.agreement.payment_hold_reason.lower())

    def test_03_performance_computation_driver_type(self):
        """Test performance computation for driver_transport contract type"""
        # Create validated diesel logs
        for i in range(3):
            diesel = self.DieselLog.create({
                'agreement_id': self.agreement.id,
                'date': datetime.now().date() - timedelta(days=i),
                'opening_ltr': 100,
                'issued_ltr': 50,
                'closing_ltr': 50,
                'work_done_km': 250,  # 5 km/l efficiency
            })
            diesel.state = 'validated'
        
        self.agreement._compute_diesel_kpi()
        self.assertAlmostEqual(self.agreement.avg_diesel_efficiency, 5.0, places=2,
                              msg='Diesel efficiency should be 5 km/l')
        
        self.agreement._compute_performance()
        self.assertGreater(self.agreement.performance_score, 0,
                          'Performance score should be computed')

    def test_04_breakdown_deduction_calculation(self):
        """Test Clause 9 breakdown deduction calculation"""
        Breakdown = self.env['rmc.breakdown.event']
        
        breakdown = Breakdown.create({
            'agreement_id': self.agreement.id,
            'event_type': 'emergency',
            'start_time': datetime.now() - timedelta(hours=10),
            'end_time': datetime.now(),
            'responsibility': 'contractor',
            'is_mgq_achieved': False,
        })
        
        breakdown._compute_downtime()
        self.assertAlmostEqual(breakdown.downtime_hr, 10.0, places=1)
        
        breakdown._compute_deduction()
        self.assertGreater(breakdown.deduction_amount, 0,
                          'Contractor fault should trigger deduction')

    def test_05_breakdown_no_deduction_if_mgq_achieved(self):
        """Test no deduction if MGQ achieved despite breakdown"""
        Breakdown = self.env['rmc.breakdown.event']
        
        breakdown = Breakdown.create({
            'agreement_id': self.agreement.id,
            'event_type': 'emergency',
            'start_time': datetime.now() - timedelta(hours=10),
            'end_time': datetime.now(),
            'responsibility': 'contractor',
            'is_mgq_achieved': True,
        })
        
        breakdown._compute_deduction()
        self.assertEqual(breakdown.deduction_amount, 0.0,
                        'No deduction if MGQ achieved')

    def test_06_inventory_variance_computation(self):
        """Test inventory variance calculation"""
        Inventory = self.env['rmc.inventory.handover']
        
        product = self.env['product.product'].create({
            'name': 'Test Item',
            # 'type' is a selection on product.template; valid values in this Odoo install are
            # 'consu' (goods), 'service', or 'combo'. Use 'consu' for a consumable product.
            'type': 'consu',
            'standard_price': 100.0,
        })
        
        inv = Inventory.create({
            'agreement_id': self.agreement.id,
            'date': datetime.now().date(),
            'item_id': product.id,
            'uom_id': product.uom_id.id,
            'issued_qty': 100,
            'returned_qty': 95,
            'unit_price': 100.0,
        })
        
        inv._compute_variance()
        self.assertEqual(inv.variance_qty, 5.0, 'Variance should be 5')
        self.assertEqual(inv.variance_value, 500.0, 'Variance value should be 500')

    def test_07_star_rating_computation(self):
        """Test star rating based on performance score"""
        self.agreement.performance_score = 92.0
        self.agreement._compute_stars()
        self.assertEqual(self.agreement.stars, '5', 
                        'Performance 92% should be 5 stars')
        
        self.agreement.performance_score = 76.0
        self.agreement._compute_stars()
        self.assertEqual(self.agreement.stars, '4',
                        'Performance 76% should be 4 stars')

    def test_08_manpower_matrix_total(self):
        """Test manpower matrix total calculation"""
        Matrix = self.env['rmc.manpower.matrix']
        
        matrix = Matrix.create({
            'agreement_id': self.agreement.id,
            'designation': 'Driver',
            'headcount': 5,
            'shift': 'day',
            'base_rate': 10000,
            'remark': 'part_a',
        })
        
        matrix._compute_total()
        self.assertEqual(matrix.total_amount, 50000.0,
                        'Total should be 5 × 10000 = 50000')

    def test_09_attendance_compliance_calculation(self):
        """Test attendance compliance percentage calculation"""
        # Add manpower matrix first
        Matrix = self.env['rmc.manpower.matrix']
        Matrix.create({
            'agreement_id': self.agreement.id,
            'designation': 'Staff',
            'headcount': 10,
            'shift': 'general',
            'base_rate': 5000,
            'remark': 'part_a',
        })
        
        attendance = self.Attendance.create({
            'agreement_id': self.agreement.id,
            'date': datetime.now().date(),
            'headcount_present': 8,
            'documents_ok': True,
            'supervisor_ok': True,
        })
        
        attendance._compute_expected()
        self.assertEqual(attendance.headcount_expected, 10)
        
        attendance._compute_compliance()
        self.assertGreater(attendance.compliance_percentage, 0,
                          'Compliance should be calculated')

    def test_10_contract_type_immutable_after_sign(self):
        """Test contract type cannot change after signing"""
        # Mock signing
        self.agreement.write({'state': 'active'})
        
        # Attempt to change contract type should fail
        with self.assertRaises(ValidationError):
            self.agreement.write({'contract_type': 'pump_ops'})

    def test_11_part_b_manual_value_preserved_without_matrix_lines(self):
        """Manual Part-B value should persist if no matrix lines use Part-B."""
        Matrix = self.env['rmc.manpower.matrix']
        Matrix.create({
            'agreement_id': self.agreement.id,
            'designation': 'Operator',
            'headcount': 3,
            'shift': 'day',
            'base_rate': 12000,
            'remark': 'part_a',
        })

        self.agreement.write({'part_b_variable': 2550.0})
        self.agreement._update_manpower_totals_from_matrix()
        self.assertEqual(
            self.agreement.part_b_variable,
            2550.0,
            'Part-B should keep manual value when no Part-B lines exist.',
        )

    def test_12_part_b_resets_after_removing_matrix_lines(self):
        """Part-B should follow matrix totals once Part-B lines existed."""
        Matrix = self.env['rmc.manpower.matrix']
        part_b_line = Matrix.create({
            'agreement_id': self.agreement.id,
            'designation': 'MGQ Bonus',
            'headcount': 1,
            'shift': 'general',
            'base_rate': 2000.0,
            'remark': 'part_b',
        })

        self.agreement._update_manpower_totals_from_matrix()
        self.assertEqual(self.agreement.part_b_variable, 2000.0, 'Part-B should match matrix total.')

        part_b_line.unlink()
        self.agreement._update_manpower_totals_from_matrix()
        self.assertEqual(
            self.agreement.part_b_variable,
            0.0,
            'Removing all Part-B lines should reset the Part-B value.',
        )

    def test_13_retention_entry_created_on_bill(self):
        """Posting a vendor bill should create retention entry automatically."""
        bill = self._create_vendor_bill(10000.0)
        bill.action_post()
        self.assertTrue(bill.retention_entry_ids, 'Retention entry should be created')
        entry = bill.retention_entry_ids[0]
        expected = bill.amount_untaxed * (self.agreement.retention_rate / 100.0)
        self.assertAlmostEqual(entry.retention_amount, expected, places=2)
        self.assertEqual(bill.retention_release_date, entry.scheduled_release_date)
        self.assertEqual(bill.release_due_date, entry.scheduled_release_date)
        self.assertTrue(bill.x_retention_booked, 'Retention booking flag should be set.')
        self.assertTrue(bill.retention_move_id, 'Retention journal entry should be linked.')
        self.assertAlmostEqual(
            bill.amount_residual,
            bill.amount_total - bill.retention_amount,
            places=2,
            msg='Bill residual should drop by retention amount.'
        )

    def test_14_retention_release_date_over_period(self):
        """Over-period retention should target agreement end date."""
        self.agreement.write({'retention_duration': 'over_period'})
        bill = self._create_vendor_bill(5000.0)
        bill.action_post()
        entry = bill.retention_entry_ids[0]
        self.assertEqual(entry.scheduled_release_date, self.agreement.validity_end)
        self.assertEqual(bill.release_due_date, self.agreement.validity_end)

    def test_15_overlap_active_agreement_blocked(self):
        """Only one active agreement allowed per vendor/analytic/company on overlapping dates."""
        self.agreement.write({'state': 'active'})
        with self.assertRaises(ValidationError):
            self.Agreement.create({
                'name': 'TEST-OVERLAP',
                'contractor_id': self.contractor.id,
                'contract_type': 'driver_transport',
                'validity_start': self.agreement.validity_start + timedelta(days=15),
                'validity_end': self.agreement.validity_end + timedelta(days=30),
                'state': 'active',
            })

    def test_16_auto_detect_agreement_using_analytic(self):
        """Bill posting should auto-link agreement when analytics line up."""
        analytic = self.env['account.analytic.account'].create({'name': 'Ops-1'})
        self.agreement.write({
            'state': 'active',
            'analytic_account_id': analytic.id,
        })
        bill = self._create_vendor_bill(8000.0, link_agreement=False, analytic_account=analytic)
        bill.action_post()
        self.assertEqual(bill.agreement_id, self.agreement, 'Agreement should auto-link via analytic match.')
        self.assertTrue(bill.retention_entry_ids, 'Retention entries should be created after auto-link.')

    def test_17_auto_detect_fallback_to_vendor(self):
        """If no analytic match exists, fallback to vendor-only detection."""
        analytic = self.env['account.analytic.account'].create({'name': 'Ops-Extra'})
        self.agreement.write({'state': 'active', 'analytic_account_id': False})
        bill = self._create_vendor_bill(6000.0, link_agreement=False, analytic_account=analytic)
        bill.action_post()
        self.assertEqual(bill.agreement_id, self.agreement, 'Vendor-only fallback should link the bill.')

    def test_18_auto_detect_conflict_raises(self):
        """Multiple vendor agreements should raise a validation error when ambiguous."""
        analytic_a = self.env['account.analytic.account'].create({'name': 'Ops-A'})
        analytic_b = self.env['account.analytic.account'].create({'name': 'Ops-B'})
        self.agreement.write({
            'state': 'active',
            'analytic_account_id': analytic_a.id,
        })
        self.Agreement.create({
            'name': 'TEST-002',
            'contractor_id': self.contractor.id,
            'contract_type': 'driver_transport',
            'validity_start': self.agreement.validity_start,
            'validity_end': self.agreement.validity_end,
            'state': 'active',
            'analytic_account_id': analytic_b.id,
        })
        bill = self._create_vendor_bill(4500.0, link_agreement=False)
        with self.assertRaises(ValidationError):
            bill.action_post()

    def test_19_missing_retention_account_blocks_post(self):
        """Posting should fail if retention payable account is absent."""
        self.retention_account.unlink()
        bill = self._create_vendor_bill(4000.0)
        with self.assertRaises(ValidationError):
            bill.action_post()

    def test_20_retention_move_removed_on_reset(self):
        """Resetting invoice to draft should drop retention move and flags."""
        bill = self._create_vendor_bill(7500.0)
        bill.action_post()
        retention_move = bill.retention_move_id
        self.assertTrue(retention_move, 'Retention JE must exist before reset.')
        bill.button_draft()
        self.assertFalse(bill.retention_move_id, 'Retention move link should be cleared on reset.')
        self.assertFalse(bill.x_retention_booked, 'Retention booked flag should reset on draft.')
        self.assertFalse(retention_move.exists(), 'Retention journal entry should be deleted after reset.')

    def test_21_retention_with_child_contact_vendor(self):
        """Retention booking should work when the bill partner is a child contact."""
        parent_vendor = self.env['res.partner'].create({
            'name': 'Parent Contractor',
            'supplier_rank': 1,
            'is_company': True,
        })
        child_vendor = self.env['res.partner'].create({
            'name': 'Branch Vendor',
            'parent_id': parent_vendor.id,
            'type': 'invoice',
            'supplier_rank': 1,
        })
        child_agreement = self.Agreement.create({
            'name': 'TEST-CHILD',
            'contractor_id': child_vendor.id,
            'contract_type': 'driver_transport',
            'validity_start': datetime.now().date(),
            'validity_end': datetime.now().date() + timedelta(days=365),
            'state': 'active',
        })
        bill = self._create_vendor_bill(
            8200.0,
            link_agreement=True,
            partner=child_vendor,
            agreement=child_agreement,
        )
        bill.action_post()
        self.assertTrue(bill.retention_move_id, 'Retention JE should be created for child vendors.')
        self.assertAlmostEqual(
            bill.amount_residual,
            bill.amount_total - bill.retention_amount,
            places=2,
            msg='Residual must exclude retention even for child partner bills.',
        )

    def test_22_retention_release_after_90_days(self):
        """Retention should auto-release after 90 days."""
        past_date = fields.Date.today() - timedelta(days=95)
        bill = self._create_vendor_bill(12000.0, invoice_date=past_date)
        bill.action_post()
        self._run_retention_cron()
        self._assert_retention_released(bill)

    def test_23_retention_release_after_180_days(self):
        """Retention should auto-release after 6 months (180 days)."""
        self.agreement.write({'retention_duration': '6_months'})
        past_date = fields.Date.today() - timedelta(days=190)
        bill = self._create_vendor_bill(14000.0, invoice_date=past_date)
        bill.action_post()
        self._run_retention_cron()
        self._assert_retention_released(bill)

    def test_24_retention_release_after_1_year(self):
        """Retention should auto-release after one year."""
        self.agreement.write({'retention_duration': '1_year'})
        past_date = fields.Date.today() - timedelta(days=380)
        bill = self._create_vendor_bill(16000.0, invoice_date=past_date)
        bill.action_post()
        self._run_retention_cron()
        self._assert_retention_released(bill)

    def test_25_retention_release_on_agreement_end(self):
        """Retention should auto-release on agreement end date for over-period duration."""
        end_date = fields.Date.today() - timedelta(days=1)
        self.agreement.write({
            'retention_duration': 'over_period',
            'validity_end': end_date,
            'end_date': end_date,
        })
        bill = self._create_vendor_bill(18000.0)
        bill.action_post()
        self._run_retention_cron()
        self._assert_retention_released(bill)

    def test_26_wizard_prefills_from_log_values(self):
        """Wizard defaults should mirror the edited log snapshot."""
        log = self.env['rmc.billing.prepare.log'].create({
            'agreement_id': self.agreement.id,
            'period_start': fields.Date.from_string('2024-01-01'),
            'period_end': fields.Date.from_string('2024-01-31'),
            'prime_output_qty': 875.0,
            'optimized_standby_qty': 42.0,
            'mgq_achieved': 875.0,
        })
        action = log.action_prepare_monthly_bill()
        wizard = self.env['rmc.billing.prepare.wizard'].with_context(action.get('context', {})).create({})
        self.assertEqual(wizard.period_start, log.period_start, 'Period start should copy from the log.')
        self.assertEqual(wizard.period_end, log.period_end, 'Period end should copy from the log.')
        self.assertEqual(wizard.prime_output_qty, log.prime_output_qty, 'Prime output must respect log edits.')
        self.assertEqual(
            wizard.optimized_standby_qty,
            log.optimized_standby_qty,
            'Optimized standby must respect log edits.',
        )

    def test_27_supporting_reports_posted_to_log_chatter(self):
        """Supporting PDFs should also live on the log chatter."""
        self._get_purchase_journal()
        self.env['ir.attachment'].create({
            'name': 'signed_agreement.pdf',
            'res_model': 'rmc.contract.agreement',
            'res_id': self.agreement.id,
            'type': 'binary',
            'datas': base64.b64encode(b'signed'),
        })
        log = self.env['rmc.billing.prepare.log'].create({
            'agreement_id': self.agreement.id,
            'period_start': fields.Date.from_string('2024-02-01'),
            'period_end': fields.Date.from_string('2024-02-29'),
            'prime_output_qty': 500.0,
            'optimized_standby_qty': 10.0,
            'mgq_achieved': 500.0,
        })
        action = log.action_prepare_monthly_bill()
        wizard = self.env['rmc.billing.prepare.wizard'].with_context(action.get('context', {})).create({})
        wizard.action_create_bill()

        log = self.env['rmc.billing.prepare.log'].browse(log.id)
        support_messages = log.message_ids.filtered(lambda msg: msg.attachment_ids)
        self.assertTrue(support_messages, 'Monthly log should have a chatter message with attachments.')
        log_attachments = log.attachment_ids.filtered(lambda att: att.res_model == log._name)
        self.assertTrue(log_attachments, 'Log must own copies of the supporting PDF.')
        self.assertTrue(
            all(att.description == log._SUPPORT_ATTACHMENT_DESCRIPTION for att in log_attachments),
            'Supporting attachments should be flagged for safe cleanup.',
        )

    def test_28_billing_log_state_tracks_vendor_bill_payment(self):
        """Monthly log state should follow the vendor bill lifecycle."""
        bill = self._create_vendor_bill(7000.0)
        period_start = fields.Date.from_string('2024-03-01')
        period_end = fields.Date.from_string('2024-03-31')
        log = self.env['rmc.billing.prepare.log'].create({
            'agreement_id': self.agreement.id,
            'bill_id': bill.id,
            'period_start': period_start,
            'period_end': period_end,
            'prime_output_qty': 0.0,
            'optimized_standby_qty': 0.0,
            'mgq_achieved': 0.0,
            'state': 'done',
        })

        bill.action_post()
        self.assertEqual(log.state, 'done', 'Log should remain done for posted, unpaid bills.')

        bill.button_draft()
        self.assertEqual(log.state, 'review', 'Resetting bill to draft should revert log to review.')

        bill.action_post()
        self.assertEqual(log.state, 'done', 'Reposting bill should push log back to Done.')

        self._register_payment_for_bill(bill, amount=bill.amount_residual)
        self.assertEqual(log.state, 'paid', 'Paying the bill should mark the log as paid.')

    def test_29_log_auto_refresh_on_period_change(self):
        """Changing log period should auto-refresh attendance preview."""
        Attendance = self.Attendance
        base_date = fields.Date.from_string('2024-04-01')
        Attendance.create({
            'agreement_id': self.agreement.id,
            'date': base_date,
            'headcount_expected': 7,
            'headcount_present': 5,
            'compliance_percentage': 71.4,
            'state': 'validated',
        })
        Attendance.create({
            'agreement_id': self.agreement.id,
            'date': base_date + timedelta(days=5),
            'headcount_expected': 7,
            'headcount_present': 6,
            'compliance_percentage': 85.7,
            'state': 'validated',
        })
        LogModel = self.env['rmc.billing.prepare.log']
        period_end = base_date + timedelta(days=10)
        log = LogModel._generate_log_for_period(self.agreement, base_date, period_end)
        self.assertIn(str(base_date), log.attendance_preview_html or '', 'Initial preview should include early dates.')

        new_start = base_date + timedelta(days=3)
        log.write({'period_start': new_start})
        refreshed = LogModel.browse(log.id)
        self.assertNotIn(str(base_date), refreshed.attendance_preview_html or '', 'Preview should drop rows outside the new window.')
        self.assertIn(str(base_date + timedelta(days=5)), refreshed.attendance_preview_html or '', 'Preview should retain rows inside the window.')

    def test_30_mgq_achieved_tracks_prime_and_standby(self):
        """MGQ achieved should be Prime + Optimized Standby everywhere."""
        log = self.env['rmc.billing.prepare.log']._generate_log_for_period(
            self.agreement,
            fields.Date.from_string('2024-05-01'),
            fields.Date.from_string('2024-05-31'),
        )
        log.write({'prime_output_qty': 1200.0, 'optimized_standby_qty': 300.0})
        log.flush()
        self.assertEqual(log.mgq_achieved, 1500.0, 'Log snapshot should sum prime + standby for MGQ achieved.')
        wizard_action = log.action_prepare_monthly_bill()
        wizard = self.env['rmc.billing.prepare.wizard'].with_context(wizard_action.get('context', {})).create({})
        self.assertEqual(wizard.mgq_achieved, 1500.0, 'Wizard should reuse the same MGQ sum when opened from log.')
