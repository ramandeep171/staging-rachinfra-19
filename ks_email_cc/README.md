# Email CC & BCC (Odoo 18)

Adds CC / BCC (partners + raw emails) support to the chatter composer and displays those values on messages.

Maintained by **SP Nexgen Automind**.

## Features
- Configure visibility and defaults per company:
  - Toggle fields: CC (emails), BCC (emails), Reply-To, Email To, Partner CC/BCC groups
  - Default CC / BCC / Reply-To values
- Wizard enhancements (`mail.compose.message`):
  - Partner CC & BCC (Many2many) with tag widget
  - Raw email CC & BCC fields
  - Optional Reply-To + explicit To field
- Message display (QWeb extension of `mail.Message`)
- JS patches (OWL models) to inject extra fields and context flag (`ks_from_button`) so only selected recipients are mailed
- Mail sending override to inject CC/BCC directly into outgoing `mail.mail`

## Installation
1. Copy module folder `ks_email_cc` into your Odoo 18 addons path.
2. Update app list.
3. Install module "Email Cc and Bcc".

## Usage
1. Go to Settings > Companies > (Your Company) > Mail Compose Settings tab to configure visibility and defaults.
2. Open any record with chatter, click Send Message / Log Note (Send Message for emailing) to see CC/BCC options.
3. Add partners or raw emails; they will be persisted in the message and mail queues.

## Technical Notes
- Assets: declared via `assets` key in `__manifest__.py` (old `web.assets_backend` inherit XML removed).
- JS uses legacy `registerClassPatchModel` / `registerFieldPatchModel`. If Odoo refactors mail JS models, adapt imports to new service modules.
- Python override `_send` in `mail.mail` kept minimal; upstream changes in future minors may require diff review.
- Extra message fields added so OWL renderer can access them without additional RPC.

### Migration / Naming
The technical field and file prefixes still use `ks_` from the original publisher. For stability (existing databases, exported data, external integrations) they are kept unchanged. If you need fully rebranded technical names, plan a separate migration script to rename database columns, XML IDs, and JS/QWeb references.

## Potential Future Adjustments
- Replace direct `_send` override with extensibility hooks if Odoo 18.x introduces them.
- Add access group restrictions for seeing BCC (currently always shown if stored; you may hide in QWeb for non-admins).

## License
LGPL-3

