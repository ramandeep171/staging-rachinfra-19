# Diesel Log - Fleet Fuel Management

## Module Overview

| Property | Value |
|----------|-------|
| **Name** | Diesel Log |
| **Technical Name** | `diesel_log` |
| **Version** | 19.0.1.2.0 |
| **Category** | Fleet |
| **Author** | Odoo Expert Developer / SP Nexgen Automind |
| **License** | LGPL-3 |
| **Depends** | base, fleet, mail, stock, hr_attendance |

---

## Purpose (क्या है और क्यों जरूरी है)

यह module **fleet vehicles और equipment के लिए diesel/fuel management का complete system** है।

**क्या करता है?**
- Vehicle या equipment को diesel issue करना (petrol pump से या company tank से)
- Odometer reading automatically track करना
- Fuel efficiency calculate करना (km/liter या hours/liter)
- Fuel short/excess detect करना (चोरी या wastage identification)
- Stock inventory से automatic diesel consume होना
- Equipment के working hours track करना

**क्यों जरूरी है?**
- **Cost Control**: Diesel expense company का बड़ा cost होता है, proper tracking से savings होती है
- **Theft Detection**: जब fuel efficiency suddenly drop हो तो theft या leakage का indication
- **Maintenance Planning**: Fuel efficiency drops indicate करता है कि maintenance जरूरी है
- **Operator Accountability**: Kon operator kitna fuel use kar raha hai - complete visibility
- **Compliance**: Transport department audits के लिए fuel records maintain होते हैं

**Business Impact:**
- 10-15% fuel savings typical (proper monitoring से)
- Unauthorized usage elimination
- Better fleet utilization visibility

---

## Key Features

### Core Features
- **Diesel Issuing**: Track diesel issued to vehicles with automatic inventory management
- **Dual Mode**: Vehicle logs (for fleet) + Equipment logs (for stationary equipment like generators, pumps)
- **Odometer Tracking**: Automatic fleet vehicle odometer updates from diesel logs
- **Fuel Efficiency Calculation**: km/L or hours/L tracking with historical comparison
- **Fuel Short/Excess Detection**: Highlight shortage (possible theft) or excess (faulty meter/calculation)
- **Stock Integration**: Auto-creates stock pickings for fuel consumption
- **Multi-company Support**: Full isolation per company

### Advanced Features
- **Fuel Type Awareness**: Restricts diesel logs to diesel-capable vehicles (not petrol/electric)
- **Odometer Unit Support**: Respects vehicle's km/miles setting
- **Historical Comparison**: Shows old logs for trend analysis
- **Operator Tracking**: Links to HR employees or partners
- **Activity Notifications**: Creates follow-up activities for anomalies
- **Equipment-Specific Logs**: Separate tracking for generators, pumps, compressors

---

## Dependencies

```python
'depends': [
    'base',            # Core Odoo framework
    'fleet',           # Fleet vehicle management
    'mail',            # Chatter and activity tracking
    'stock',           # Inventory management for diesel stock
    'hr_attendance',   # Operator/driver tracking (optional)
]
```

---

## Main Models

### 1. `diesel.log` - Main Diesel Log

**Purpose**: Records each diesel issuance to a vehicle

| Field Name | Type | Description |
|------------|------|-------------|
| `name` | Char | Log reference (auto-sequence: DL/YYYY/NNNN) |
| `date` | Datetime | When fuel was issued |
| `log_type` | Selection | 'vehicle' or 'equipment' |
| `vehicle_id` | Many2one(fleet.vehicle) | Vehicle receiving fuel |
| `fuel_qty` | Float | Quantity issued (liters) |
| `last_odometer` | Float | Previous odometer reading |
| `current_odometer` | Float | Current odometer reading |
| `odometer_unit` | Selection | 'kilometers' or 'miles' |
| `odometer_difference` | Float | Computed: current - last |
| `odometer_difference_display` | Char | Human-readable with unit |
| `fuel_efficiency` | Float | Current avg efficiency (km/L or hr/L) |
| `current_efficiency` | Float | Expected fuel for this trip |
| `fuel_short` | Float | Short/Excess = Expected - Actual |
| `fuel_short_excess_display` | Html | Color-coded display (red=short, green=excess) |
| `operator_id` | Many2one(res.partner) | Driver or operator |
| `employee_id` | Many2one(hr.employee) | Driver employee record |
| `picking_id` | Many2one(stock.picking) | Generated stock picking |
| `state` | Selection | draft → confirmed → done → cancel |
| `notes` | Text | Additional remarks |
| `old_log_ids` | One2many | Historical logs for comparison |

