# HR Job Responsibility Module

## Communication Surface Inventory
- **Email template**: `mail_template_jr_issue` (JR issue notification with PDF attachment) triggered from `jr.employee.jr.action_issue_to_employee`.
- **Chatter events**:
  - Auto-generation notice when a JR is created from a template.
  - Issuance log on state change to `issued`.
  - Acknowledgement log on state change to `acknowledged`.
  - Email outcomes logged for missing templates, missing work emails, sandbox suppression/rerouting, and send failures.
- **Issuance trigger**: Manual button on JR form or via smart button from employee form that calls `action_issue_to_employee`.
- **Automatic send logic**: `mail_template_jr_issue.send_mail` invoked per JR with PDF attachment when a valid recipient is available.

## Sandbox Mode Design
- Controlled via system parameters:
  - `jr.email_sandbox.enabled` (`true`/`false`), default `false`.
  - `jr.email_sandbox.allowed_domains` (comma-separated list, e.g., `example.com,test.local`).
  - `jr.email_sandbox.redirect_to` (single email used when recipient domain is not allowlisted).
- Behaviour:
  - When disabled: email sends to the employee work email.
  - When enabled:
    - If the employee email domain is allowlisted, send normally.
    - Otherwise, reroute to `jr.email_sandbox.redirect_to` if configured.
    - If no redirect is configured, suppress the send and log the suppression to chatter.
- Safe recipients: keep a single shared sandbox mailbox in `jr.email_sandbox.redirect_to` and explicitly list any approved domains in `jr.email_sandbox.allowed_domains`.

## Error Handling & Logging
- Missing template: chatter note “JR issue email template missing; email not sent.”
- Missing work email: chatter note “No work email on employee; JR issue email not sent.”
- Sandbox suppression: chatter note detailing the suppression reason.
- Sandbox reroute: chatter note indicating original and redirected recipients.
- Mail failure: chatter note with the exception message; workflow continues.

## QA Test Scenarios
1. **Create employee → Auto JR generation**
   - Create an employee with job and company; confirm a JR is created in Draft and chatter logs auto-generation.
2. **Issue JR → Email send (sandbox enabled)**
   - Set parameters: `jr.email_sandbox.enabled=true`, `jr.email_sandbox.redirect_to=test@example.com`.
   - Click “Issue to Employee”; expect chatter log for issuance and reroute note; email sent to `test@example.com` with PDF attachment name `JR_<employee>.pdf`.
3. **Issue JR → Email suppressed (sandbox, no redirect)**
   - Set `jr.email_sandbox.enabled=true`, clear `jr.email_sandbox.redirect_to`, set `allowed_domains` to a domain that does not match the employee email.
   - Click “Issue to Employee”; expect chatter log that email was suppressed; no outgoing mail.
4. **Issue JR → Missing template**
   - Uninstall or archive the mail template; issuance should still change state and log missing template.
5. **Acknowledge JR**
   - Click “Mark as Acknowledged”; expect chatter log only, no email.

## Test Commands (run in real Odoo environment)
- Install/upgrade: `odoo-bin -d <sandbox_db> -u hr_job_responsibility`
  - Validates module loads, data files, views, reports, and email template.
- Tests (if added later): `python3 -m pytest hr_job_responsibility/tests`
  - Runs automated coverage for JR generation, issuance, acknowledgement, and security.
