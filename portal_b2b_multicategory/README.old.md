# Portal B2B Multi-Category

Advanced customer-portal extension for Odoo 19 Enterprise that delivers category-aware dashboards, role filtering and deep Ready-Mix Concrete (RMC) flows for B2B customers.

## Highlights

- **Multi-category dashboards** – Automatically derives `x_portal_categories` from confirmed sales and renders dedicated tabs per product category.
- **Role-aware portal** – Contact roles (`x_portal_role`) gate the quality, logistics and finance sections so each team member only sees what they need.
- **RMC specific experience**
  - Circle-metric snapshot cards with quick links to orders, dispatch and invoices.
  - Each sale order card collapses just like workorders for a tidy overview.
  - Ticket rows open an inline timeline detailing the full RMC journey: Order Confirmed → Ticket Confirmed → Truck Loading → Plant Check → Dispatched → Invoiced → Delivered.
- **Live data sourcing** – Timelines and totals are built from `sale.order`, `dropshipping.workorder`, `dropshipping.workorder.ticket`, `rmc.truck_loading`, `rmc.plant_check`, `rmc.docket` and `account.move`.
- **Bootstrap styling bundle** – Custom SCSS and portal JS (placeholder) included in `web.assets_frontend`.

## Setup & Dependencies

Requires standard Odoo Enterprise apps plus the custom RMC management stack:

```
depends: portal, sale_management, stock, account, rmc_management_system
```

Install like any addon (copy into `custom_addons`, update `addons_path`, restart Odoo, update module list, install module).

## How It Works

1. **Category harvesting** – On SO confirmation (`sale.order.action_confirm`), the mixin adds product categories to the partner’s `x_portal_categories` many2many. Commercial partners push categories to child contacts, ensuring consistent dashboards for the whole company.
2. **Portal entry point** – `/my/b2b-dashboard` renders the tabbed view. Tabs come from `res.partner.get_portal_dashboard_categories()`.
3. **Controller orchestration** – `portal_b2b.py` fetches orders, cross-populates helper payloads, builds ticket timelines and exposes formatting helpers to QWeb.
4. **Helper services** – `portal_helpers.py` centralises business logic: timelines, category KPIs, workorder/ticket lookups and formatting.
5. **Templates** – `portal_templates.xml`
   - Tab navigation & empty-state messages
   - RMC summary card grid with deep links
   - Collapsible order cards with timeline, quality, logistics, finance sections
   - Ticket table with inline flow accordion plus timeline formatting
   - Home portal hook that adds category entries to `/my/home`
   - Inherit of subcontractor ticket page to embed the flow card
6. **Assets** – `portal_dashboard.scss` styles the timeline, card grid and general layout. (The JS file is a stub ready for future interactivity.)

## Configuring Roles

Set the `Portal Role` field on every contact who uses the portal:

- `Team Leader`: full RMC view (quality + logistics + finance)
- `Quality`: access to quality tables/tickets only
- `Logistics`: dispatch info + timeline
- `Finance`: invoice section

## Customising Look & Feel

Adjust `static/src/scss/portal_dashboard.scss` or override the classes in your website theme. The metric cards use `.rmc-metric-grid` selectors; the timeline can be restyled via `.timeline-step`.

## Extending

- **Additional categories** – Extend `get_portal_dashboard_categories` or the helper methods to create tailored widgets per category.
- **Extra timeline steps** – Enhance `prepare_rmc_ticket_timeline` to include more data points; add the matching UI inside the ticket-collapse template.
- **Modal detail view** – If inline collapses are too dense, convert the timeline block to a Bootstrap modal triggered by the same button.

## Support & Notes

- The module relies on the custom RMC domain models (workorders, truck loadings, plant checks). Ensure those modules are installed and data is maintained.
- Timeline steps fall back gracefully when records are absent (e.g. no truck loading yet).
- Update/upgrade the addon after code changes to reload helper logic and assets: `./odoo-bin -u portal_b2b_multicategory --assets`.

Happy portalling! 🚀