**Computed Logic:**

```python
# Odometer usage
odometer_difference = current_odometer - last_odometer

# Current efficiency (what fuel SHOULD have been used)
current_efficiency = odometer_difference * vehicle.fuel_efficiency

# Fuel shortage/excess
fuel_short = current_efficiency - fuel_qty
# Positive = Shortage (less fuel used than expected - possible theft)
# Negative = Excess (more fuel used - wastage or inaccurate reading)

# Update vehicle average efficiency
new_avg_efficiency = odometer_difference / fuel_qty
vehicle.fuel_efficiency = (old_avg * 0.7) + (new_avg * 0.3)  # Weighted average
```

**State Workflow:**
```
draft → confirmed → done
           ↓
        cancel
```

### 2. `diesel.equipment.log` - Equipment Fuel Log

**Purpose**: For stationary or mobile equipment (generators, pumps, excavators)

| Field Name | Type | Description |
|------------|------|-------------|
| `name` | Char | Reference (auto-sequence: DEL/YYYY/NNNN) |
| `date` | Datetime | Log date |
| `diesel_log_id` | Many2one(diesel.log) | Parent vehicle log (if combined) |
| `vehicle_id` | Many2one(fleet.vehicle) | Equipment (stored as fleet vehicle) |
| `hours_worked` | Float | Equipment run hours |
| `fuel_used` | Float | Fuel consumed (liters) |
| `output_qty` | Float | Production output (e.g., concrete m³, water pumped) |
| `operator_id` | Many2one(res.partner) | Equipment operator |
| `state` | Selection | draft → in_progress → done → cancel |
| `note` | Text | Notes |

**Use Cases:**
- Generator: hours_worked=8, fuel_used=25L, output_qty=200 kWh
- Concrete Pump: hours_worked=6, fuel_used=30L, output_qty=150 m³
- Excavator: hours_worked=10, fuel_used=80L, output_qty=500 m³ earth

---

### 3. `fleet.vehicle` (inherited)

**Purpose**: Extended with fuel management fields

| Added Field | Type | Description |
|-------------|------|-------------|
| `fuel_efficiency` | Float | Average efficiency (km/L or hr/L) |
| `diesel_log_ids` | One2many | All diesel logs for this vehicle |
| `diesel_log_count` | Integer | Count for smart button |
| `total_fuel_consumed` | Float | Lifetime fuel consumption |
| `last_fuel_date` | Datetime | Last fueling date |
| `odometer_at_last_fuel` | Float | Odometer at last fueling |

**Smart Buttons:**
- **Diesel Logs**: View all fuel logs
- **Add Fuel**: Quick diesel log creation

---

### 4. `res.config.settings` (inherited)

**Purpose**: Global diesel module configuration

| Added Field | Type | Description |
|-------------|------|-------------|
| `diesel_product_id` | Many2one(product.product) | Default diesel product |
| `fuel_operation_type_id` | Many2one(stock.picking.type) | Stock picking type for fuel issues |

**Default Values (Auto-Created):**
- Product: "Diesel" (unit: Liters)
- Operation Type: "Fuel Issue"
  - Source: "Fuel Tank" (internal location)
  - Destination: "Fuel Consumption" (virtual location for consumption)

---

### 5. `stock.picking` (created automatically)

**Purpose**: Each confirmed diesel log creates a stock picking

**Flow:**
```
Diesel Log Confirmed
      ↓
Stock Picking Created
  Source: Fuel Tank
  Dest: Fuel Consumption
  Product: Diesel
  Qty: fuel_qty
      ↓
Stock Move Created
      ↓
Picking Validated
      ↓
Inventory Updated
```

---

## How It Works (Workflow Diagrams)

### Vehicle Diesel Issuing Flow

