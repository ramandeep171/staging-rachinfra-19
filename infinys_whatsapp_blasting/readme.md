# Infinys WhatsApp Blasting

Mass broadcast add-on for **Odoo 19 Enterprise** that reuses the official WhatsApp module and its infrastructure (Meta Cloud API or WAHA).  
Every place where the UI requests a “WhatsApp Account” is pointing to *WhatsApp ‣ Configuration ‣ WhatsApp Business Accounts* from the standard app—no parallel configuration exists inside this module.

## Menu map (WhatsApp application)

1. **Broadcasts** – Mailings and Mailing Logs (campaign-centric views).  
2. **Contacts** – Contact-centric views: Mailing Lists, Recipients, Incoming, Outgoing.  
   Everything lives inside the default WhatsApp app, so users never leave the native experience.

## Step-by-step setup & usage

### 1. Prerequisites

1. Install **WhatsApp** from Odoo Enterprise and finish Meta/WAHA onboarding until you can send a message from Discuss.  
2. Install this module and upgrade the app list. The WhatsApp menu gains the Broadcasts + Contacts entries described above.  
3. Ensure scheduled actions are running (Odoo cron workers must be active).

### 2. Configure transport (one-time per phone number)

1. Go to *WhatsApp ‣ Configuration ‣ WhatsApp Business Accounts*.  
2. Create or open an account and fill the standard Meta fields.  
3. Scroll to the **Infinys Gateway** section that this module injects and fill:
   - **Provider** – choose `WAHA` for on-prem WAHA or `Meta` to continue using Meta Cloud.
   - **WhatsApp API URL / Webhook URL** – WAHA base URL and the N8n (or similar) webhook that will receive payloads.
   - **Authentication User / Password** – WAHA credentials.
   - **Phone Number ID (WAHA)** – identifier provided by WAHA (defaults to the same phone UID that Odoo requires).  
   - Optional **Welcome Message** template.
4. Click **Test WAHA Credentials** (visible for provider = WAHA) to validate access. Re-use this screen whenever credentials change.
5. Multi-company rules, allowed users, and access rights are inherited from the default WhatsApp configuration.

### 3. Prepare contacts and lists

1. Navigate to *WhatsApp ‣ Contacts ‣ Recipients*.  
2. Create or import contacts (international format, numbers only). The form includes country, tags, and an Incoming/Outgoing history similar to the standard Contacts app.  
3. Build mailing lists from *WhatsApp ‣ Contacts ‣ Mailing Lists* and add contacts to each list.  
4. Use the *Incoming* and *Outgoing* menu items to inspect automatically captured messages and confirm opt-outs.

### 4. Build and schedule a campaign

1. Open *WhatsApp ‣ Broadcasts ‣ Mailings* and click **New**.  
2. Fill the form:
   - **Subject** and **Message/Header/Footer** fields support the placeholders listed in the Variables tab (e.g., `{{contact.name}}`).  
   - **WhatsApp Account** is a direct link to the default WhatsApp configuration; creation/quickedits are disabled to guarantee a single source of truth.  
   - Choose **Recipients** = Mailing List or Manual Contacts.  
   - Select the Mailing List or the Contact records, then set the **Schedule Date** (must be >= current datetime).  
3. Click **Submit to Scheduler** to move the mailing to the queue or **Send Now** to push it immediately.  
4. Use *Broadcasts ‣ Mailing Log* to follow the status. Each log entry references outgoing messages, the WhatsApp account, and any error message returned by WAHA/Meta.

### 5. Monitor traffic

1. *Contacts ‣ Incoming* lists received messages (auto-linked to contacts when possible) so you can react or enrich the database.  
2. *Contacts ‣ Outgoing* shows deliveries triggered by campaigns with metadata such as config account, mailing list, and error messages.  
3. Contact records maintain counters (`Messages Sent`, `Received Messages`) and the `Opt-Out` flag to control future blasts.

### 6. Automation / cron

- **Infinys Whatsapp Blasting : Scheduler Send** – runs every minute; releases mailings whose schedule date has been reached.  
- **Infinys Whatsapp Blasting : Scheduler Enqueue** – disabled by default; enable when you want the system to push queued payloads to WAHA/N8n automatically in batches.

## Tips & troubleshooting

- Keep the WAHA/N8n endpoints reachable from the Odoo server; failed webhooks surface in the Mailing Log’s `Error Message` column.  
- If contact imports fail, double-check that numbers are stripped from spaces/`+` (the form auto-normalises input).  
- Because the module reuses default WhatsApp accounts, any transport-level issue can be debugged from *Discuss > WhatsApp* logs or the standard WhatsApp module tools.
