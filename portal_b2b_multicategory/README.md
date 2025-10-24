# Portal B2B Multi-Category - Advanced Customer Portal

## Module Overview

| Property | Value |
|----------|-------|
| **Name** | Portal B2B Multi Category |
| **Technical Name** | `portal_b2b_multicategory` |
| **Version** | 19.0.1.0.0 |
| **Category** | Portal |
| **Author** | SmarterPeak |
| **License** | LGPL-3 |
| **Depends** | portal, sale_management, stock, account |

---

## Purpose (क्या है और क्यों जरूरी है)

यह module B2B customers के लिए **advanced, multi-category portal dashboard** बनाता है - especially RMC (Ready-Mix Concrete) business के लिए optimized।

**क्या करता है?**
- Product categories के basis पर portal automatically organize होता है
- Different roles (Quality, Logistics, Finance) के लिए different views
- RMC orders की complete timeline tracking (order → dispatch → delivery → invoice)
- Work orders और tickets की detailed status tracking
- Circle metric cards with quick stats और deep links

**क्यों जरूरी है?**
- **B2B Complexity**: B2B customers को multiple products, categories chahiye - single view confusing हो जाता है
- **Role-Based Access**: Quality team को sirf quality data, Logistics को dispatch data - unnecessary clutter nahi
- **RMC-Specific Needs**: Concrete delivery में real-time tracking critical है (fresh concrete time-sensitive)
- **Self-Service**: Customers खुद portal पर sab kuch track कर सकते हैं - less calls, less emails
- **Professional Image**: Advanced portal = Professional company impression

**Standard Odoo Problem:**
- Default portal सबको same view दिखाता है
- No product category organization
- RMC business की specific needs (truck loading, plant checks) address nahi होतीं
- Timeline tracking basic है

---

## Key Features

### Multi-Category Dashboard
- Automatic category tabs from confirmed sales
- Each category gets dedicated view
- Empty state handling for categories without orders

### Role-Based Access Control
- **Team Leader**: Full access (Quality + Logistics + Finance)
- **Quality**: Quality tables, test results only
- **Logistics**: Dispatch info, delivery tracking
- **Finance**: Invoices, payments

### RMC-Specific Features
- Order → Workorder → Ticket → Truck Loading → Plant Check → Delivery flow
- Interactive timeline with status indicators
- Collapsible cards for clean UI
- Metric cards with counts and quick links
- Real-time data from multiple models

### Integration
- Sale Order integration
- Workorder & Ticket tracking
- Truck Loading records
- Plant Check records
- Docket management
- Invoice display

---

## Main Models & Fields

### 1. `res.partner` (inherited)

| Added Field | Type | Description |
|-------------|------|-------------|
| `x_portal_categories` | Many2many(product.category) | Product categories from confirmed orders |
| `x_portal_role` | Selection | Portal role (team_leader/quality/logistics/finance) |

**Key Methods:**
- `add_portal_categories(categories)`: Add categories to partner
- `get_portal_dashboard_categories()`: Get portal categories sorted
- `get_portal_role_key()`: Get role string for templates

### 2. `sale.order` (inherited in helper)

Auto-adds product categories to partner on order confirmation.

### 3. `portal.b2b.helper` (Model)

Helper model with business logic methods:
- `get_partner_orders(partner, category, limit)`: Fetch orders by category
- `get_order_workorders(order)`: Get workorders for order
- `prepare_order_timeline(order)`: Build order timeline
- `prepare_rmc_ticket_timeline(ticket)`: Build RMC delivery timeline

---

## How It Works (Workflow)

### Category Auto-Assignment

```
Sale Order Created
        ↓
Order Confirmed (action_confirm)
        ↓
System extracts product categories from order lines
        ↓
Categories added to partner.x_portal_categories
        ↓
Categories pushed to commercial partner + child contacts
        ↓
Portal dashboard shows tabs for each category
```

### Portal Dashboard Flow

```
Customer logs into portal
        ↓
System checks partner.x_portal_categories
        ↓
Finds categories: [RMC, Steel, Cement]
        ↓
Dashboard renders 3 tabs
        ↓
Customer selects "RMC" tab
        ↓
Controller fetches:
  - Orders in RMC category
  - Workorders for those orders
  - Tickets for workorders
  - Truck loadings for tickets
  - Plant checks
  - Invoices
        ↓
Template renders:
  - Summary metrics (Total Orders, Delivered, Pending, Invoiced)
  - Order cards (collapsible)
  - Each order shows workorders
  - Each workorder shows tickets
  - Each ticket shows timeline
```

