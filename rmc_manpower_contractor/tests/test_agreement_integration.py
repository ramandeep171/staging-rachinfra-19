# -*- coding: utf-8 -*-
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
