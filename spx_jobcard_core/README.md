# SPX Job Card Core - Unified Maintenance Management

## Module Overview

| Property | Value |
|----------|-------|
| **Name** | SPX Job Card Core (Plant + Fleet) |
| **Technical Name** | `spx_jobcard_core` |
| **Version** | 19.0.1.0.0 |
| **Category** | Maintenance |
| **Author** | SP Nexgen Automind |
| **License** | LGPL-3 |

**Dependencies**: base, maintenance, fleet, hr, account, stock, web

---

## Purpose (क्या है और क्यों जरूरी है)

यह module **plant equipment और fleet vehicles के लिए unified maintenance job card system** है।

**क्या करता है?**
- Maintenance requests से automatic job cards create होते हैं
- Emergency breakdowns के लिए instant job card generation
- Costs tracking (labor, parts, external services)
- LOTO (Lock Out Tag Out) compliance
- SLA tracking
- Production loss calculation
- Vendor bill synchronization
- SOP gate (procedure compliance before job start)
- Spare parts management with stock integration

**क्यों जरूरी है?**
- **Unified System**: Plant equipment (generators, pumps, mixers) और vehicles (trucks, excavators) - ek hi system में
- **Cost Control**: Labor, parts, external vendor costs - complete tracking
- **Compliance**: LOTO procedures mandatory for safety
- **Downtime Reduction**: Fast emergency response with auto-job creation
- **Accountability**: Who did what, when, at what cost - complete audit trail
- **Planning**: Preventive vs corrective maintenance analysis

---

## Key Features

### Job Card Management
- Auto-creation from maintenance requests (especially emergency)
- Manual creation option
- State workflow: draft → planned → in_progress → done → validated
- Priority levels: Low, Medium, High, Critical

### Cost Tracking
- Labor costs (by technician, hours worked)
- Spare parts costs (from stock or purchases)
- External vendor costs (subcontractor services)
- Total cost calculation and reporting

### LOTO Integration
- Lock out procedures before job start
- Tag out verification
- Safety checklist enforcement
- Photo/document attachment for compliance

### SLA Management
- Response time tracking (request to job start)
- Resolution time tracking (job start to completion)
- SLA breach alerts
- Performance metrics

### Production Loss Calculation
- Equipment downtime duration
- Production rate impact
- Financial loss estimation
- Reporting for management

### Spare Parts Integration
- Maintenance request spare lines
- Auto-create stock picking for spare issues
- Spare consumption tracking
- Inventory replenishment alerts

### Vendor Bill Sync
- Link vendor bills to job cards
- Cost verification
- Payment tracking
- Automatic reconciliation

---

## Main Models

### 1. `maintenance.jobcard` - Main Job Card

**Key Fields:**
- `request_id`: Linked maintenance request
- `type`: preventive/corrective/emergency
- `priority`: 1(low) to 4(critical)
- `equipment_id`: Plant equipment or fleet vehicle
- `technician_ids`: Assigned technicians (Many2many hr.employee)
- `vendor_id`: External service provider
- `planned_hours`: Estimated time
- `actual_hours`: Actual time spent
- `downtime_start`, `downtime_end`: Production loss period
- `state`: draft/planned/in_progress/done/validated
- `total_cost`: Labor + Parts + Vendor
- `loto_checklist_id`: LOTO procedure record
- `sla_response_time`, `sla_resolution_time`: SLA tracking

**Key Methods:**
- `action_plan()`: Move to planned state
- `action_start()`: Start job, record time
- `action_complete()`: Complete job
- `action_validate()`: Final validation
- `_compute_total_cost()`: Calculate all costs

### 2. `maintenance.request` (inherited)

**Added Fields:**
- `spx_kind`: preventive/corrective/emergency
- `spare_line_ids`: One2many(maintenance.request.spare)
- `spare_picking_id`: Auto-created stock picking for spares

**Auto-Job Creation:**
```python
@api.model_create_multi
def create(self, vals_list):
    recs = super().create(vals_list)
    for req in recs:
        if req.spx_kind == 'emergency':
            # Auto-create job card with preferred vendor
            vendor = req.equipment_id.x_preferred_vendor_id
            self.env['maintenance.jobcard'].create({
                'request_id': req.id,
                'type': 'emergency',
                'priority': '3',  # High
                'vendor_id': vendor.id,
            })
    return recs
```

### 3. `maintenance.request.spare` - Spare Parts Lines

- `request_id`: Parent request
- `product_id`: Spare part product
- `qty`: Required quantity
- `uom_id`: Unit of measure
- `description`: Part description

### 4. `jobcard.spares` - Job Card Spare Parts

- `jobcard_id`: Parent job card
- `product_id`: Spare used
- `qty_used`: Actual quantity
- `cost`: Spare cost
- Links to stock move for inventory update

### 5. `checklist` - LOTO/Procedure Checklists

- `name`: Checklist name
- `checklist_type`: LOTO/SOP/Quality
- `line_ids`: Checklist items
- Template-based for consistency

### 6. `jobcard.checklist.link` - Checklist Assignment

- `jobcard_id`: Job card
- `checklist_id`: Checklist template
- `completed`: Boolean (all items checked?)
- `completion_date`: When completed

---

## How It Works

### Emergency Job Card Flow