### RMC Timeline Steps

```
Order Confirmed → Workorder Created → Ticket Created →
Truck Loading (Plant) → Plant Check → Dispatched →
In Transit → Delivered → Invoice Generated → Payment Received
```

Each step shows:
- Icon (✓ complete, ⏱ pending, ✗ failed)
- Timestamp
- Responsible person/department
- Additional notes

---

## Controllers & Routes

### Main Route: `/my/b2b-dashboard`

**Controller**: `portal_b2b.py` → `PortalB2BCustomerPortal`

**Parameters:**
- `category_id` (optional): Selected category ID

**Method**: `portal_b2b_dashboard()`

**Flow:**
```python
def portal_b2b_dashboard(self, category_id=None, **kwargs):
    contact_partner = request.env.user.partner_id
    categories = contact_partner.get_portal_dashboard_categories()

    # Detect RMC categories
    rmc_categories = categories.filtered(lambda c: 'rmc' in c.name.lower())

    # Select category (from param or first available)
    selected_category = self.env['product.category'].browse(category_id) if category_id else categories[0]

    # Fetch orders for selected category
    orders = helper.get_partner_orders(contact_partner, category=selected_category)

    # For RMC category, enrich with workorder/ticket data
    if selected_category in rmc_categories:
        for order in orders:
            workorders = helper.get_order_workorders(order)
            for workorder in workorders:
                tickets = workorder.ticket_ids
                # Build timeline for each ticket
                timeline = helper.prepare_rmc_ticket_timeline(ticket)

    # Render template
    return request.render('portal_b2b_multicategory.b2b_dashboard', values)
```

---

## Views & Templates

### Portal Dashboard Template

**File**: `views/portal_templates.xml`

**Structure:**
```xml
<template id="b2b_dashboard">
    <!-- Category Tabs -->
    <ul class="nav nav-tabs">
        <li t-foreach="categories" t-as="cat">
            <a href="/my/b2b-dashboard/{cat.id}">
                <t t-esc="cat.name"/>
            </a>
        </li>
    </ul>

    <!-- RMC Summary Cards (if RMC category) -->
    <div class="rmc-metric-grid" t-if="is_rmc_category">
        <div class="metric-card">
            <h3>Total Orders</h3>
            <p class="metric-value"><t t-esc="order_count"/></p>
        </div>
        <div class="metric-card">
            <h3>Delivered</h3>
            <p class="metric-value"><t t-esc="delivered_count"/></p>
        </div>
        <!-- More cards... -->
    </div>

    <!-- Order Cards -->
    <div class="order-cards">
        <div t-foreach="orders" t-as="order" class="order-card">
            <div class="card-header" data-toggle="collapse" data-target="#order_{order.id}">
                <h4><t t-esc="order.name"/> - <t t-esc="order.partner_id.name"/></h4>
                <span class="badge"><t t-esc="order.state"/></span>
            </div>
            <div id="order_{order.id}" class="collapse">
                <!-- Quality Tab (if role allows) -->
                <div t-if="role in ['team_leader', 'quality']">
                    <h5>Quality</h5>
                    <table class="table">
                        <tr t-foreach="order.order_line" t-as="line">
                            <td><t t-esc="line.product_id.name"/></td>
                            <td><t t-esc="line.product_uom_qty"/></td>
                        </tr>
                    </table>
                </div>

                <!-- Logistics Tab (if role allows) -->
                <div t-if="role in ['team_leader', 'logistics']">
                    <h5>Logistics</h5>
                    <!-- Workorders & Tickets -->
                    <div t-foreach="workorders" t-as="wo">
                        <h6><t t-esc="wo.name"/></h6>
                        <div t-foreach="wo.tickets" t-as="ticket">
                            <button data-toggle="collapse" data-target="#timeline_{ticket.id}">
                                View Timeline
                            </button>
                            <div id="timeline_{ticket.id}" class="collapse">
                                <div class="timeline">
                                    <div t-foreach="ticket.timeline" t-as="step" class="timeline-step">
                                        <span class="timeline-icon" t-att-class="step.status"/>
                                        <div class="timeline-content">
                                            <strong><t t-esc="step.label"/></strong>
                                            <p><t t-esc="step.timestamp"/></p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Finance Tab (if role allows) -->
                <div t-if="role in ['team_leader', 'finance']">
                    <h5>Finance</h5>
                    <table class="table">
                        <tr t-foreach="order.invoice_ids" t-as="invoice">
                            <td><t t-esc="invoice.name"/></td>
                            <td><t t-esc="invoice.amount_total"/></td>
                            <td><t t-esc="invoice.payment_state"/></td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
    </div>
</template>
```

