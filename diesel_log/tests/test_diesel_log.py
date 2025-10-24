# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError
from odoo import fields


class TestDieselLog(TransactionCase):
    
    def setUp(self):
        super(TestDieselLog, self).setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Test Company',
        })
        
        # Create vehicle model with diesel fuel type (required in Odoo 19)
        self.vehicle_brand = self.env['fleet.vehicle.model.brand'].create({
            'name': 'Test Brand',
        })
        self.vehicle_model = self.env['fleet.vehicle.model'].create({
            'name': 'Test Model',
            'brand_id': self.vehicle_brand.id,
            'vehicle_type': 'car',
            'default_fuel_type': 'diesel',
        })

        # Create test vehicle
        self.vehicle = self.env['fleet.vehicle'].create({
            'name': 'Test Vehicle',
            'license_plate': 'TEST-001',
            'odometer': 50000,
            'company_id': self.company.id,
            'model_id': self.vehicle_model.id,
            'fuel_type': 'diesel',
        })
        
        # Create test product
        self.diesel_product = self.env['product.product'].create({
            'name': 'Test Diesel',
            'type': 'product',
            'uom_id': self.env.ref('uom.product_uom_litre').id,
            'uom_po_id': self.env.ref('uom.product_uom_litre').id,
            'company_id': self.company.id,
        })
        
        # Create test locations
        self.source_location = self.env['stock.location'].create({
            'name': 'Test Fuel Tank',
            'usage': 'internal',
            'company_id': self.company.id,
        })
        
        self.destination_location = self.env['stock.location'].create({
            'name': 'Test Fuel Consumption',
            'usage': 'consumption',
            'company_id': self.company.id,
        })
        
        # Create test warehouse
        self.warehouse = self.env['stock.warehouse'].create({
            'name': 'Test Warehouse',
            'code': 'TW',
            'company_id': self.company.id,
        })
        
        # Create test operation type
        self.operation_type = self.env['stock.picking.type'].create({
            'name': 'Test Fuel Issue',
            'code': 'outgoing',
            'warehouse_id': self.warehouse.id,
            'default_location_src_id': self.source_location.id,
            'default_location_dest_id': self.destination_location.id,
            'sequence_code': 'TFI',
            'company_id': self.company.id,
        })
        
        # Set configuration parameters
        self.env['ir.config_parameter'].sudo().set_param(
            f'diesel_log.diesel_product_id.{self.company.id}', 
            self.diesel_product.id
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'diesel_log.fuel_operation_type_id.{self.company.id}', 
            self.operation_type.id
        )
        self.shortage_activity_type = self.env.ref('diesel_log.mail_activity_type_fuel_shortage')
        self.env['ir.config_parameter'].sudo().set_param(
            f'diesel_log.shortage_activity_type_id.{self.company.id}',
            self.shortage_activity_type.id
        )
        self.env['ir.config_parameter'].sudo().set_param(
            f'diesel_log.shortage_activity_user_id.{self.company.id}',
            self.env.user.id
        )
    
    def test_diesel_log_creation(self):
        """Test basic diesel log creation"""
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'product_id': self.diesel_product.id,
            'company_id': self.company.id,
        })
        
        self.assertTrue(diesel_log.name.startswith('DL'))
        self.assertEqual(diesel_log.state, 'draft')
        self.assertEqual(diesel_log.vehicle_id, self.vehicle)
        self.assertEqual(diesel_log.quantity, 50.0)
        self.assertEqual(diesel_log.current_odometer, 50500)
        self.assertEqual(diesel_log.last_odometer, 50000)  # From vehicle odometer
        self.assertEqual(diesel_log.odometer_difference, 500)
    
    def test_diesel_log_onchange_vehicle(self):
        """Test onchange method for vehicle_id"""
        diesel_log = self.env['diesel.log'].with_company(self.company).new({
            'vehicle_id': self.vehicle.id,
        })
        diesel_log._onchange_vehicle_id()
        self.assertEqual(diesel_log.last_odometer, self.vehicle.odometer)
    
    def test_quantity_validation(self):
        """Test quantity validation constraint"""
        with self.assertRaises(ValidationError):
            self.env['diesel.log'].with_company(self.company).create({
                'vehicle_id': self.vehicle.id,
                'quantity': -10.0,
                'current_odometer': 50500,
                'company_id': self.company.id,
            })
        
        with self.assertRaises(ValidationError):
            self.env['diesel.log'].with_company(self.company).create({
                'vehicle_id': self.vehicle.id,
                'quantity': 0.0,
                'current_odometer': 50500,
                'company_id': self.company.id,
            })
    
    def test_odometer_validation(self):
        """Test odometer reading validation constraint"""
        with self.assertRaises(ValidationError):
            self.env['diesel.log'].with_company(self.company).create({
                'vehicle_id': self.vehicle.id,
                'quantity': 50.0,
                'current_odometer': 49000,  # Less than vehicle's current odometer
                'company_id': self.company.id,
            })
    
    def test_fuel_efficiency_computation(self):
        """Test fuel efficiency computation"""
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,  # 500 km difference
            'company_id': self.company.id,
        })
        
        # 50 liters per 500 km = 10 L/100km
        expected_efficiency = (50.0 / 500.0) * 100
        self.assertEqual(diesel_log.fuel_efficiency, expected_efficiency)
    
    def test_diesel_log_confirmation(self):
        """Test diesel log confirmation process"""
        # Add stock to source location
        self.env['stock.quant'].create({
            'product_id': self.diesel_product.id,
            'location_id': self.source_location.id,
            'quantity': 1000.0,
        })
        
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'product_id': self.diesel_product.id,
            'company_id': self.company.id,
        })
        
        # Confirm the diesel log
        diesel_log.action_confirm()
        
        # Check state
        self.assertEqual(diesel_log.state, 'done')
        
        # Check picking creation
        self.assertTrue(diesel_log.picking_id)
        self.assertEqual(diesel_log.picking_id.picking_type_id, self.operation_type)
        self.assertEqual(diesel_log.picking_id.state, 'done')
        
        # Check vehicle odometer update
        self.assertEqual(self.vehicle.odometer, 50500)
    
    def test_default_product_configuration(self):
        """Test default product ID retrieval"""
        config = self.env['res.config.settings'].with_company(self.company)
        product_id = config._get_diesel_product_id()
        self.assertEqual(product_id, self.diesel_product.id)
    
    def test_default_operation_type_configuration(self):
        """Test default operation type ID retrieval"""
        config = self.env['res.config.settings'].with_company(self.company)
        operation_type = config._get_fuel_operation_type_id()
        self.assertEqual(operation_type, self.operation_type)
    
    def test_fleet_vehicle_extensions(self):
        """Test fleet vehicle model extensions"""
        # Create some diesel logs
        diesel_log1 = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 40.0,
            'current_odometer': 50400,
            'state': 'done',
            'date': fields.Datetime.now(),
            'company_id': self.company.id,
        })
        
        diesel_log2 = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 45.0,
            'current_odometer': 50900,
            'state': 'done',
            'date': fields.Datetime.now(),
            'company_id': self.company.id,
        })
        
        # Refresh to compute fields
        self.vehicle.invalidate_cache()
        
        # Test computed fields
        self.assertEqual(self.vehicle.diesel_log_count, 2)
        self.assertEqual(self.vehicle.total_fuel_consumed, 85.0)
        self.assertGreater(self.vehicle.average_fuel_efficiency, 0)
    
    def test_smart_button_actions(self):
        """Test smart button actions"""
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'company_id': self.company.id,
        })
        
        # Test vehicle diesel logs action
        action = self.vehicle.action_view_diesel_logs()
        self.assertEqual(action['res_model'], 'diesel.log')
        self.assertEqual(action['domain'], [('vehicle_id', '=', self.vehicle.id)])
        
        # Test create diesel log action
        action = self.vehicle.action_create_diesel_log()
        self.assertEqual(action['res_model'], 'diesel.log')
        self.assertEqual(action['context']['default_vehicle_id'], self.vehicle.id)

    def test_vehicle_fuel_type_constraint(self):
        """Ensure non-diesel vehicles cannot create diesel logs."""
        gasoline_model = self.env['fleet.vehicle.model'].create({
            'name': 'Gasoline Model',
            'brand_id': self.vehicle_brand.id,
            'vehicle_type': 'car',
            'default_fuel_type': 'gasoline',
        })
        gasoline_vehicle = self.env['fleet.vehicle'].create({
            'name': 'Gasoline Vehicle',
            'license_plate': 'GAS-001',
            'odometer': 1000,
            'company_id': self.company.id,
            'model_id': gasoline_model.id,
            'fuel_type': 'gasoline',
        })

        with self.assertRaises(ValidationError):
            self.env['diesel.log'].with_company(self.company).create({
                'vehicle_id': gasoline_vehicle.id,
                'quantity': 20.0,
                'current_odometer': 1200,
                'company_id': self.company.id,
            })

    def test_shortage_activity_scheduling(self):
        """Ensure shortage activities are scheduled on finalize and cleared when resolved."""
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'vehicle_avg_fuel_eff_per_hr': 0.05,
            'company_id': self.company.id,
        })

        diesel_log.action_request()
        diesel_log.action_approve()
        diesel_log.action_confirm()

        activities = diesel_log.activity_ids.filtered(
            lambda act: act.activity_type_id == self.shortage_activity_type
        )
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities.user_id, self.env.user)
        self.assertEqual(activities.summary, 'Review fuel shortage')

        diesel_log.write({'vehicle_avg_fuel_eff_per_hr': 0.2})
        open_activities = diesel_log.activity_ids.filtered(
            lambda act: act.activity_type_id == self.shortage_activity_type and act.state != 'done'
        )
        self.assertFalse(open_activities)

    def test_unlink_restrictions(self):
        """Test deletion restrictions"""
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'company_id': self.company.id,
        })
        
        # Should be able to delete draft record
        diesel_log.unlink()
        
        # Create another and confirm it
        diesel_log = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'company_id': self.company.id,
            'state': 'done',
        })
        
        # Should not be able to delete confirmed record
        with self.assertRaises(UserError):
            diesel_log.unlink()
    
    def test_company_isolation(self):
        """Test multi-company data isolation"""
        # Create another company
        company2 = self.env['res.company'].create({
            'name': 'Test Company 2',
        })
        
        # Create diesel log in first company
        diesel_log1 = self.env['diesel.log'].with_company(self.company).create({
            'vehicle_id': self.vehicle.id,
            'quantity': 50.0,
            'current_odometer': 50500,
            'company_id': self.company.id,
        })
        
        # Switch to second company and search
        diesel_logs_company2 = self.env['diesel.log'].with_company(company2).search([])
        
        # Should not see diesel log from first company
        self.assertNotIn(diesel_log1, diesel_logs_company2)