```
┌─────────────────┐
│  Vehicle Arrives│  Driver comes to fuel pump
│  for Refueling  │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ Pump Operator Opens │
│ Fleet → Add Fuel    │
└────────┬────────────┘
         │
         ▼
┌─────────────────────────────┐
│ System Auto-Fills:          │
│ - Last Odometer: 12450 km   │
│ - Vehicle Avg: 8.5 km/L     │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Operator Enters:            │
│ - Current Odometer: 12600   │
│ - Fuel Qty: 20 L            │
│ - Driver: Ramesh Kumar      │
└────────┬────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│ System Calculates:           │
│ - Distance: 150 km           │
│ - Expected Fuel: 17.6 L      │
│ - Actual Fuel: 20 L          │
│ - Shortage: -2.4 L (EXCESS!) │
│ - New Avg: 7.5 km/L          │
└────────┬─────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ Operator Clicks "Confirm"   │
└────────┬────────────────────┘
         │
         ▼
┌────────────────────────────────┐
│ System Actions:                │
│ 1. Update vehicle odometer    │
│ 2. Update vehicle efficiency  │
│ 3. Create stock picking        │
│ 4. Consume diesel from stock  │
│ 5. If shortage > threshold:   │
│    → Create activity/alert    │
└────────┬───────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Log State: Done     │
│ Vehicle Can Leave   │
└─────────────────────┘
```

### Fuel Efficiency Tracking

```
Historical Average: 8.5 km/L
New Trip: 150 km, 20 L used
New Efficiency: 7.5 km/L

Updated Average (Weighted):
= (8.5 * 0.7) + (7.5 * 0.3)
= 5.95 + 2.25
= 8.2 km/L

Why weighted? To smooth out anomalies while still reflecting trends.
```

### Equipment Logging Flow

```
┌──────────────────────┐
│ Generator Operator   │  Night shift operator
│ Completes Shift      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────┐
│ Opens Equipment Log Form │
└──────────┬───────────────┘
           │
           ▼
┌─────────────────────────────┐
│ Enters:                     │
│ - Equipment: DG Set 01      │
│ - Hours Worked: 8 hrs       │
│ - Fuel Used: 24 L           │
│ - Output: 200 kWh generated │
│ - State: Done               │
└──────────┬──────────────────┘
           │
           ▼
┌────────────────────────────┐
│ System Calculates:         │
│ - Efficiency: 3 L/hr       │
│ - Specific Consumption:    │
│   0.12 L/kWh               │
└────────────────────────────┘
```

---

## Controllers/Routes

No web controllers (all backend functionality)

---

## Views & Menus

### Menu Structure

```
Fleet
  └─ Diesel Logs
      ├─ Diesel Logs          (diesel.log list)
      ├─ Equipment Logs       (diesel.equipment.log list)
      └─ Configuration
          ├─ Diesel Product
          └─ Fuel Operation Type
```

### Key Views

1. **Diesel Log List View** (`views/diesel_log_views.xml`)
   - Columns: Date, Vehicle, Fuel Qty, Odometer, Efficiency, Short/Excess, State
   - Color coding: Red for shortage, Green for excess
   - Group by: Vehicle, Driver, Date

2. **Diesel Log Form View**
   - Basic Info: Vehicle, Date, Driver
   - Fuel Details: Quantity, Last/Current Odometer
   - Calculations: Distance, Efficiency, Short/Excess (readonly, highlighted)
   - Stock Info: Related picking
   - Notes section

3. **Equipment Log List & Form** (`views/diesel_log_equipment_views.xml`)
   - Simplified for equipment tracking
   - Focus on hours worked and output

4. **Fleet Vehicle Form** (inherited - `views/fleet_vehicle_views.xml`)
   - New "Fuel Management" tab:
     - Fuel efficiency chart
     - Recent diesel logs
     - Total consumption statistics
   - Smart buttons: Diesel Logs, Add Fuel

5. **Configuration Settings** (`views/res_config_settings_views.xml`)
   - Diesel Log Configuration section in Settings

---

## Security & Access Rights

### Groups

| Group | Technical Name | Description |
|-------|---------------|-------------|
| Diesel User | `diesel_log.group_diesel_user` | Can create/view diesel logs |
| Diesel Manager | `diesel_log.group_diesel_manager` | Full access + configuration |

### Access Rights (`security/ir.model.access.csv`)

| Model | Group | Read | Write | Create | Delete |
|-------|-------|------|-------|--------|--------|
| `diesel.log` | User | ✓ | ✓ | ✓ | ✗ |
| `diesel.log` | Manager | ✓ | ✓ | ✓ | ✓ |
| `diesel.equipment.log` | User | ✓ | ✓ | ✓ | ✗ |
| `diesel.equipment.log` | Manager | ✓ | ✓ | ✓ | ✓ |

### Record Rules

**Multi-Company Rule:**
```python
[('company_id', 'in', user.company_ids.ids)]
```
Ensures users only see logs from their allowed companies.