### Portal Home Extension

Adds category links to `/my/home`:

```xml
<template id="portal_my_home_extend">
    <xpath expr="//div[@id='o_portal_docs']" position="inside">
        <t t-if="portal_b2b_category_count">
            <div class="col-12 col-md-6">
                <a href="/my/b2b-dashboard">
                    <span class="fa fa-th-large"/>
                    <span>Multi-Category Dashboard</span>
                    <span class="badge"><t t-esc="portal_b2b_category_count"/> Categories</span>
                </a>
            </div>
        </t>
    </xpath>
</template>
```

---

## Security & Access

**Role-Based Visibility:**

```python
# In template
<div t-if="role == 'team_leader' or role == 'quality'">
    Quality section...
</div>

<div t-if="role == 'team_leader' or role == 'logistics'">
    Logistics section...
</div>

<div t-if="role == 'team_leader' or role == 'finance'">
    Finance section...
</div>
```

**Data Access:**
- Portal users can only see their own orders (via `portal.group_portal`)
- RMC subcontractor portal group auto-assigned for RMC categories
- No backend access - all through portal routes

---

## Configuration Steps

### 1. Install Module

```bash
./odoo-bin -d database -i portal_b2b_multicategory
```

### 2. Configure Partner Roles

1. Go to Contacts → Select B2B customer contact
2. Set field **"Portal Role"**:
   - Team Leader (full access)
   - Quality (quality data only)
   - Logistics (dispatch/delivery)
   - Finance (invoices only)
3. Save

### 3. Grant Portal Access

Settings → Users → Select portal user → Grant portal access

### 4. Confirm Sales Orders

Categories auto-populate when orders are confirmed.

### 5. Test Portal

1. Login as portal user
2. Go to `/my` → See "Multi-Category Dashboard"
3. Click to see categories
4. Select RMC category
5. View orders, workorders, timelines

---

## Usage Examples

### Example 1: RMC Customer Tracking Delivery

**User**: Site Engineer (Logistics role)
**Scenario**: Track concrete delivery in real-time

```
1. Login to portal
2. Go to Multi-Category Dashboard
3. Select "RMC" tab
4. See metric: "5 Orders in Transit"
5. Click on Order SO001
6. Expand Logistics section
7. See Workorder WO/0001 with 3 tickets
8. Click "View Timeline" on Ticket TKT-001
9. Timeline shows:
   ✓ Order Confirmed - 10:00 AM
   ✓ Ticket Created - 10:15 AM
   ✓ Truck Loading - 10:45 AM (Truck: TN01AB1234)
   ✓ Plant Check - 11:00 AM (Slump: 150mm, OK)
   ✓ Dispatched - 11:15 AM
   ⏱ In Transit - ETA 12:00 PM
   ⏳ Delivered - Pending
   ⏳ Invoiced - Pending
10. Site engineer sees truck is 15 mins away, prepares site
```

---

### Example 2: Finance Team Checking Invoices

**User**: Accountant (Finance role)
**Scenario**: Review pending invoices

```
1. Login to portal
2. Multi-Category Dashboard → RMC
3. Sees only "Finance" section (other sections hidden due to role)
4. Summary card shows: "8 Pending Invoices"
5. Clicks card → Lists all pending invoices
6. Can download invoice PDFs
7. Can see payment terms, due dates
8. Makes payment, marks as paid
```

---

### Example 3: Quality Manager Reviewing Test Results

**User**: QC Manager (Quality role)
**Scenario**: Check cube test results for project

```
1. Portal → RMC Dashboard
2. Sees "Quality" section only
3. Order SO005 - ABC Construction Project
4. Quality tab shows:
   - M25 RMC: 100 m³ ordered
   - Cube Tests:
     - 7-day: 18.5 MPa (Pass)
     - 28-day: 31.2 MPa (Pass)
   - Slump tests: All within range
5. Downloads test certificates
6. Shares with client
```

