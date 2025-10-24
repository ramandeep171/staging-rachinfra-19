# RMC Management System - Complete Ready-Mix Concrete ERP

## Module Overview

| Property | Value |
|----------|-------|
| **Name** | RMC Management System |
| **Technical Name** | `rmc_management_system` |
| **Version** | 19.0.1.0.0 |
| **Category** | Manufacturing |
| **Author** | RACH INFRA PVT. LTD. |
| **License** | LGPL-3 |

**Core Dependencies**: base, sale, purchase, stock, helpdesk, crm, quality, fleet, account, project, industry_fsm, spx_jobcard_core, mrp, mail, portal, website

---

## Purpose (क्या है और क्यों जरूरी है)

यह module **Ready-Mix Concrete (RMC) business का complete end-to-end management system** है - order से लेकर delivery और invoicing तक।

**क्या करता है?**
- RMC orders, recipes, batching, delivery tracking
- Subcontractor management (plants, transports, assignments)
- Quality control (cube tests, trial mixes, plant checks)
- Weighbridge integration for accurate measurements
- Docket management (delivery tickets)
- Workorder और ticket-based delivery scheduling
- Material balance और inventory tracking
- Portal access for customers and subcontractors
- Automated reporting and reconciliation

**क्यों जरूरी है?**
- RMC business में timing critical है (concrete sets in 90-120 mins)
- Multiple stakeholders coordination (plant, trucks, site, quality)
- Accurate measurement और billing essential (weighbridge records)
- Quality standards compliance (IS 456, cube tests)
- Subcontractor accountability और payment reconciliation

---

## Key Features

### Order Management
- Sale orders with customer cement options
- Product variants by grade (M20, M25, M30, etc.)
- Delivery scheduling and workorder generation
- Ticket-based dispatch management

### Subcontractor Management
- Plant assignments
- Transport (truck/mixer) tracking
- Assignment automation with workorder integration
- Performance tracking and reconciliation

### Quality Control
- Trial mix management (integrated with crm_trial_mix)
- Cube test scheduling (7-day, 28-day)
- Plant checks (slump, temperature, density)
- Quality reports and certificates

### Delivery Tracking
- Docket creation and management
- Truck loading records with timestamps
- Delivery variance tracking
- Real-time status updates
- Portal visibility for customers

### Weighbridge Integration
- Weight capture at entry/exit
- Automatic calculation of delivered quantity
- Material consumption tracking
- Billing reconciliation

### Reporting & Analytics
- Consolidated daily/weekly/monthly reports
- Material balance reports
- Subcontractor performance
- Quality compliance reports
- Automated email delivery

---

## Main Models

### Core RMC Models

**1. `rmc.docket`** - Delivery Ticket
- Docket number, date, quantity
- Links to: sale order, workorder, ticket, subcontractor, recipe
- Truck loading और plant check records
- State: draft → in_production → dispatched → delivered

**2. `rmc.batch`** - Concrete Batch Production
- Batch details, recipe, actual vs planned quantities
- Material consumption tracking
- Quality parameters

**3. `rmc.subcontractor`** - Subcontractor Master
- Plants (rmc.subcontractor.plant)
- Transports (rmc.subcontractor.transport)
- Assignment wizard for workorder allocation

**4. `dropshipping.workorder`** - Production Workorder
- Links sale order to production and delivery
- Quantity tracking (ordered, delivered, remaining)
- Multiple tickets per workorder
- State management

**5. `dropshipping.workorder.ticket`** - Delivery Ticket
- Individual delivery scheduling
- Truck assignment
- Delivery tracking
- Invoice integration

**6. `rmc.truck_loading`** - Truck Loading Log
- Vehicle, driver, loading time
- Quantity loaded
- Links to docket/ticket

**7. `rmc.plant_check`** - Quality Plant Check
- Slump test, temperature, density
- Visual inspection
- Pass/Fail status
- Links to docket/batch