---

## Configuration/Setup Steps

### 1. Install Module

```bash
./odoo-bin -d your_database -i fleet,stock,diesel_log
```

### 2. Configure Diesel Product (Auto or Manual)

**Option A: Auto-Configuration (Recommended)**
- Module auto-creates on first diesel log
- Product: "Diesel" (unit: L)
- Category: Consumables

**Option B: Manual Configuration**
1. Go to Settings → Diesel Log Configuration
2. Select existing diesel product or create new
3. Save

### 3. Configure Fuel Operation Type (Auto or Manual)

**Auto-Created:**
- Name: "Fuel Issue"
- Code: internal
- Source Location: "Fuel Tank" (internal)
- Destination: "Fuel Consumption" (consumption/production type)

**Manual (if customization needed):**
1. Go to Inventory → Configuration → Operation Types
2. Create or edit "Fuel Issue" type
3. Link in Settings → Diesel Log Configuration

### 4. Set Up Fuel Stock

**Create Fuel Tank Location:**
1. Inventory → Configuration → Locations
2. Create: "Fuel Tank" (Type: Internal, Parent: Physical Locations)

**Initial Fuel Stock:**
1. Inventory → Products → Diesel
2. Update Quantity: Enter initial stock (e.g., 5000 L)

### 5. Configure Fleet Vehicles

1. Go to Fleet → Vehicles
2. For each vehicle:
   - Set Fuel Type: Diesel (important for filtering)
   - Set Odometer Unit: Kilometers or Miles
   - Optionally set initial Fuel Efficiency (system learns over time)

### 6. Assign User Groups

1. Settings → Users & Companies → Users
2. Edit user → Assign:
   - "Diesel User" (for operators)
   - "Diesel Manager" (for supervisors)

---

## Usage Examples

### Example 1: Daily Vehicle Refueling

**Scenario**: Truck driver takes fuel from company pump before starting trip

```
Operator: Pump Attendant
Vehicle: TN 01 AB 1234 (Tata 407)

1. Fleet → Diesel Logs → Create
2. System shows:
   - Last Odometer: 45,230 km (from last log)
   - Vehicle Avg Efficiency: 9.2 km/L

3. Driver says current odometer: 45,380 km
   Operator enters: 45,380

4. System calculates:
   - Distance traveled: 150 km
   - Expected fuel: 150 / 9.2 = 16.3 L

5. Operator dispenses: 18 L (as per driver request)
   System shows: Fuel Excess: -1.7 L (in GREEN - slightly more than expected)

6. Operator selects Driver: Suresh Kumar

7. Clicks "Confirm"
   → Stock picking created (18L consumed from Fuel Tank)
   → Vehicle odometer updated to 45,380
   → New efficiency: (150 / 18) = 8.3 km/L
   → Updated average: (9.2 * 0.7) + (8.3 * 0.3) = 8.93 km/L
```

---

### Example 2: Detecting Fuel Theft

**Scenario**: Unusual fuel consumption pattern detected

```
Normal Pattern for Vehicle MH 12 CD 5678:
- Average: 10 km/L
- Daily logs: Usually 15-20 L per 150-200 km trips

Suspicious Log:
Date: Today
Last Odo: 52,100 km
Current Odo: 52,250 km (150 km trip)
Expected Fuel: 15 L
Actual Fuel Taken: 30 L

System Alert:
Fuel Shortage: -15 L (RED - 100% excess!)

Possible Reasons:
1. Driver taking extra fuel in jerrycan (theft)
2. Fuel tank leak
3. Odometer tampered
4. Incorrect odometer reading entry

Action:
→ System creates Activity for Fleet Manager
→ Manager investigates:
  - Checks vehicle physically
  - Interviews driver
  - Reviews CCTV at pump
  - Checks fuel tank level before/after
```

---

### Example 3: Equipment Logging (Generator)

**Scenario**: Diesel generator running during power outage

```
Equipment: DG Set - 125 KVA (stored as Fleet Vehicle)
Operator: Site Engineer

Shift: Night (8 PM to 6 AM = 10 hours)

Equipment Log Entry:
- Equipment: DG Set 125 KVA
- Hours Worked: 10 hrs
- Fuel Used: 35 L
- Output Generated: 800 kWh
- Operator: Amit Sharma
- State: Done

Calculations:
- Fuel efficiency: 35 / 10 = 3.5 L/hr
- Specific consumption: 35 / 800 = 0.044 L/kWh

Manager's View:
- Can compare with manufacturer spec (usually 0.05 L/kWh for 125 KVA)
- This generator is performing better than spec!
- Track over time to detect deterioration
```

