# RMC Commission Agent

Commission lifecycle management for Ready-Mix Concrete (RMC) sales channels,
complete with a dedicated partner portal and channel-aware metrics.

---

## 1. Feature Highlights

- Multi-channel commission agents (`rmc.commission.agent`) with regional tags.
- Implicit commission master suggestion based on channel and geography.
- Sales Order enrichment: delivered volume, recovery rate, retention bonuses.
- Automated portal onboarding for agent partners with configurable ACLs.
- Portal dashboards (`/my/commission`, `/my/commission/orders`) tailored per
  channel, including KPIs, tables, and empty-state guidance.
- Auto-generated commission vouchers: once an order hits 100% commission
  release, a draft payout voucher is created and exposed on the portal.

---

## 2. Architecture Overview

| Component                               | Purpose                                                    |
|-----------------------------------------|------------------------------------------------------------|
| `models/commission_agent.py`            | Agent definition, portal bridge, helper methods.           |
| `models/sale_order.py`                  | Commission fields and onchange helpers on sale orders.     |
| `controllers/portal.py`                 | Portal routes, layout values, access guards.               |
| `views/commission_agent_views.xml`      | Backend tree/form/search views.                            |
| `views/portal_templates.xml`            | Portal cards, dashboards, and table templates.             |
| `security/*.xml` , `ir.model.access.csv`| Groups, ACLs, and record rules for portal users.           |
| `data/demo_data.xml`                    | Sample agents and orders (optional demo load).             |

---

## 3. Prerequisites

### Functional
- Odoo 19 (Community or Enterprise) with database initialized.
- Company contacts for the agents you plan to onboard.

### Module Dependencies
- `sale`, `sale_management`, `stock`, `account`, `portal`, `contacts`, `mail`.

### Access & Credentials
- Technical user with rights to install custom modules.
- Portal users must have valid email addresses for automated invitations.

---

## 4. Installation (Fresh Deploy)

1. **Activate environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Run database migrations (if any core updates pending)**
   ```bash
   ./odoo-bin -c odoo.conf -d <db> -u base
   ```
3. **Install dependencies** (if not already present)
   ```bash
   ./odoo-bin -c odoo.conf -d <db> -i sale,sale_management,stock,account,portal,contacts,mail
   ```
4. **Install the module**
   ```bash
   ./odoo-bin -c odoo.conf -d <db> -i rmc_commission_agent
   ```
5. **(Optional) Load demo data**
   ```bash
   ./odoo-bin -c odoo.conf -d <db> -i rmc_commission_agent --load=web,base,rmc_commission_agent
   ```

---

## 5. Upgrade / Reinstallation

1. Pull latest code.
2. Restart the Odoo service to avoid cached controller/templates.
3. Run module upgrade:
   ```bash
   ./odoo-bin -c odoo.conf -d <db> -u rmc_commission_agent
   ```
4. Review existing agents (default channel `rmc_dropshipping`) and adjust the
   `agent_type` / commission master assignments as needed.
5. For legacy agents, toggle the `Active` field to trigger portal user sync.

---

## 6. Post-Installation Checklist (Step-by-Step)

1. **Verify security groups**
   - Navigate to *Settings ▸ Users & Companies ▸ Groups*.
   - Open **Commission Agent Portal** and confirm intended users are listed.
2. **Configure commission masters**
   - Go to *Sales ▸ Commissions ▸ Commission Masters*.
   - Create a record with country tag and channel scope.
3. **Create or update agents**
   - Menu: *Sales ▸ Commissions ▸ Commission Agents*.
   - Link to a partner (ensure email present).
   - Choose channel (`agent_type`), review suggested master.
4. **Provision portal access**
   - On the agent form, check the chatter log for auto-created portal users.
   - Resend invitations via *Action ▸ Send Portal Access* if necessary.
5. **Validate portal dashboard**
   - Log in as the portal user (incognito window).
   - Confirm the **Commission Dashboard** tile appears on `/my/home`.
   - Visit `/my/commission` and `/my/commission/orders` to verify data.

---

## 7. Detailed Configuration Guides

### 7.1 Commission Masters
1. Create master records with `country_tag`.
2. Set `applicable_channel` to limit visibility or leave blank for all.
3. Optionally preload commission formulas or notes to guide agents.

### 7.2 Commission Agents
1. Create agent and link to the commercial partner.
2. Optionally accept the suggested commission master or choose manually.
3. Review channel-specific fields (rental period, retention bonuses, etc.).
4. Save to trigger `portal.mixin` synchronization and group assignment.

### 7.3 Sales Order Integration
1. Open a sales order and set `Commission Agent`.
2. Observe auto-populated channel info and suggested master.
3. Capture channel KPIs (delivered volume, recovery rate, etc.) per order.

---

## 8. Portal Usage

| Route                     | Description                                               |
|---------------------------|-----------------------------------------------------------|
| `/my/commission`          | Overview dashboard with agent profile and KPIs.          |
| `/my/commission/orders`   | Paginated list of sales orders tied to the agent.        |
| `/my`                     | Portal home; tile visible only for authorized agents.    |

### Portal Guardrails
- Anonymous visitors are redirected to `/web/login?redirect=…`.
- Internal users without the portal group are redirected to `/my`.
- Missing agents show an informative warning page.

---

## 9. Data & Security Model

- **Groups**
  - `rmc_commission_agent.group_portal_commission_agent`: toggles portal access.
- **Record Rules**
  - Agents and Sale Orders limited to the user’s commercial partner hierarchy.
- **Access Controls**
  - Portal users (`share = True`) receive read-only access to agent data.
- **Tokens & URLs**
  - `portal.mixin` ensures each agent record has a shareable portal URL.

---

## 10. Troubleshooting Guide

| Symptom                              | Resolution                                                   |
|-------------------------------------|--------------------------------------------------------------|
| 403 Forbidden on `/my/commission`   | Ensure user belongs to `group_portal_commission_agent`.      |
| Tile missing on portal home         | Verify portal user isn’t internal and has a linked agent.    |
| Dashboard empty                     | Confirm sale orders have `commission_agent_id` set.          |
| Missing translations                | `request.env._` used in templates; install desired languages.|
| Duplicate portal users              | Merge partners before activating agents to avoid duplicates. |

---

## 11. Development & Maintenance

1. **Code Quality**
   ```bash
   ruff check custom_addons/rmc_commission_agent
   ```
2. **Testing**
   - Add functional tests under `rmc_commission_agent/tests/`.
   - Use `./odoo-bin -c odoo.conf -d <db> --test-tags rmc_commission_agent`.
3. **Commit Style**
   - Follow `[TYPE] module: summary` (e.g., `[ADD] rmc_commission_agent: portal guard`).
4. **Asset Reload Issues**
   - Run `./fix_file_watchers.sh` on Linux when live reload stalls.

---

## 12. FAQ

- **Can internal users view the dashboard?**  
  Yes, add them to the portal group and ensure a linked agent exists.

- **How are portal logins generated?**  
  When an agent is created or the partner is updated, `portal.mixin`
  provisions a portal user (random password, email invitation).

- **Is multi-company supported?**  
  Yes, provided commercial partner hierarchies are maintained per company.

- **Where do I customize the dashboard layout?**  
  Edit `views/portal_templates.xml` targeting `portal_agent_dashboard`
  or extend it from another module.

---

## 13. References

- Odoo portal mixin docs: `odoo/addons/portal/models/portal_mixin.py`
- Core portal templates: `addons/portal/views/portal_templates.xml`
- Related custom modules: `rmc_management_system`, `portal_b2b_multicategory`