```
Equipment Breaks Down
        ↓
Operator Creates Maintenance Request (Kind: Emergency)
        ↓
System Auto-Creates Job Card:
  - Type: Emergency
  - Priority: High
  - Vendor: Equipment's preferred vendor (if configured)
        ↓
Maintenance Manager Receives Notification
        ↓
Assigns Technicians → Job Card moves to Planned
        ↓
Technician Starts Job → Checks LOTO Checklist
        ↓
All LOTO items verified → Job moves to In Progress
        ↓
Spare Parts Issued (Auto-creates stock picking)
        ↓
Work Completed → Technician marks Done
        ↓
Manager Validates → Reviews:
  - Hours worked
  - Spares used
  - Costs incurred
        ↓
Job Card Validated → Equipment back in service
        ↓
Vendor Bill Received → Linked to Job Card
        ↓
Cost reconciliation complete
```

### Cost Calculation

```python
# Labor Cost
labor_cost = Σ (technician.hourly_rate * hours_worked)

# Spare Parts Cost
spare_cost = Σ (spare.product_id.standard_price * spare.qty_used)

# Vendor Cost
vendor_cost = vendor_bill.amount_total

# Total Cost
total_cost = labor_cost + spare_cost + vendor_cost

# Production Loss
if downtime_start and downtime_end:
    downtime_hours = (downtime_end - downtime_start).total_seconds() / 3600
    production_loss = downtime_hours * equipment.production_rate * product_value
```

---

## Configuration Steps

1. **Install**: `./odoo-bin -d db -i spx_jobcard_core`
2. **Configure Equipment**: Add maintenance.equipment for plant assets
3. **Configure Fleet**: Existing fleet.vehicle records automatically available
4. **Set Preferred Vendors**: On equipment form, set x_preferred_vendor_id
5. **Create Checklists**: LOTO procedures, SOP checklists
6. **Configure Costs**: Technician hourly rates, spare part costs
7. **Set SLA Targets**: Response and resolution time targets

---

## Usage Examples

### Example 1: Emergency Breakdown

```
Concrete Mixer Breaks Down
↓
Operator: Maintenance Request
  - Equipment: Mixer 01
  - Kind: Emergency
  - Description: "Motor overheating, burning smell"
↓
System: Auto-creates Job Card #JC001
  - Priority: High
  - Vendor: ABC Motors (preferred)
↓
Manager: Assigns 2 technicians
↓
Technicians: Start job, complete LOTO
  - Lock out power supply
  - Tag out control panel
  - Verify zero energy
↓
Diagnosis: Motor bearing failure
↓
Spare Issue:
  - Motor bearing: 1 unit
  - Coupling: 1 unit
  - System creates stock picking, deducts from inventory
↓
Repair Complete: 4 hours
↓
Validation:
  - Labor: 2 techs × 4 hrs × ₹500/hr = ₹4,000
  - Spares: ₹8,500
  - Vendor: ₹0 (in-house)
  - Total: ₹12,500
↓
Downtime: 4 hours
Production Loss: 4 hrs × 20 m³/hr × ₹4,000/m³ = ₹3,20,000
```

### Example 2: Preventive Maintenance

```
Schedule: Monthly PM for Fleet Vehicle TN01AB1234
↓
Maintenance Request Created:
  - Kind: Preventive
  - Due Date: 15th of month
↓
Job Card Created (manual/automatic)
↓
Checklist:
  - ✓ Engine oil change
  - ✓ Air filter replacement
  - ✓ Brake inspection
  - ✓ Tire pressure check
  - ✓ Battery check
↓
Spares Used:
  - Engine Oil 15W40: 8 liters
  - Oil Filter
  - Air Filter
↓
Completion: 2 hours
Cost: ₹3,500 (all spares)
↓
Next PM Scheduled: +1 month
```

---

## Integration Points

- **Maintenance**: Core maintenance request workflow
- **Fleet**: Vehicle maintenance
- **HR**: Technician assignment, cost tracking
- **Stock**: Spare parts inventory
- **Accounting**: Cost tracking, vendor bills
- **Purchase**: Spare parts procurement

---

## Technical Notes

### 1. Auto-Job Creation Logic

Only for emergency requests:
```python
if req.spx_kind == 'emergency':
    Job.create({'type': 'emergency', 'priority': '3'})
```

### 2. Spare Picking Creation

```python
def action_create_spare_picking(self):
    picking = Picking.create({
        'picking_type_id': spare_issue_type.id,
        'origin': self.name,
    })
    for line in self.spare_line_ids:
        Move.create({
            'product_id': line.product_id.id,
            'product_uom_qty': line.qty,
            'picking_id': picking.id,
        })
    picking.action_confirm()
    picking.action_assign()
    return picking
```

### 3. Vendor Bill Linking

Search vendor bills by origin/reference matching job card name.

---

## Business Use Cases

**1. RMC Plant**: Mixer, pump, generator maintenance with downtime tracking
**2. Transport Fleet**: Vehicle PM and repairs with cost per km analysis
**3. Manufacturing**: Production equipment with LOTO compliance
**4. Construction**: Equipment rental maintenance tracking

---

## File Structure

```
spx_jobcard_core/
├── models/
│   ├── jobcard.py                         # Main job card
│   ├── maintenance_request_patch.py       # Request extensions
│   ├── jobcard_spares.py                  # Spare parts
│   ├── checklist.py                       # LOTO/SOP checklists
│   ├── account_move_patch.py              # Vendor bill sync
│   └── equipment_patch.py                 # Equipment extensions
├── views/
│   ├── jobcard_views.xml
│   ├── maintenance_request_views.xml
│   ├── checklist_views.xml
│   └── (more view files)
├── data/
│   ├── ir_sequence.xml                    # Job card numbering
│   └── cron.xml                           # Scheduled jobs
├── security/
│   └── ir.model.access.csv
└── demo/
    └── demo.xml
```

---

## Support

**Author**: SP Nexgen Automind
**Website**: https://example.com

---

**End of Documentation**