---

## Integration Points (कैसे दूसरे modules के साथ काम करता है)

### 1. **Fleet Module** (`fleet`)
- **Link**: Main data source for vehicles
- **Data Flow**:
  - Diesel log reads vehicle details, odometer
  - Writes back: updated odometer, fuel efficiency
- **Why**: Centralized fleet information

### 2. **Stock/Inventory** (`stock`)
- **Link**: Fuel consumption creates stock moves
- **Data Flow**:
  - Diesel log → Stock picking → Stock move → Inventory updated
- **Why**: Accurate fuel stock management, accounting integration

### 3. **HR Attendance** (`hr_attendance`)
- **Link**: Links operators/drivers to employee records
- **Data Flow**:
  - Can link diesel log to employee
  - Track which employee used how much fuel
- **Why**: Accountability and payroll/allowance calculations

### 4. **Accounting** (via stock)
- **Link**: Stock moves create journal entries
- **Data Flow**:
  - Fuel consumption → COGS (Cost of Goods Sold)
  - Fuel purchases → Inventory asset
- **Why**: Accurate cost accounting

### 5. **Maintenance** (optional, if `maintenance` module installed)
- **Link**: Can trigger maintenance alerts based on fuel efficiency drops
- **Data Flow**:
  - Low efficiency detected → Create maintenance request
- **Why**: Preventive maintenance based on performance indicators

---

## Business Use Cases

### Use Case 1: Fleet Fuel Cost Control
**Challenge**: Transport company with 50 trucks, monthly diesel cost: 15 lakhs

**Solution with Diesel Log:**
1. Daily fuel logging for all vehicles
2. Efficiency tracking per vehicle and driver
3. Automatic alerts for anomalies
4. Monthly reports: vehicle-wise, driver-wise consumption

**Results:**
- Identified 3 vehicles with poor efficiency → Maintenance done → 15% improvement
- Detected 2 drivers with consistent excess consumption → Training provided
- Total savings: 1.5 lakhs/month (10%)

---

### Use Case 2: Construction Site Equipment Management
**Challenge**: Multiple generators, pumps, excavators on site, no fuel accountability

**Solution:**
1. Each equipment registered as fleet vehicle
2. Operators log hours worked and fuel used
3. Output tracked (kWh, m³ concrete, m³ earth moved)
4. Weekly reports generated

**Results:**
- Identified over-fueling by operators (selling excess)
- Optimized equipment usage (right machine for right job)
- Better maintenance scheduling based on hours worked

---

### Use Case 3: Rental Vehicle Fleet
**Challenge**: Renting vehicles to clients, need to bill for fuel accurately

**Solution:**
1. Vehicle goes out: Note odometer
2. Vehicle returns: Create diesel log with start/end odometer
3. System calculates fuel consumed based on efficiency
4. Bill customer for fuel used

**Results:**
- Accurate fuel billing
- No disputes (transparent calculation)
- Better profitability (no fuel losses)

---

## File Structure

```
diesel_log/
├── __init__.py
├── __manifest__.py
├── README.rst                         # Original RST documentation
├── README.md                          # This comprehensive guide
│
├── data/
│   ├── sequence.xml                   # Auto-numbering for diesel logs
│   ├── sequence_equipment_log.xml     # Equipment log sequence
│   └── mail_activity_type.xml         # Activity types for alerts
│
├── models/
│   ├── __init__.py
│   ├── diesel_log.py                  # Main diesel log model
│   ├── diesel_equipment_log.py        # Equipment-specific logs
│   ├── fleet_vehicle.py               # Fleet vehicle extensions
│   ├── res_config_settings.py         # Configuration settings
│   ├── hr_attendance.py               # HR integration (optional)
│   └── stock_picking.py               # Stock picking extensions
│
├── views/
│   ├── diesel_log_views.xml           # Diesel log views and actions
│   ├── diesel_log_equipment_views.xml # Equipment log views
│   ├── fleet_vehicle_views.xml        # Fleet vehicle inherited views
│   ├── diesel_log_menus.xml           # Menu structure
│   ├── hr_attendance_views.xml        # HR attendance extensions
│   └── res_config_settings_views.xml  # Settings configuration view
│
├── wizard/
│   └── (empty or future wizards)
│
├── static/
│   └── description/
│       └── (icons, banner)
│
├── tests/
│   └── (test files)
│
└── security/
    ├── security.xml                   # Groups definition
    └── ir.model.access.csv            # Access rights
```