**8. `quality.cube.test`** - Compressive Strength Test
- 7-day and 28-day tests
- Sample management (quality.cube.sample)
- Average strength calculation
- Pass/Fail determination

**9. `rmc.delivery.track`** - Delivery Tracking
- GPS/manual tracking
- Arrival confirmation
- Unloading completion
- Customer signature

**10. `rmc.delivery.variance`** - Delivery vs Order Variance
- Ordered quantity vs delivered
- Reasons tracking
- Billing adjustments

---

## How It Works

### Complete RMC Flow

```
Customer Order (SO) → Workorder Created → Tickets Scheduled
                                                ↓
                          Subcontractor Assigned (Plant + Transport)
                                                ↓
                          Recipe Selected (M25, M30, etc.)
                                                ↓
                          Docket Created → Batching Starts
                                                ↓
                          Batch Mixed → Quality Plant Check
                                                ↓
                          Truck Loading → Weighbridge Exit
                                                ↓
                          Dispatch → GPS Tracking
                                                ↓
                          Site Arrival → Unloading
                                                ↓
                          Delivery Confirmation → Weighbridge Entry (return)
                                                ↓
                          Invoice Generation → Payment
                                                ↓
                          Cube Tests (7d, 28d) → Quality Certificate
```

---

## Key Technical Features

### 1. Recipe/BoM Management
- MRP integration for mix designs
- Component tracking (cement, aggregates, water, admixtures)
- Batch calculations based on required quantity

### 2. Weighbridge Integration
- Entry/Exit weight capture
- Net quantity calculation
- Stock move generation
- Material reconciliation

### 3. Portal Features
- Customer portal: Order tracking, quality reports, invoices
- Subcontractor portal: Assigned workorders, docket submission, payment status
- Real-time updates

### 4. Reporting Automation
- Cron jobs for daily/weekly reports
- Email distribution to stakeholders
- Customizable report formats

### 5. Material Balance
- Real-time stock tracking per plant
- Consumption vs delivery reconciliation
- Shortage/excess alerts

---

## Configuration Steps

1. **Install Module**: `./odoo-bin -d db -i rmc_management_system`
2. **Configure Subcontractors**: Add plants and transports
3. **Set Up Products**: RMC grades with categories
4. **Create Recipes**: BoMs for each grade
5. **Configure Quality**: Test types, inspection points
6. **Set Up Weighbridge**: If integrated hardware
7. **Configure Portal**: Enable for customers and subcontractors
8. **Set Up Reporting**: Email templates and cron schedules

---

## Integration Points

- **CRM**: Lead to order conversion, trial mix integration
- **Sales**: Order management, pricing, delivery terms
- **Purchase**: Material procurement from suppliers
- **Stock**: Inventory management, material consumption
- **Fleet**: Vehicle and driver tracking
- **Quality**: Test management, compliance tracking
- **Accounting**: Invoicing, vendor bills, payment reconciliation
- **Project**: Site management, delivery coordination
- **FSM**: Field service for quality checks, customer visits
- **Helpdesk**: Issue tracking, complaint management

---

## Business Use Cases

**1. Large Construction Project**: Multiple deliveries tracked from order to cube test
**2. Subcontractor Performance**: Track on-time delivery, quality compliance
**3. Material Optimization**: Reduce wastage through accurate tracking
**4. Quality Assurance**: Complete audit trail from mixing to strength test
**5. Customer Self-Service**: Portal for tracking and reports

---

## File Structure

```
rmc_management_system/
├── models/           (45+ model files for complete RMC operations)
├── views/            (UI for all models)
├── security/         (Access rights, record rules)
├── data/             (Sequences, cron jobs, mail templates)
├── report/           (PDF reports, QWeb templates)
├── wizard/           (Wizards for assignments, cancellations)
├── controllers/      (Portal routes)
├── scripts/          (Utility scripts)
└── demo/             (Demo data)
```

---

## Support

**Author**: RACH INFRA PVT. LTD.
**Website**: https://rachinfra.com

---

**End of Documentation**