---

## Integration Points

### 1. **Sale Management** (`sale_management`)
- Orders drive category assignment
- Order data displayed in portal
- Order timeline tracking

### 2. **RMC Management System** (`rmc_management_system`)
- Workorders, tickets, dockets
- Truck loading records
- Plant checks
- Delivery tracking
- Complete RMC-specific data

### 3. **Stock/Inventory** (`stock`)
- Delivery orders
- Picking status
- Stock moves

### 4. **Accounting** (`account`)
- Invoice display
- Payment status
- Financial data per order

---

## File Structure

```
portal_b2b_multicategory/
├── __manifest__.py
├── README.md                          # Original brief doc
├── README_COMPREHENSIVE.md            # This detailed guide
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── res_partner.py                 # Category & role fields
│   ├── portal_helpers.py              # Business logic helpers
│   └── sale_order.py                  # SO confirmation hook
├── controllers/
│   ├── __init__.py
│   └── portal_b2b.py                  # Main dashboard controller
├── views/
│   └── portal_templates.xml           # QWeb templates
├── data/
│   └── (any demo/default data)
├── security/
│   └── ir.model.access.csv            # Access rights
└── static/src/
    ├── js/
    │   └── portal_dashboard.js        # Frontend JS (stub)
    └── scss/
        └── portal_dashboard.scss      # Dashboard styles
```

---

## Technical Notes

### 1. Category Detection Logic

```python
@staticmethod
def _is_rmc_category(category):
    if not category:
        return False
    name = (category.name or '').strip().lower()
    return 'rmc' in name or 'ready mix' in name
```

Simple keyword matching - can be extended for other patterns.

---

### 2. Timeline Builder

```python
def prepare_rmc_ticket_timeline(ticket):
    steps = []

    # Step 1: Order Confirmed
    if ticket.workorder_id.sale_order_id:
        steps.append({
            'label': 'Order Confirmed',
            'timestamp': ticket.workorder_id.sale_order_id.date_order,
            'status': 'complete' if ticket.workorder_id.sale_order_id.state == 'sale' else 'pending',
            'icon': 'fa-check-circle',
        })

    # Step 2: Ticket Created
    steps.append({
        'label': 'Ticket Created',
        'timestamp': ticket.create_date,
        'status': 'complete',
        'icon': 'fa-file-text',
    })

    # Step 3: Truck Loading (if exists)
    truck_loading = env['rmc.truck_loading'].search([('ticket_id', '=', ticket.id)], limit=1)
    if truck_loading:
        steps.append({
            'label': f'Truck Loading ({truck_loading.vehicle_id.name})',
            'timestamp': truck_loading.loading_time,
            'status': 'complete',
            'icon': 'fa-truck',
        })

    # Step 4: Plant Check
    plant_check = env['rmc.plant_check'].search([('ticket_id', '=', ticket.id)], limit=1)
    if plant_check:
        steps.append({
            'label': f'Plant Check (Slump: {plant_check.slump}mm)',
            'timestamp': plant_check.check_time,
            'status': 'pass' if plant_check.result == 'ok' else 'fail',
            'icon': 'fa-clipboard-check',
        })

    # ... more steps

    return steps
```

---

### 3. Role-Based Filtering

```python
# In controller
def portal_b2b_dashboard(self, **kwargs):
    contact_partner = request.env.user.partner_id
    role = contact_partner.get_portal_role_key()

    values = {
        'role': role,
        'can_view_quality': role in ['team_leader', 'quality'],
        'can_view_logistics': role in ['team_leader', 'logistics'],
        'can_view_finance': role in ['team_leader', 'finance'],
    }

    return request.render(..., values)
```

---

## Customization Ideas

1. **Add More Categories**: Extend beyond RMC (Steel, Cement, Equipment)
2. **Custom Metrics**: Add category-specific KPIs
3. **Export Functions**: PDF/Excel download of timelines
4. **Notifications**: Email/SMS alerts on delivery status changes
5. **Mobile Optimization**: PWA for field use
6. **Multi-Language**: Hindi/regional language support
7. **Integration**: GPS tracking, IoT sensors for real-time data

---

## Version History

**19.0.1.0.0** - Initial Odoo 19 release

---

## Support

**Author**: SmarterPeak
**Support**: Contact via SmarterPeak channels

---

**End of Documentation**