---

## Technical Notes

### 1. Fuel Efficiency Calculation (Weighted Average)

```python
def _compute_fuel_efficiency(self):
    for rec in self:
        if rec.odometer_difference and rec.fuel_qty:
            new_efficiency = rec.odometer_difference / rec.fuel_qty

            # Update vehicle's average (70% old, 30% new)
            if rec.vehicle_id.fuel_efficiency:
                rec.vehicle_id.fuel_efficiency = \
                    (rec.vehicle_id.fuel_efficiency * 0.7) + \
                    (new_efficiency * 0.3)
            else:
                rec.vehicle_id.fuel_efficiency = new_efficiency
```

**Why weighted average?**
- Smooths out anomalies (one-time events like heavy load, traffic)
- Still reflects recent trends (30% weight to new data)
- Prevents wild swings from single data points

**Alternative: Moving Average (can be implemented)**
```python
# Last 10 logs average
recent_logs = self.env['diesel.log'].search([
    ('vehicle_id', '=', rec.vehicle_id.id),
    ('state', '=', 'done')
], order='date desc', limit=10)

avg_efficiency = sum(log.odometer_difference / log.fuel_qty
                     for log in recent_logs) / len(recent_logs)
```

---

### 2. Fuel Short/Excess Formula

```python
# Expected fuel based on vehicle's average efficiency
expected_fuel = odometer_difference / vehicle.fuel_efficiency

# Actual fuel issued
actual_fuel = fuel_qty

# Shortage/Excess
fuel_short = expected_fuel - actual_fuel

# Interpretation:
# fuel_short > 0  → Shortage (less fuel than expected - theft suspicion)
# fuel_short < 0  → Excess (more fuel than expected - wastage or low efficiency)
# fuel_short ≈ 0  → Normal (within tolerance)
```

**Threshold-based Alerts:**
```python
# Create activity if shortage > 2L or > 20% of expected
if fuel_short > 2.0 or (fuel_short / expected_fuel) > 0.20:
    self.activity_schedule(
        activity_type_id=ref('diesel_log.mail_activity_fuel_shortage'),
        summary='Fuel Shortage Detected!',
        note=f'Expected: {expected_fuel}L, Actual: {actual_fuel}L, Short: {fuel_short}L',
        user_id=rec.vehicle_id.driver_id.user_id.id
    )
```

---

### 3. Stock Picking Creation

```python
def action_confirm(self):
    for rec in self:
        # Get configured product and operation type
        diesel_product = rec.company_id.diesel_product_id
        if not diesel_product:
            diesel_product = self._get_or_create_diesel_product()

        operation_type = rec.company_id.fuel_operation_type_id
        if not operation_type:
            operation_type = self._get_or_create_fuel_operation_type()

        # Create picking
        picking = self.env['stock.picking'].create({
            'picking_type_id': operation_type.id,
            'location_id': operation_type.default_location_src_id.id,
            'location_dest_id': operation_type.default_location_dest_id.id,
            'origin': rec.name,
            'move_lines': [(0, 0, {
                'name': f'Diesel for {rec.vehicle_id.name}',
                'product_id': diesel_product.id,
                'product_uom_qty': rec.fuel_qty,
                'product_uom': diesel_product.uom_id.id,
                'location_id': operation_type.default_location_src_id.id,
                'location_dest_id': operation_type.default_location_dest_id.id,
            })],
        })

        # Validate picking immediately
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()

        rec.picking_id = picking.id
        rec.state = 'done'
```

---

### 4. Odometer Unit Handling (Odoo 19)

```python
def _compute_odometer_difference_display(self):
    for rec in self:
        diff = rec.odometer_difference
        if diff is None or rec.current_odometer == 0:
            rec.odometer_difference_display = _('Waiting...')
        else:
            # Get unit from vehicle or default
            unit = rec.odometer_unit or 'kilometers'
            unit_label = dict(self._fields['odometer_unit'].selection).get(unit, 'km')

            # Format integer if whole number, else 2 decimals
            formatted = f'{int(diff)}' if float(diff).is_integer() else f'{diff:.2f}'

            rec.odometer_difference_display = f'{formatted} {unit_label}'
```

