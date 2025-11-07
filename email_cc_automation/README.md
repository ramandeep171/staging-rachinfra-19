# Email CC Configuration for Odoo

This module extends Odoo’s email workflow by letting administrators configure **global default CC recipients** for business documents.  

With this module, companies can ensure that certain partners (e.g. a shared mailbox, compliance team, or manager) are always copied on outgoing transactional emails.

---

## ✨ Features

- **Global CC toggle**  
  Enable/disable global CC recipients from *Settings → General Settings*.

- **Partner selection**  
  Select one or more `res.partner` records (must have an email) as global CC recipients.

- **Automatic CC population**  
  If enabled, the chosen partners are automatically added to the **CC field** when sending:
  - Invoices & Credit Notes
  - Sales Quotations & Confirmations
  - Purchase Orders & Requests for Quotation
  - Stock Pickings (Shipping Emails)

- **Fallback behavior**  
  If the feature is disabled or no partners are selected, the CC field falls back to the responsible user:
  - Salesperson for Sales Orders
  - Buyer for Purchase Orders
  - Invoice User for Invoices
  - Responsible User for Pickings

---

## 📧 Covered Email Templates

This module ensures that global CC partners (when enabled) are applied to the following standard templates:

- **Journal Entries**
  - Credit Note: Sending  
  - Invoice: Sending  

- **Sales Orders**
  - Sales: Send Quotation  
  - Sales: Order Confirmation  

- **Purchase Orders**
  - Purchase: Purchase Order  
  - Purchase: Request For Quotation  

- **Stock Transfers**
  - Shipping: Send by Email  

---

## ⚙️ Configuration

1. Go to **Settings → General Settings → Email CC**.
2. Tick **Enable Custom Partner**.
3. Select one or more partners (only contacts with valid emails can be chosen).
4. Save.
5. In order to use the CC field in Stock Transfers templates enable **Email Confirmation**, go to, **Inventory > Configuration > Settings > Shipping**. 

From now on, all supported email flows will include those partners in CC.

---

## 🔄 Technical Details

- Global settings are stored in `ir.config_parameter` under:
  - `email_cc_automation.enable_custom_partner`
  - `email_cc_automation.custom_partner_ids` (comma-separated partner IDs)
- All affected wizards (`account.move.send`, `mail.compose.message`, `validate.picking.email`) check these parameters in `default_get()`.
- CC partners are injected into the wizard’s `cc_email_partner_ids` before sending.

---

## 🛠️ Compatibility

- Depends on `mail` and standard business apps (`sale`, `purchase`, `account`, `stock`).
- Validated on Odoo 19.0. The upstream Sales Order Cancellation wizard was removed in this release, so CC automation now applies to the remaining email flows listed above.

---

## 📄 License

LGPL-3.0 or later
