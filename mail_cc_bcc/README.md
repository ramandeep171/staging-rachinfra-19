# Mail CC & BCC Module for Odoo 18

## Overview
This module extends Odoo's mail functionality to support CC (Carbon Copy) and BCC (Blind Carbon Copy) recipients in emails.

## Features
- **CC Field**: Add carbon copy recipients to emails who will be visible to all recipients
- **BCC Field**: Add blind carbon copy recipients to emails who will be hidden from other recipients
- **Mail Composer Integration**: CC and BCC fields are available in the email composer wizard
- **Email Tracking**: View CC and BCC recipients in sent emails

## Installation
1. Copy the `mail_cc_bcc` folder to your Odoo addons directory
2. Update the addons list in Odoo
3. Install the module from Apps menu

## Usage
1. Open any email composer in Odoo (e.g., from a lead, opportunity, or invoice)
2. You'll see two new fields:
   - **CC**: Enter email addresses separated by commas
   - **BCC**: Enter email addresses separated by commas
3. Compose your message and send
4. CC and BCC recipients will receive the email accordingly

## Technical Details
- **Models Extended**:
  - `mail.compose.message`: Added email_cc and email_bcc fields
  - `mail.mail`: Added email_cc and email_bcc fields with send logic

- **Views**:
  - Mail composer form view extended with CC/BCC fields
  - Mail tree and form views extended to display CC/BCC

## Dependencies
- mail

## Version
- Odoo 18.0
- Module Version: 1.0.0

## License
LGPL-3

## Author
Your Company