---

### 5. Fuel Type Filtering (Odoo 19)

```python
# In diesel.log model
@api.onchange('vehicle_id')
def _onchange_vehicle_id(self):
    if self.vehicle_id:
        # Auto-fill odometer
        self.last_odometer = self.vehicle_id.odometer
        self.current_odometer = self.vehicle_id.odometer
        self.odometer_unit = self.vehicle_id.odometer_unit

        # Check fuel type
        if self.vehicle_id.fuel_type not in ALLOWED_DIESEL_FUEL_TYPES:
            return {
                'warning': {
                    'title': _('Warning'),
                    'message': _(f'Vehicle {self.vehicle_id.name} uses {self.vehicle_id.fuel_type}, not diesel!')
                }
            }

# In fleet.vehicle domain
@api.model
def _get_diesel_vehicle_domain(self):
    return [('fuel_type', 'in', ['diesel', 'plug_in_hybrid_diesel'])]
```

---

## Troubleshooting

### Issue 1: Fuel Efficiency Shows 0.0

**Cause**: No previous logs or odometer difference is zero

**Fix**:
1. Check if `odometer_difference > 0`
2. Check if `fuel_qty > 0`
3. For first log, manually set vehicle's `fuel_efficiency` field

```python
# Set initial efficiency manually
vehicle.fuel_efficiency = 10.0  # km/L (typical for trucks)
```

---

### Issue 2: Stock Picking Not Created

**Symptoms**: Diesel log confirmed but no picking generated

**Checks**:
1. Diesel product configured? (Settings → Diesel Log Configuration)
2. Fuel operation type configured?
3. Check picking exists: `diesel_log.picking_id`

**Manual Fix**:
```python
# Trigger picking creation manually
diesel_log.action_confirm()
```

---

### Issue 3: "Waiting..." Shown Instead of Odometer Difference

**Cause**: Current odometer not entered or is zero

**Fix**:
1. Ensure `current_odometer > 0`
2. Ensure `current_odometer > last_odometer`

---

### Issue 4: Fuel Short Calculation Incorrect

**Cause**: Vehicle's `fuel_efficiency` not set or outdated

**Fix**:
1. Check vehicle's current fuel efficiency
2. If incorrect, recalculate from recent logs:
   ```python
   recent_logs = self.env['diesel.log'].search([
       ('vehicle_id', '=', vehicle.id),
       ('state', '=', 'done')
   ], order='date desc', limit=10)

   if recent_logs:
       avg = sum(log.odometer_difference / log.fuel_qty for log in recent_logs) / len(recent_logs)
       vehicle.fuel_efficiency = avg
   ```

---

### Issue 5: Multi-Company: Seeing Other Company's Logs

**Cause**: Record rules not applied or user has multiple company access

**Check**:
1. User's allowed companies (Settings → Users → Allowed Companies)
2. Diesel log's `company_id` field set correctly
3. Record rule active: `diesel_log_company_rule`

**Fix**:
```xml
<!-- Verify record rule in security.xml -->
<record id="diesel_log_company_rule" model="ir.rule">
    <field name="name">Diesel Log Multi-Company</field>
    <field name="model_id" ref="model_diesel_log"/>
    <field name="domain_force">[('company_id', 'in', company_ids)]</field>
</record>
```

---

## Version History

### 19.0.1.2.0 (Current)
- Added equipment logging (`diesel.equipment.log`)
- Enhanced fuel efficiency tracking with weighted averages
- Fuel short/excess detection with activity alerts
- Odoo 19 compatibility: Fuel type filtering, odometer unit support
- Multi-company enhancements

### 19.0.1.1.0
- Added stock integration
- Configuration settings page
- Fleet vehicle extensions

### 19.0.1.0.0
- Initial release for Odoo 19
- Basic diesel logging
- Odometer tracking
- Simple fuel efficiency calculation

---

## Support & Customization

**Maintainer**: Odoo Expert Developer / SP Nexgen Automind

**Common Customizations:**
1. Add GPS integration for odometer readings
2. RFID/barcode scanner integration for vehicle identification
3. Mobile app for field operators
4. Advanced analytics dashboards
5. Integration with fuel pump dispensers
6. SMS/WhatsApp alerts for anomalies
7. Fuel card integration (if using third-party fuel cards)
8. Route tracking integration (Google Maps API)

---

**End of Documentation**
