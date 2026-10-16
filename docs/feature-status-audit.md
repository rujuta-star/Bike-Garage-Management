# Bike Garage feature status audit

**Audit date:** 2026-10-15
**Scope:** Source and security audit updated during Phase 9A. Payment dashboard/resource authorization code and regression tests were changed; no schema, staging/production database, or business data was changed. This status report and `docs/workflow-audit.md` record the findings.

## How to read this report

- **Implemented** means the source contains an end-to-end capability for the stated action. It does not mean it was tested in a live browser or staging.
- **Partially implemented** means some useful parts exist, but meaningful workflow steps, policies, permissions, or verification are missing.
- **Missing** means no working implementation was found for that feature.
- **Not verified** means the source alone cannot establish the feature's runtime or deployment state.
- Frappe website pages are served from the app's `www` directory. The DocType JSON files define database-backed record types; their presence alone does not make a user workflow complete.

## Evidence and environment

Phase 9A validation on the isolated SQLite site passed 48 Frappe integration tests and 147 unit tests (195 total), including 14 focused payment tests. Five Node regression files passed; Python compilation, JavaScript syntax checks, two rendered inline-script checks, parsing of 15 app JSON files, and whitespace checks passed. These are automated checks against the isolated test site, not live browser or staging evidence. No staging/production database was accessed.

The same audit log records a failed read-only staging connection (`Can't create TCP/IP socket (1)`). There is no verified current staging revision, schema state, or production deployment evidence. No MariaDB concurrency run is recorded. Previous user messages reported manual Chrome checks passing for language switching and the profile/avatar menu; that report was not independently repeated in this audit. User-provided Chrome DevTools evidence earlier showed the login API returning HTTP 200 with `No App`; it does not prove the current redirect works in Chrome.

Current Git status shows `bike_garage/hooks.py` modified and numerous app paths and `docs/` untracked, including `bike_garage/stock.py.backup`. This audit did not reset, stage, or otherwise alter them. Since most source is untracked in this working tree, `git diff` alone does not show the full source being audited. No conclusion is made here about which untracked files predate this audit.

## Feature checklist

### 1. Garage registration, approval, and owner accounts

**Status: Partially implemented**

- **What a user can do today:** A guest can submit a garage application. It creates a pending garage request, not an enabled account. An explicitly authorized Platform Super Admin can review, approve, reject, and resend an approval link. An approved applicant can use a one-time, expiring token to create/activate a Website User and Owner membership. The workflow avoids automatically granting Desk access.
- **What remains:** Confirm real email delivery and public registration URL configuration. Define support/recovery for lost or expired links and operational owner-account recovery. The live deployment and email setup are unknown.
- **Automated tests:** Yes. `test_onboarding.py` covers guest requests, validation, approval, one-time completion, expiration, replay, rollback, and login routing; `test_multi_garage_security.py` covers selected onboarding and membership boundaries.
- **Browser/staging:** No current browser or staging verification. Email delivery is specifically unverified.
- **Evidence:** [`api/onboarding.py`](../bike_garage/bike_garage/api/onboarding.py), [`www/register.py`](../bike_garage/www/register.py), [`www/register.html`](../bike_garage/www/register.html), [`www/platform_admin.py`](../bike_garage/www/platform_admin.py), [`test_onboarding.py`](../bike_garage/test_onboarding.py).

### 2. Login, dashboard, and profile

**Status: Partially implemented**

- **What a user can do today:** Frappe's real login form, password handling, CSRF protection, and session flow remain in use. A request-local hook makes direct GET/HEAD `/` resolve to the public landing page even if Frappe role, portal, or global home-page settings point elsewhere. The landing header suppresses the inherited Frappe navbar to avoid a duplicate Login; it has one visible responsive Login entry for Guests and a separate Request garage access action. Authenticated landing pages show a dashboard link only when the server resolves an authorized route. `/garage` still requires one valid active garage membership. After a successful login, the app asks the authenticated server session to resolve `/platform_admin` for the explicit Platform Super Admin role or `/garage` for a Website User with exactly one active membership in an Active garage; ineligible Website Users return to `/`. Verification and server-directed login responses remain with Frappe. The login page keeps Frappe's real accessible email/password form and the existing Bike Garage responsive styles, validation/error feedback, and password toggle. `/me` uses its native Home `/`, authorized Dashboard, and Logout `/logout` links; `/update-profile/<user>` adds Home, authorized Dashboard when available, and the supported Logout route. No Desk access is granted. The public preview remains explicitly fictional and disconnected from live data; no demo auto-login or seeding was added.
- **What remains:** Manually verify root rendering and login/profile navigation in a browser after Chromium dependencies are restored. Verify actual successful and failed sign-ins, session invalidation, verification/password-reset flows, mobile navigation, and dashboard route denial in Chrome. Confirm deployed assets separately; the SQLite test site does not prove staging or production behavior.
- **Automated tests:** Yes. `test_garage_page.py`, `test_ui_language_preferences.py`, `test_onboarding.py`, and `test_garage_login.js` cover source/API behavior and selected routing/menu logic.
- **Browser/staging:** Earlier user report says language switching and the avatar menu passed manual browser checks; not repeated here. Phase 13 browser verification remains blocked because the bundled Chromium cannot load `libnss3.so`, `libnssutil3.so`, `libnspr4.so`, or `libasound.so.2`. No server was started and no browser flow is claimed. Staging remains unreachable per the audit log.
- **Evidence:** [`website.py`](../bike_garage/website.py), [`hooks.py`](../bike_garage/hooks.py), [`www/index.html`](../bike_garage/www/index.html), [`www/index.py`](../bike_garage/www/index.py), [`www/garage.py`](../bike_garage/www/garage.py), [`www/garage.html`](../bike_garage/www/garage.html), [`public/js/garage_login.js`](../bike_garage/public/js/garage_login.js), [`public/css/garage_ui.css`](../bike_garage/public/css/garage_ui.css), [`public/css/landing.css`](../bike_garage/public/css/landing.css), [`api/preferences.py`](../bike_garage/bike_garage/api/preferences.py), [`test_onboarding.py`](../bike_garage/test_onboarding.py), [`test_garage_page.py`](../bike_garage/test_garage_page.py), and [`public/js/test_garage_login.js`](../bike_garage/public/js/test_garage_login.js).

### 3. Customer management

**Status: Partially implemented**

- **What a user can do today:** A garage member can create a customer and view a customer detail page. API reads are scoped to the active garage, and server code derives ownership rather than trusting a submitted garage ID.
- **What remains:** Website update/delete flows, duplicate/merge policy, and role-specific rules for who may create or edit customer records. Existing data quality and deployed permissions have not been checked on staging.
- **Automated tests:** Yes for create, validation, cross-garage isolation, and selected links; no complete browser test or CRUD lifecycle suite.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/customers.py`](../bike_garage/bike_garage/api/customers.py), [`www/customer_new.py`](../bike_garage/www/customer_new.py), [`www/customer_new.html`](../bike_garage/www/customer_new.html), [`www/customer_view.py`](../bike_garage/www/customer_view.py), [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py).

### 4. Bike management

**Status: Partially implemented**

- **What a user can do today:** A member can create and view bikes. Creation requires a customer from the same garage and validates basic registration/model/date/numeric values. The detail query is garage-scoped.
- **What remains:** Update/delete, a confirmed uniqueness rule for registration numbers, and a concurrency-safe duplicate-registration guard. `last_service_date` is stored but is not automatically updated by a completed service workflow.
- **Automated tests:** Yes for creation, validation, same-garage customer linkage, and cross-garage denial. Duplicate submissions and a full bike lifecycle are not established.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/bikes.py`](../bike_garage/bike_garage/api/bikes.py), [`doctype/bg_bike/bg_bike.json`](../bike_garage/bike_garage/doctype/bg_bike/bg_bike.json), [`www/bike_new.py`](../bike_garage/www/bike_new.py), [`www/bike_view.py`](../bike_garage/www/bike_view.py), [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py).

### 5. Job Cards and service workflow

**Status: Partially implemented**

- **What a user can do today:** Members can list and view garage-scoped Job Cards and submit a basic card with customer, optional bike, and problem description. Existing DocType records also support parts, labour, totals, a mechanic text field, and status values. Existing save/delete hooks consume and restore custom stock and create stock-movement audit entries for actual deltas.
- **What remains:** The website create path deliberately does not accept parts. There is no enforced status transition graph, estimate approval/versioning, mechanic assignment relation, customer approval, QC, delivery confirmation, booking workflow, or defined cancellation/refund workflow. Mechanic is free text. `payment_status`/`amount_paid` on Job Cards are not backed by the new BG Sale receipt ledger.
- **Automated tests:** Yes for scoped create/list/detail, child links, stock consumption/restoration, cancellation/re-activation behavior, calculations, and audit rollback. Tests do not establish a full human service lifecycle.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/garage_job_cards.py`](../bike_garage/bike_garage/api/garage_job_cards.py), [`doctype/bg_job_card/bg_job_card.py`](../bike_garage/bike_garage/doctype/bg_job_card/bg_job_card.py), [`doctype/bg_job_card/bg_job_card.json`](../bike_garage/bike_garage/doctype/bg_job_card/bg_job_card.json), [`stock.py`](../bike_garage/stock.py), [`test_garage_job_cards.py`](../bike_garage/test_garage_job_cards.py), [`test_stock_unit.py`](../bike_garage/test_stock_unit.py).

### 6. Spare Parts and inventory catalog

**Status: Partially implemented**

- **What a user can do today:** A member can create a spare-part catalog entry from the website. The server forces initial quantity to zero and validates fields; direct browser-supplied quantity changes are rejected by the stock controller. Dashboard and inventory pages can show the garage's parts and balances.
- **What remains:** Website catalog edit/archive flows and clear rules for who may change commercial fields. Legacy stock quantities and historical opening balances have not been reconciled. This is a custom per-garage stock balance, not ERPNext's stock ledger.
- **Automated tests:** Yes for zero-stock creation, forged stock values, stock validation, and tenant isolation.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/spare_parts.py`](../bike_garage/bike_garage/api/spare_parts.py), [`doctype/bg_spare_part/bg_spare_part.py`](../bike_garage/bike_garage/doctype/bg_spare_part/bg_spare_part.py), [`www/part_new.py`](../bike_garage/www/part_new.py), [`test_inventory.py`](../bike_garage/test_inventory.py), [`test_stock_unit.py`](../bike_garage/test_stock_unit.py).

### 7. Stock receiving, adjustments, and returns

**Status: Partially implemented**

- **What a user can do today:** Authorized Owner, Manager, or Inventory Manager memberships can use `/stock_receive` and its API to record purchase receipts, positive/negative adjustments, and supplier returns. The server validates quantity/cost, derives garage ownership, checks stock cannot go negative, and records before/after values, reason, reference, request key, and movement type. A return is a full return against a same-garage receipt; submitted movements are reversed through audited cancellation. Sale and Job Card stock changes also create source-linked movement records for new operations.
- **What remains:** Concurrent mutation guarantees need real MariaDB/InnoDB testing. Legacy stock history is incomplete and no opening-stock backfill was made. Unit costs are reference only; valuation, COGS, customer returns, partial supplier returns, and formal purchasing/accounting linkage are not implemented. Permission policy for who may view supplier/cost movement history should be confirmed; the history API currently permits any active garage member to query that garage's movement rows.
- **Automated tests:** Yes for receipt/adjustment/return validation, retry behavior, rollback, negative-stock protection, source references, cancellation, and tenant isolation. These ran on SQLite, not concurrent MariaDB.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/inventory.py`](../bike_garage/bike_garage/api/inventory.py), [`stock.py`](../bike_garage/stock.py), [`doctype/bg_stock_movement/bg_stock_movement.py`](../bike_garage/bike_garage/doctype/bg_stock_movement/bg_stock_movement.py), [`www/stock_receive.py`](../bike_garage/www/stock_receive.py), [`test_inventory.py`](../bike_garage/test_inventory.py), [`test_garage_job_cards.py`](../bike_garage/test_garage_job_cards.py), [Phase 7 audit](workflow-audit.md#phase-7-stock-movement-audit-coverage).

### 8. Sales and invoices

**Status: Partially implemented**

- **What a user can do today:** Existing Sales can be listed and opened as garage-scoped invoice details at `/garage?invoice=...`. Direct query loading and in-dashboard selection are implemented. The UI explains that website Sale creation is unavailable. Website Users cannot create/edit/delete Sales through resource permissions. Sale records use the custom stock balance, and source-linked stock audit entries are written for stock-changing Sales.
- **What remains:** There is no website Sale creation workflow. A complete safe sale lifecycle still needs verified stock availability, cancellation/return policy, retry behavior, and operational payment correction/refund behavior. Existing Desk access for System Users depends on deployed DocType permissions and has not been checked on staging. Invoice output is an app preview, not an ERPNext Sales Invoice.
- **Automated tests:** Yes for invoice query handling/navigation, scoped invoice reads, blocked website Sale creation, stock lifecycle, and preservation of the list/detail behavior in source tests.
- **Browser/staging:** Historical Chrome evidence showed `/garage` could be opened manually and the invoice bug had been observed; there is no current browser confirmation of invoice navigation. Staging remains unverified.
- **Evidence:** [`www/garage.html`](../bike_garage/www/garage.html), [`doctype/bg_sale/bg_sale.py`](../bike_garage/bike_garage/doctype/bg_sale/bg_sale.py), [`permissions.py`](../bike_garage/permissions.py), [`test_garage_page.py`](../bike_garage/test_garage_page.py), [`test_garage_invoice_navigation.js`](../bike_garage/public/js/test_garage_invoice_navigation.js), [`test_payments.py`](../bike_garage/test_payments.py).

### 9. Payments, partial payments, and outstanding balances

**Status: Partially implemented**

- **What a user can do today:** The API supports append-only receipts for tracked BG Sales. Amounts use configured currency precision, reject zero/invalid/excess amounts, and support partial and full payment. Status and paid balance derive from receipt rows; exact retry keys are idempotent and changed payload reuse is rejected. Owner, Manager, and Accountant memberships can record/read payment entries through authorized APIs. Existing Sales are marked/displayed Unverified when their historical status has no reliable ledger evidence. Sale deletion and reducing the total below recorded payments are blocked.
- **What remains:** There is no payment-entry UI because refund/reversal policy is unresolved. Refunds, reversals, chargebacks, payment reconciliation for legacy Sales, and reconciliation evidence are missing. Phase 9A verified and fixed the dashboard authorization gap: aggregate payment fields and payment-report endpoints now require an Owner, Manager, or Accountant membership for that garage. Unapproved members get no dashboard financial values, and direct Sale/Job Card resource reads no longer expose payment-derived fields. Explicit Platform Super Admin has its existing global read path; Guests are denied.
- **Automated tests:** Yes. Focused regression tests cover Guest, Technician, Owner, Platform Super Admin, cross-garage membership, direct resource reads, and forged garage arguments; the full Bike Garage suite and five Node regression files passed on the isolated SQLite site. No MariaDB concurrency test was run.
- **Browser/staging:** No payment-entry UI to verify. Browser, staging, and production behavior remain unverified. MariaDB locking/concurrency is unverified.
- **Evidence:** [`payments.py`](../bike_garage/payments.py), [`doctype/bg_sale_payment/bg_sale_payment.json`](../bike_garage/bike_garage/doctype/bg_sale_payment/bg_sale_payment.json), [`permissions.py`](../bike_garage/permissions.py), [`api/dashboard.py`](../bike_garage/bike_garage/api/dashboard.py), [`api/garage_job_cards.py`](../bike_garage/bike_garage/api/garage_job_cards.py), [`test_payments.py`](../bike_garage/test_payments.py), [Phase 9A audit](workflow-audit.md#phase-9a-payment-dashboard-authorization).

### 10. Expenses and reports

**Status: Partially implemented**

- **What a user can do today:** Members can create and view garage-scoped expenses. The create API validates fields, derives garage ownership, and uses a unique request key to make retries safe. Dashboard endpoints provide operational counts and expenses to garage members; payment-derived revenue, outstanding values, cash summaries, and profit figures are limited to payment-authorized memberships (and the explicit Platform Super Admin read path). Job Card part reports also require payment read access.
- **What remains:** Expense edit/delete and role-specific accounting controls are not present in the website workflow. The displayed profit figure is a simple collected-revenue-minus-recorded-expense estimate, not accounting profit: it excludes stock costs, tax liabilities, receivables rules, and formal postings. Financial report endpoints need an explicit role-access decision, including the payment aggregate issue above.
- **Automated tests:** Yes for expense validation/idempotency/scoping, dashboard scope, and Job Card part report scoping. They do not establish formal accounting correctness or browser reporting UX.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/expenses.py`](../bike_garage/bike_garage/api/expenses.py), [`api/dashboard.py`](../bike_garage/bike_garage/api/dashboard.py), [`api/reports.py`](../bike_garage/bike_garage/api/reports.py), [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py), [`test_dashboard_api.py`](../bike_garage/test_dashboard_api.py), [`test_reports_api.py`](../bike_garage/test_reports_api.py).

### 11. Staff and mechanic management

**Status: Partially implemented**

- **What a user can do today:** Platform administration APIs can add and update garage memberships with types and statuses. The code recognizes Owner, Manager, Accountant, Technician, and Inventory Manager in relevant authorization paths. Job Cards store a mechanic name as text.
- **What remains:** No complete garage-owner staff-management page or staff invitation/onboarding workflow was found. Mechanic is not a link to an authorized garage member; there is no assignment, mechanic-specific access, schedule, workload, or staff activity history. The role matrix for customer, bike, Job Card, expense, and financial data remains incomplete.
- **Automated tests:** Some tests cover platform membership changes and role checks for inventory/payment operations. No end-to-end staff assignment or mechanic workflow tests were found.
- **Browser/staging:** Not verified in a current browser or staging.
- **Evidence:** [`api/onboarding.py`](../bike_garage/bike_garage/api/onboarding.py), [`doctype/bg_garage_membership/bg_garage_membership.json`](../bike_garage/bike_garage/doctype/bg_garage_membership/bg_garage_membership.json), [`doctype/bg_job_card/bg_job_card.json`](../bike_garage/bike_garage/doctype/bg_job_card/bg_job_card.json), [`test_onboarding.py`](../bike_garage/test_onboarding.py).

### 12. Notifications, WhatsApp, and follow-ups

**Status: Partially implemented**

- **What a user can do today:** Admin approval queues a one-time registration email and records queue status. Dashboard helpers build localized English/Hindi/Marathi WhatsApp message text for invoice, payment reminder, and service messages; the UI can open WhatsApp with a prefilled message for the user to review/send.
- **What remains:** Actual email delivery and link configuration need live verification. WhatsApp is user-initiated and external; the app does not confirm delivery. No scheduled service reminders, automatic follow-ups, delivery status, retry queue, consent tracking, or notification history were found.
- **Automated tests:** Yes for message text/localization and onboarding email-queue behavior. Tests do not send a real WhatsApp message or prove email delivery.
- **Browser/staging:** No current browser or external-service verification. Earlier user requests identify WhatsApp browser checks as still outstanding.
- **Evidence:** [`api/onboarding.py`](../bike_garage/bike_garage/api/onboarding.py), [`www/garage.html`](../bike_garage/www/garage.html), [`test_garage_whatsapp.js`](../bike_garage/public/js/test_garage_whatsapp.js), [`test_onboarding.py`](../bike_garage/test_onboarding.py).

### 13. Roles, permissions, and multi-garage security

**Status: Partially implemented**

- **What a user can do today:** Tenant records carry garage ownership. Permission hooks scope list and direct document access; ownership is assigned from the authenticated user's active membership; linked customers, bikes, parts, sales, Job Cards, payment records, and child rows are checked. Payment-derived dashboard data and sensitive Sale/Job Card resource fields require Owner, Manager, or Accountant membership, with the existing Platform Super Admin global read path. Website Users do not receive Desk access from this app. BG Garage Settings source permissions grant access to System Manager rather than All, and isolated tests cover Website User denial/System Manager access. Platform-wide access uses an explicit Platform Super Admin role or Frappe Administrator.
- **What remains:** Tests cover representative endpoints, not every resource, export, attachment/File access, background job, Desk route, or integration path. Stock movement history exposes same-garage supplier/cost fields to any active garage member; its role visibility still needs policy review. Runtime staging permissions and deployed hooks are unknown.
- **Automated tests:** Broad isolated Frappe-context coverage exists for two-garage resource isolation, exact IDs, forged garage values, child rows, dashboard scope, settings permissions, and selected APIs. This is not proof of complete isolation. No MariaDB concurrency verification.
- **Browser/staging:** No current manual security/browser testing and no staging verification. Staging DB connection failure is recorded in the workflow audit.
- **Evidence:** [`tenancy.py`](../bike_garage/tenancy.py), [`permissions.py`](../bike_garage/permissions.py), [`hooks.py`](../bike_garage/hooks.py), [`doctype/bg_garage_settings/bg_garage_settings.json`](../bike_garage/bike_garage/doctype/bg_garage_settings/bg_garage_settings.json), [`test_permissions.py`](../bike_garage/test_permissions.py), [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py), [`test_tenancy.py`](../bike_garage/test_tenancy.py).

### 14. ERPNext integration and accounting

**Status: Partially implemented**

- **What a user can do today:** Source includes optional mapping fields and validation for existing ERPNext Company, Warehouse, Item, Customer, and transaction references. This checks mappings; it does not create ERPNext business transactions.
- **What remains:** No verified Sales Invoice, Purchase Receipt, Stock Entry, Payment Entry, General Ledger, tax posting, receivable, valuation, COGS, or reversal integration was found. Per-garage Company/Warehouse and accounting configuration are not established. The custom `BG Spare Part.stock_qty` is the operational quantity balance; it is not synchronized as ERPNext stock.
- **Automated tests:** Yes for mapping validation and rejection of invalid/cross-garage references. Tests explicitly avoid creating/posting ERPNext transactions; there is no posting integration test.
- **Browser/staging:** No ERPNext posting has been browser- or staging-verified.
- **Evidence:** [`erpnext_integration.py`](../bike_garage/erpnext_integration.py), [`test_erpnext_integration.py`](../bike_garage/test_erpnext_integration.py), [`BG Garage schema`](../bike_garage/bike_garage/doctype/bg_garage/bg_garage.json), [Phase 5 decisions](workflow-audit.md#phase-5-inventory-and-sales-foundation).

### 15. Mobile responsiveness and user experience

**Status: Partially implemented**

- **What a user can do today:** Landing, dashboard, registration, platform admin, and receiving pages include responsive styling. Dashboard source includes a mobile sidebar toggle, scrim, Escape handling, focus behavior, accessible labels, loading/error messages, profile keyboard controls, and reduced-motion-aware scrolling. Language controls and localized WhatsApp text are present.
- **What remains:** Test real viewport behavior, touch targets, keyboard/screen-reader behavior, overlays, form validation, loading and errors, and every dashboard action in Chrome at desktop and mobile sizes. Automated source tests cannot establish layout or interaction quality across browsers.
- **Automated tests:** Partial. UI source tests cover sidebar behavior, profile menu wiring, language catalogs, invoice navigation, login hooks, inventory UI, and WhatsApp text. They do not provide screenshot or real-browser coverage.
- **Browser/staging:** Prior user report confirms manual language/profile-menu checks only. Current responsive and broader interaction checks are outstanding; staging is unavailable.
- **Evidence:** [`www/garage.html`](../bike_garage/www/garage.html), [`public/css/landing.css`](../bike_garage/public/css/landing.css), [`public/css/garage_ui.css`](../bike_garage/public/css/garage_ui.css), [`test_garage_page.py`](../bike_garage/test_garage_page.py), JavaScript tests under [`public/js`](../bike_garage/public/js).

### 16. Installation, migration, backup, and deployment

**Status: Partially implemented; deployment state not verified**

- **What a user/operator can do today:** README documents installing the app with Bench. App install/migrate hooks create the Platform Super Admin role definition and ensure selected unique indexes. DocType source files define schema. The latest automated schema and app tests were run on the isolated SQLite site.
- **What remains:** No reviewed end-to-end deployment runbook, verified backup/restore exercise, staging revision/schema check, or production deployment evidence was found. MariaDB index and locking behavior needs isolated MariaDB validation. Pending patches and all migration effects need review before a future staging sync. Staging access must be restored first.
- **Automated tests:** App tests and schema parsing passed in the latest documented isolated run; tests do not substitute for backup restoration, migration review, or deployment validation.
- **Browser/staging:** Staging connection failed in the recorded probe; no migration was run there. Production is not verified. No claim is made about live install state.
- **Evidence:** [`README.md`](../README.md), [`hooks.py`](../bike_garage/hooks.py), [`install.py`](../bike_garage/install.py), DocType JSON under [`bike_garage/doctype`](../bike_garage/bike_garage/doctype), [workflow audit](workflow-audit.md#source-schema-and-staging-procedure).

## Overall completion summary

The codebase is a substantial but unfinished garage-management application. It contains a public application/approval flow; garage-scoped website pages and APIs for selected customer, bike, Job Card, expense, part, and inventory actions; custom stock movement records; read-only Sales/invoices; and an operational receipt ledger. Automated SQLite tests provide meaningful coverage for selected business and tenant boundaries.

It is **not verified as a deployed working product**. There is no current staging or production evidence, no real MariaDB concurrency run, and most website workflows lack current browser verification. Important workflow gaps remain in Job Card lifecycle, staff assignment, payment corrections/reconciliation, legacy stock/payment history, and ERPNext accounting. The payment dashboard aggregate authorization gap found in the prior audit is fixed in source and covered by isolated tests; deployment and browser behavior remain unverified.

## Five highest-priority remaining tasks

1. **Restore a safe staging verification path:** Confirm the intended app revision, establish database access, take and verify a recoverable backup, inspect pending patches/schema changes, then approve a targeted sync plan. Do not begin with a broad migration.
2. **Review financial and inventory access policy:** Payment aggregate and resource-field access is now restricted and covered in source tests. Separately decide which membership types may see stock supplier/cost history, then add tests before widening that access.
3. **Validate database behavior on MariaDB:** Use an isolated MariaDB test database/site to exercise unique idempotency keys and concurrent receipt/stock operations. The existing SQLite lock assertions are not concurrency evidence.
4. **Define complete operational lifecycles:** Approve Job Card state transitions, staff/mechanic assignment roles, Sale cancellation/stock reversal, payment refund/reversal, and legacy reconciliation rules before enabling missing actions.
5. **Run an end-to-end browser acceptance pass:** Test registration/login, dashboard/profile, customer/bike/Job Card/expense, stock receiving/return, invoice navigation, payment messages, Desk restrictions, mobile layout, language switching, and logout on the verified staging revision.

## Dependencies and recommended order

1. Recover staging access and establish backup/restore and revision evidence. Until then, code can only be tested in isolation.
2. Resolve the membership role matrix, especially payment-report and stock-history visibility; add authorization tests before any wider financial rollout.
3. Set up isolated MariaDB validation and prove transaction/unique-key behavior under retries and concurrent requests.
4. Agree business rules for stock valuation/opening balances, Job Card transitions/staff, Sale lifecycle, refunds, and legacy payment reconciliation. These decisions block safe Sale creation, correction, and accounting.
5. Implement only the agreed missing workflows, with focused tests and migration review.
6. Perform a browser acceptance pass against the verified staging revision; document failures and only then consider production readiness.

## Important source and test index

- Routes and landing/login/dashboard/profile: [`www/`](../bike_garage/www), [`website.py`](../bike_garage/website.py), [`garage_login.js`](../bike_garage/public/js/garage_login.js).
- Garage registration and administration: [`api/onboarding.py`](../bike_garage/bike_garage/api/onboarding.py), [`test_onboarding.py`](../bike_garage/test_onboarding.py).
- Domain records: DocType definitions and controllers under [`bike_garage/doctype`](../bike_garage/bike_garage/doctype).
- API endpoints: [`bike_garage/api`](../bike_garage/bike_garage/api).
- Tenant and role checks: [`tenancy.py`](../bike_garage/tenancy.py), [`permissions.py`](../bike_garage/permissions.py), [`hooks.py`](../bike_garage/hooks.py).
- Inventory and stock changes: [`stock.py`](../bike_garage/stock.py), [`test_inventory.py`](../bike_garage/test_inventory.py), [`test_stock_unit.py`](../bike_garage/test_stock_unit.py), [`test_garage_job_cards.py`](../bike_garage/test_garage_job_cards.py).
- Sales/payments: [`payments.py`](../bike_garage/payments.py), [`test_payments.py`](../bike_garage/test_payments.py), [`test_garage_invoice_navigation.js`](../bike_garage/public/js/test_garage_invoice_navigation.js).
- Other regression coverage: [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py), [`test_permissions.py`](../bike_garage/test_permissions.py), [`test_dashboard_api.py`](../bike_garage/test_dashboard_api.py), [`test_reports_api.py`](../bike_garage/test_reports_api.py), and JavaScript tests under [`public/js`](../bike_garage/public/js).
- Historical decisions and validation snapshots: [`docs/workflow-audit.md`](workflow-audit.md). It is chronological; earlier Phase 2–5 statements such as “payment ledger not implemented” describe older snapshots and are superseded by the later Phase 8 completion section. Read the latest phase sections for current source status.

## Platform Super Admin dashboard audit

**Audit date:** 2026-10-15
**Scope:** Read-only source and test inspection. No tests were run in this audit. No code, UI, schema, or data was changed.
**Verification boundary:** Source and automated test files were inspected; no current browser or staging session was available to verify runtime behavior.

### 1. Admin dashboard page and route

**Status: Implemented (source-level; runtime not verified)**

- Frappe's `www` convention serves [`/platform_admin`](../bike_garage/www/platform_admin.html) from `platform_admin.html`; [`platform_admin.py`](../bike_garage/www/platform_admin.py) sets `no_cache`, calls `_require_platform_super_admin()` before rendering, and adds the session user and CSRF token to context. No custom route override was found for this path.
- The template has a Garage administration page, logout link, platform counts, garage/application table, application detail dialog, membership editor, subscription-plan editor, and garage-subscription editor.
- Tests exercise authorization of `get_platform_dashboard` and onboarding APIs, but no inspected test renders this page or verifies its browser route.
- **Browser/staging:** Not verified. The workflow audit records staging access as unavailable; source route existence is not proof of a deployed route.

### 2. Dashboard statistics and summaries

**Status: Implemented (limited summary scope)**

- [`get_platform_dashboard`](../bike_garage/bike_garage/api/onboarding.py) is guarded and returns counts for total, pending, approved, active, suspended, rejected, and closed garages, plus total and pending memberships. It returns a complete garage summary list and up to 500 membership rows.
- The page renders those nine count cards and each garage's basic owner/contact, state, decision, and registration status. It does not return or calculate platform sales, payment collections, expenses, profit, or subscription revenue.
- Subscription plan amounts and per-garage agreed subscription terms are returned separately by [`get_platform_subscription_data`](../bike_garage/bike_garage/api/subscriptions.py); they are contract/plan amounts, not collected revenue.
- `test_authorized_dashboard_returns_real_counts_without_subscription_totals` checks the counts/list contract and confirms no `subscription_revenue` field.
- **Browser/staging:** Not verified.

### 3. Garage registration request list, filtering, and detail view

**Status: Partially implemented**

- The dashboard displays all garage records in one table, including requests in Pending, Approved, Rejected, and later operational states. A status selector filters the already-fetched list in the browser; the selector exposes All, Pending, Approved, and Rejected only. It does not limit the API query or provide server-side filtering.
- A View action opens an in-page dialog populated from the dashboard response with garage ID/name, owner identity, contact/address, submission time, decision fields, registration completion, and email-queue status. This is a modal detail view, not a separate detail route.
- Empty garage-filter results have a message. There is no pagination; garage rows are fetched without a limit. The membership API list is capped at 500.
- API authorization and selected dashboard data are covered by `test_onboarding.py`; the dialog, filter interaction, and layout have no inspected browser test.
- **Browser/staging:** Not verified.

### 4. Approve/reject actions and authorization

**Status: Implemented (source and API-test evidence; email/browser delivery not verified)**

- Page rendering and every onboarding admin endpoint call `_require_platform_super_admin()`, which rejects Guest and any signed-in user without the explicit `Platform Super Admin` role. The built-in Administrator is not implicitly treated as that role by `tenancy.is_platform_super_admin()`.
- Approve and reject accept only Pending applications. Approval records the decision actor/time, stores a hash of a random 48-hour registration token, and queues a registration link if outgoing email is configured. Resend is allowed only for an Approved garage whose owner has not completed registration. Reject records the decision, clears token state, and handles only pending memberships/legacy disabled owner cleanup.
- The UI displays email queue status and explains that queued email is not proof of delivery. These actions do not directly create an owner account. Owner registration occurs through the separate signed-out, expiring-token flow.
- `test_unauthorized_actions_and_platform_data_are_denied_before_queries`, approval/rejection/resend tests, and registration lifecycle tests cover API guards and state rules.
- **Browser/staging:** Not verified; SMTP delivery is also not verified.

### 5. Garage and owner account management

**Status: Partially implemented**

- Website admin actions can approve/reject applications, resend an incomplete registration link, and change an operational garage between Active and Suspended. The backend validates allowed states and records approval decisions. The registration-completion endpoint creates or completes the Website User and Owner membership after the owner submits the approved token.
- The admin page displays owner information but does not edit owner account details, reset a password, enable/disable an account, change the owner account itself, close a garage, or delete a garage. `set_garage_status` only supports Active/Suspended changes and only from those existing states.
- Tests cover application state handling, safe legacy cleanup, and registration completion; no browser interaction is verified.

### 6. User and membership management

**Status: Partially implemented**

- The page lists memberships and can add an existing enabled Frappe user to an Active garage as a Pending membership, then change membership status/type among the app-defined values. Activation requires an Active garage and the API prevents a user from having another active membership. Membership types are Owner, Manager, Service Advisor, Technician, Inventory Manager, and Accountant.
- The page explicitly says these membership labels do not assign Frappe system roles. It cannot create a Frappe User from this form, grant system roles, edit user profile/password, delete/remove a membership, or suspend a user account. A newly approved owner is created through the separate token-registration flow.
- `test_authorized_admin_adds_only_a_pending_membership`, membership allowlist/activation-conflict tests, and unauthorized-action tests cover the API behavior.
- The page renders at most 500 membership rows and has no paging/search or explicit empty-membership message.
- **Browser/staging:** Not verified.

### 7. Search, pagination, and error/empty states

**Status: Partially implemented**

- No search field, server-side query filters, or pagination controls were found. Application status filtering is client-side after fetching the complete garage list. Membership and subscription endpoints return at most 500 rows; the UI has no indication that a result may be truncated.
- Garage filter results have an explicit empty row. The main page and subscription section expose loading/error status text, and action failures display a message. There is no explicit empty-membership or empty-subscription row/message, and several errors are generic rather than actionable.
- No dedicated UI tests cover these states and no browser check was found.

### 8. Financial data visibility and role restrictions

**Status: Partially implemented (financial amounts are administrative terms, not accounting reports)**

- The platform dashboard API and subscription APIs are guarded by the explicit Platform Super Admin check. The page exposes plan prices, agreed subscription amounts, currency, subscription status, and payment references/status. Subscription validation permits only Pending or Unverified payment status; the page states that payment confirmation and confirmed platform collections are unavailable.
- No platform revenue, collected subscription payment, garage sales total, expenses, profit, or accounting balance is calculated or displayed. The UI's subscription amount fields must not be read as money received.
- Platform Super Admin `DocPerm` rows exist for BG Subscription Plan and BG Garage Subscription. The role bootstrap sets `desk_access: 0`; therefore those DocPerm rows alone do not establish that a user assigned only this role can open Desk. Effective access with other roles and the deployed role configuration were not checked.
- `test_garage_users_cannot_read_platform_subscription_data`, `test_all_subscription_mutations_require_platform_authorization`, plan/term validation tests, and dashboard authorization tests cover API-level access. Runtime role/Desk behavior is unverified.

### 9. Notifications or alerts

**Status: Partially implemented**

- Approval attempts to queue an email containing a one-time owner registration link. The page reports not-configured, queued-but-not-delivery-verified, or queue-failure states and offers a resend action for eligible applications. The workflow writes decision metadata to the garage record.
- No in-app notification center, new-request alert to an administrator, rejection email, scheduled reminders, delivery receipt, or notification history was found. Email queue status does not prove the owner received the email.
- Automated tests mock/check queue outcomes and token behavior; real mail delivery is not verified.

### 10. Responsive/mobile behavior and browser verification

**Status: Partially implemented (source only)**

- Inline CSS uses responsive flex/grid layouts and a breakpoint at 650px. Tables are wrapped in horizontally scrollable containers and retain a 700px minimum width. The dialog uses a viewport-constrained width and stacks detail fields on narrow screens.
- The source includes `role=status`/`aria-live` messages and a native dialog. That is not a substitute for keyboard, screen-reader, touch, or viewport testing.
- No browser or staging verification of the Platform Super Admin page was found. The current audit did not open it in Chrome.

### 11. Automated test coverage

**Status: Partially implemented**

- [`test_onboarding.py`](../bike_garage/test_onboarding.py) covers unauthorized calls before data queries, dashboard counts, approval/rejection/resend, membership operations, registration token lifecycle, and some atomicity/replay behavior.
- [`test_subscriptions.py`](../bike_garage/test_subscriptions.py) covers denial of garage-user access, platform authorization for mutations, plan/subscription validation, and the rule that payment references are not confirmed revenue.
- [`test_tenancy.py`](../bike_garage/test_tenancy.py) checks explicit Platform Super Admin recognition and no implicit membership bypass; [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py) covers selected cross-garage boundaries.
- The inspected tests are mainly API/controller tests. No focused test was found for serving `/platform_admin`, rendering its template, JavaScript filtering/actions, mobile layout, or browser behavior. This audit inspected tests but did not run them.

### 12. Features available only through Desk, not through this website page

**Status: Partially implemented / effective Desk availability not verified**

- The Platform Super Admin website page provides application review, selected garage status controls, membership controls, and subscription administration. It does not provide general platform CRUD screens for individual customer, bike, Job Card, stock, sale/invoice, expense, or stock-movement records, nor general user-account administration.
- Several of those DocType JSON definitions contain a `Platform Super Admin` permission row (including BG Customer, BG Bike, BG Job Card, BG Spare Part, BG Sale, BG Expense, and BG Stock Movement). This indicates intended DocType permissions for a role with Desk access; it does not establish usable Desk access for the Platform Super Admin role itself because `install.py` defines that role with `desk_access: 0`. Other assigned roles, deployed settings, and actual Desk access were not inspected in a live site.
- `BG Garage` and `BG Garage Membership` have empty DocType permission lists and are managed through guarded website APIs in this workflow; BG Garage Settings is System Manager-only in its source permissions. No browser or deployed Desk check was performed.

### Files and tests inspected for this audit

- Website route/page: [`www/platform_admin.py`](../bike_garage/www/platform_admin.py), [`www/platform_admin.html`](../bike_garage/www/platform_admin.html), [`website.py`](../bike_garage/website.py), and the website routing configuration in [`hooks.py`](../bike_garage/hooks.py).
- Authorization and workflow APIs: [`bike_garage/api/onboarding.py`](../bike_garage/bike_garage/api/onboarding.py), [`bike_garage/api/subscriptions.py`](../bike_garage/bike_garage/api/subscriptions.py), [`tenancy.py`](../bike_garage/tenancy.py), [`install.py`](../bike_garage/install.py).
- Related schema/permissions: `BG Garage`, `BG Garage Membership`, `BG Subscription Plan`, `BG Garage Subscription`, `BG Garage Settings`, `BG Customer`, `BG Bike`, `BG Job Card`, `BG Spare Part`, `BG Sale`, `BG Expense`, and `BG Stock Movement` DocType JSON files under [`bike_garage/doctype`](../bike_garage/bike_garage/doctype), plus the BG Garage and BG Garage Membership controllers.
- Tests inspected (not run during this audit): [`test_onboarding.py`](../bike_garage/test_onboarding.py), [`test_subscriptions.py`](../bike_garage/test_subscriptions.py), [`test_tenancy.py`](../bike_garage/test_tenancy.py), [`test_multi_garage_security.py`](../bike_garage/test_multi_garage_security.py), and [`test_garage_page.py`](../bike_garage/test_garage_page.py). No Platform Admin page-specific browser test was found.

## Phase 10 existing application verification record

**Audit-only result:** No application workflow was exercised in a browser during this pass. Source inspection confirmed the website routes `/platform_admin` and `/garage`; `/garage` is available to a signed-in user with exactly one active membership in an Active garage, so it is not Owner-only. The login routing source sends a Website User with such a membership to `/garage` after login; an unaffiliated/pending account is not granted that route. The Platform Admin page and its APIs require the explicit Platform Super Admin role.

**Environment:** The isolated `bike-garage-security-test.local` site configuration identifies SQLite and is present locally. No Frappe web server was listening on the usual local ports. A bundled Chromium `headless_shell` exists, but it fails to start because `libnss3.so` is unavailable; no Chrome/Firefox executable or active browser session was found. Staging is configured for MariaDB, but neither staging nor `site1-v16.local` received a database request. Their local site-config metadata was inspected only to distinguish environment types. There were no migrations, test runs, API writes, or business-record operations in Phase 10.

**Test evidence:** No tests were run in this verification pass. The latest previous result recorded above was on the isolated SQLite site: `bench --site bike-garage-security-test.local run-tests --app bike_garage` passed 48 integration tests and 147 unit tests (195 total), plus five Node regression files. This is prior automated evidence, not a Phase 10 run and not browser verification.

**Confirmed source limitations:** Platform Admin has no search or pagination; the garage list is fetched in full and membership/subscription lists are capped at 500. Website Admin does not offer general user-account editing or website CRUD for platform-wide customer, bike, Job Card, inventory, Sale/invoice, or expense records. Responsive CSS exists, but mobile interaction is unverified. These are source-confirmed limitations, not newly observed runtime failures. No runtime defect was confirmed because the browser/server could not be used.

**Manual browser verification steps once the blocker is cleared:** Use only the isolated SQLite test site and disposable test users/records. Sign in as a test Platform Super Admin and confirm `/platform_admin` loads, dashboard counts and empty/error messages render, a Pending test application can be viewed and approved/rejected, and unauthorized users are denied. Separately sign in as a test Owner and confirm `/garage`, customer/bike pages, stock receiving page, Job Card views, and Sale/invoice details load only for the assigned test garage. Check a Garage B ID while signed into Garage A, test mobile widths and keyboard operation, and confirm logout. Do not perform those state-changing approve/reject steps against staging or production.

## Phase 12 Platform Super Admin dashboard increment

**Status: Partially implemented; automated tests pass, browser behavior not verified.** `/platform_admin` now keeps its existing approval/rejection, resend, active/suspended garage, membership, plan, and subscription workflows, while the garage, membership, and subscription tables use server-side search/filter and bounded pagination. The dashboard count cards remain database counts; the response no longer loads every garage and the first 500 memberships as table payloads. The small active-garage option list remains available for the existing membership/subscription forms. Search limits are 100 characters and list pages are capped at 100 rows. List APIs and all existing privileged operations continue to require the explicit Platform Super Admin check; submitted role/status values remain allowlisted. Membership administration still edits only the app's membership label and status for an existing User; it does not assign Frappe roles or edit credentials.

Subscription list search is limited to garage or plan text, with status filtering and paging. Plan/agreed amounts remain contract terms. The page explicitly states that there is no verified payment collection or platform revenue data, and no collection totals were introduced. The subscription-plan catalogue remains capped at 500 rows. General user-account administration, notifications, and platform-wide CRUD for operational records remain absent from this website dashboard.

**Test evidence:** On isolated SQLite `bike-garage-security-test.local`, `bench --site bike-garage-security-test.local run-tests --app bike_garage` passed 48 integration tests and 151 unit tests (199 total). Focused onboarding/platform admin module passed 32 tests; focused subscription module passed 16 tests. Coverage added for authenticated list access, unauthorized denial before data queries, search/status filters, page-size caps, invalid filters/page values, and absence of fabricated revenue. Five Node regression files passed (18 tests total); Python compilation, JavaScript syntax, inline Platform Admin script syntax, and parsing of 15 app JSON files passed. `git diff --check` passed; because the Bike Garage source/docs are untracked in this worktree, an additional trailing-whitespace scan over all seven touched files passed. SQLite tests do not establish MariaDB concurrency behavior.

**Browser/deployment:** No browser test was run. The recorded local blocker is the bundled Chromium failing to start because `libnss3.so` is missing, and no active Chrome/Firefox session was available. No migrations, staging/production database access, or business-record changes occurred. Responsive layout, live filter interaction, modal details, and approval/status flows still need manual testing on the isolated site after browser dependencies are safely restored. Staging and production readiness are not established.

**Phase 12 files:** `bike_garage/bike_garage/api/onboarding.py`, `bike_garage/bike_garage/api/subscriptions.py`, `bike_garage/www/platform_admin.html`, `bike_garage/test_onboarding.py`, `bike_garage/test_subscriptions.py`, and this audit plus `workflow-audit.md`.

## Phase 13 homepage, login, and account navigation

### Verified source findings and changes

The homepage had two actual Login controls: the custom hero link and Frappe's inherited `Standard Navbar` Login item. Frappe's root resolver also checks a user's Role home page, Portal Settings, and Website Settings before calling this app's website-user hook, so the existing hook alone could not keep `/` public when one of those settings selected `/me`. The Bike Garage brand link itself already used an absolute `/` URL.

The landing template now suppresses the inherited navbar and places one responsive Login link in its custom navigation for Guests; the hero keeps a distinct **Request garage access** action targeting the existing registration section. For authenticated visitors, the header shows a dashboard link only when the server resolves one. A request-local before-request hook forces only GET/HEAD requests to `/` to resolve to `index`; it changes no site setting and does not redirect the explicit `/garage` or `/platform_admin` routes.

An authenticated destination resolver returns `/platform_admin` only for the explicit Platform Super Admin role, `/garage` only when a Website User's session resolves to one active membership in an Active garage, and no dashboard route otherwise. The login wrapper uses this resolver after a completed Frappe login, preventing stale `last_visited` or role/global home-page configuration from overriding the authorized destination. Pending, rejected, unlinked, ambiguous, and unverifiable Website User accounts return to `/`. Verification, server-directed redirects, password handling, CSRF, and all non-dashboard explicit redirects remain on Frappe's original flow. The former hardcoded demo-email redirect was removed; no demo login, seeding, record changes, or importer execution was added.

Frappe's `/me` links already use absolute Home `/` and the supported `/logout` endpoint. The account script changes its Desk link to a server-resolved Dashboard only when the current user is authorized; it removes the misleading Desk link for an ineligible Website User. The Frappe edit-profile Web Form hides its navbar and footer, so the app adds absolute Home `/`, optional authorized Dashboard, and supported Logout `/logout` controls there. The Logout destination is Frappe's existing page, which invalidates the session via `frappe.logout()` and then sends the user to `/login`; this task did not replace that behavior.

The real Frappe login template already supplies associated email/password labels, password visibility control, inline validation/error elements, and loading/error behavior. Existing `garage_ui.css` already provides the Bike Garage responsive card, focus states, error styling, and reduced-motion handling; this phase retained that implementation and only changed the login redirect/navigation wrapper. The landing preview remains static, fictional, read-only sample content. The legacy snapshot importer remains restricted to its configured staging target and was not run.

### Automated evidence and limits

On isolated SQLite `bike-garage-security-test.local`, final `bench --site bike-garage-security-test.local run-tests --app bike_garage` passed 48 integration tests and 155 unit tests (203 total). Focused onboarding tests passed 36 combined integration/unit tests; dashboard/profile source tests passed 9. All five existing Node regression files passed (20 tests total), including ten login/navigation/logout tests. Python source compilation, JavaScript syntax, app JSON parsing, and whitespace checks passed. The full Frappe suite emitted the pre-existing `limit_page_length` deprecation warning. Automated source/mock checks cover Frappe session deletion and post-logout garage denial; they do not prove live browser cookies, actual password authentication, or deployed routes.

The bundled `chromium/chrome-linux/headless_shell --version` still fails with `error while loading shared libraries: libnss3.so: cannot open shared object file`. `ldd` also reports `libnssutil3.so`, `libnspr4.so`, and `libasound.so.2` missing. The host is Ubuntu 22.04.5; no Chrome/Chromium/Firefox executable is available on PATH. No browser session/server was started and no visual or interactive test is claimed. An administrator can restore the documented Ubuntu runtime dependencies with `sudo apt-get update && sudo apt-get install libnss3 libnspr4 libasound2`, then rerun the smoke test against only the isolated SQLite site. No package installation, migration, staging/production access, business-data modification, or commit occurred in this phase.

**Phase 13 files:** `bike_garage/hooks.py`, `bike_garage/website.py`, `bike_garage/www/index.py`, `bike_garage/www/index.html`, `bike_garage/public/css/landing.css`, `bike_garage/public/css/garage_ui.css`, `bike_garage/public/js/garage_login.js`, `bike_garage/test_onboarding.py`, `bike_garage/test_garage_page.py`, `bike_garage/public/js/test_garage_login.js`, and this audit plus `workflow-audit.md`.

## Phase 14 final completion audit (2026-10-15)

**Worktree:** The existing modified `bike_garage/hooks.py`, untracked app source/tests/docs/assets, and `bike_garage/stock.py.backup` were preserved. No application code, schema, configuration, or business data was changed in this audit. The only files updated are this report and `docs/workflow-audit.md`.

**Code and automated evidence:** The installed site is `bike-garage-security-test.local`, configured for SQLite, with `frappe` and `bike_garage`; its database file is under the site's `db/` directory. `bench --site bike-garage-security-test.local run-tests --app bike_garage` passed 48 integration and 155 unit tests (203 total). All five Node regression files passed 20 tests. In-memory Python compilation passed for 88 files, JSON parsing passed for 15 files, `node --check` passed for six JavaScript files, and `git diff --check` passed. The suite emitted an existing Frappe `limit_page_length` deprecation warning. These checks exercise source and isolated SQLite fixtures; the lock assertion is not MariaDB concurrency evidence.

Coverage includes guest dashboard denial, active-membership routing, explicit Platform Super Admin authorization, application approval/registration unit and integration behavior, dashboard scoping, exact-ID and forged-garage isolation, invoice scope, payment-role filtering, stock receipt/reversal and Sale/Job Card movement auditing. The application request action is an in-page homepage section (`/#registration-title`); `/request-access` is not an implemented route. The approved-owner registration completion page is `/register` and requires a one-time approved token. The source/tests did not demonstrate a critical authorization defect in these paths during this audit.

**Browser status:** No browser smoke test was run. The bundled `chromium/chrome-linux/headless_shell --version` fails because `libnss3.so` is missing; `ldd` additionally reports missing `libnssutil3.so`, `libnspr4.so`, and `libasound.so.2`. No Chrome, Chromium, or Firefox executable is available on PATH. No server was started. Root, Request Access, login, role redirects, `/platform_admin`, `/garage`, `/register`, logout, responsive navigation, and live cross-garage behavior therefore remain unverified in a browser. Do not install system packages without administrator authorization; the documented Ubuntu packages are `libnss3`, `libnspr4`, and `libasound2`.

**Remaining readiness limits:** No MariaDB/InnoDB concurrency test, staging validation, or production validation was performed. Website Sale creation remains intentionally disabled; payment refunds/reversals and legacy payment reconciliation remain unimplemented, and operational payment entry has no website UI. ERPNext integration remains mapping/validation only, not posted accounting. These are known workflow boundaries, not defects demonstrated by this verification. Readiness: isolated SQLite automated testing only; not browser-, staging-, or production-verified.

## Phase 16 browser smoke verification (2026-10-15)

Using Playwright 1.62.1 and Chromium from `/home/rujuta/.cache/ms-playwright`, the isolated SQLite site was served only on `127.0.0.1:18080`. The test site's `site_config.json` reports `db_type: sqlite` and installed apps `frappe`, `bike_garage`. No staging or production endpoint was contacted. Existing modified/untracked files and backups were preserved; no code, records, migrations, or credentials were changed.

- `http://127.0.0.1:18080/`: HTTP 200, title “Bike Garage Management”; one visible desktop Login link and one Request garage access action. Clicking the request action navigated to `http://127.0.0.1:18080/#registration-title` and brought its section into view. The brand/Home link navigated to `/`.
- `http://127.0.0.1:18080/login`: HTTP 200, title “Login”; the Frappe login form and associated email/password labels rendered.
- Guest `http://127.0.0.1:18080/platform_admin`: HTTP 403, “Not Permitted”. Guest `http://127.0.0.1:18080/garage`: HTTP 403, “Not Permitted”.
- Mobile viewport 390×844: homepage HTTP 200, Request garage access visible, no horizontal overflow. The navigation button opened the mobile menu (`aria-expanded=true`), exposed Login, and its link navigated to `/login` (HTTP 200).
- Guest `http://127.0.0.1:18080/logout`: HTTP 200, title “Logout”. This was a Guest request and does not verify invalidation of an authenticated session.

The browser recorded no page JavaScript errors and no failed network requests. On the first run, Chromium emitted two generic failed-resource console messages corresponding to the intentional 403 responses for `/platform_admin` and `/garage`; a subsequent homepage/logout pass recorded no console errors. A homepage screenshot was produced at `/tmp/bike-garage-phase16-home.png`.

No authorized disposable login credentials were available in this task, so successful/failed authentication, login role redirects, authenticated Home/Dashboard/Logout behavior, `/me`, `/platform_admin` authorized access, and member/cross-garage browser isolation remain untested. No application defect was confirmed; no code fix was made. Browser evidence now covers only the Guest/public flows listed above. MariaDB, staging, and production remain unverified; readiness remains isolated development/testing, not production approval.

## Phase 17 authenticated browser verification (2026-10-15)

The isolated SQLite database already contains synthetic security fixtures created by `test_multi_garage_security.py`: 141 matching synthetic security users, including 47 enabled Platform Super Admin fixtures and 94 enabled Website User Owner fixtures with active garage memberships. A matching committed fixture group with two separate garages and a foreign-garage Customer record was selected read-only. Test setup commits these explicitly synthetic fixtures. The browser used only that fixture group's existing accounts; its test password was read from the test source into process memory and was never printed, stored, or changed. No demo or business account was used.

**Authenticated browser results (Playwright 1.62.1, Chromium, isolated SQLite, loopback only):** Owner login API returned 200 and redirected to `/garage`; authorized `/garage` returned 200. The Owner received 403 at `/platform_admin` and 403 when requesting a Customer resource by the exact ID belonging to the other garage. The profile page returned 200 and contained Home `/` and Dashboard `/garage`; clicking Dashboard returned 200 at `/garage`. Dashboard Sign out called `/api/method/logout` and received 200; the browser moved to `/login`, and a subsequent `/garage` request returned 403, confirming session invalidation. Platform Super Admin login API returned 200 and redirected to `/platform_admin`; authorized `/platform_admin` returned 200. That account received 403 at `/garage`. No page errors or failed requests were recorded; expected authorization denials were 403.

**Confirmed navigation defect:** For both the authenticated Owner and Platform Super Admin, requesting `http://127.0.0.1:18080/` returned HTTP 200 but rendered dashboard content instead of the public landing page. The Owner saw the garage dashboard; the Platform Super Admin saw the platform administration page. The URL remained `/`; therefore the Owner profile Home link reached the URL but not the intended public-home content. This contradicts the Phase 13 route contract and its source comment that `/` remains public for signed-in users. No application code was changed in this verification phase; root resolver correction and browser retest remain outstanding.

**Automated tests run in Phase 17:** Three selected Frappe unit tests passed: `test_dashboard_destination_requires_explicit_role_or_one_active_garage`, `test_login_home_page_routes_explicit_platform_admin_before_user_type_fallback`, and `test_frappe_logout_invalidates_session_and_guest_cannot_resolve_garage` (3/3). `node apps/bike_garage/bike_garage/public/js/test_garage_login.js` passed 10/10. The full Bike Garage suite was not rerun. A category-only test discovery produced no test summary and is not counted. The integration suite was not rerun because its multi-tenant setup creates and commits another set of synthetic security fixtures.

No new users, roles, memberships, garages, or business records were created or changed by Phase 17. The server was bound to `127.0.0.1:18080` and stopped afterward. Staging/production, MariaDB, and non-synthetic user flows remain unverified. Readiness remains isolated development/testing, with the authenticated `/` homepage behavior outstanding.

## Phase 18 authenticated homepage routing and regression (2026-10-15)

**Defect and correction:** Frappe normalizes `/` to `index`, then resolves that alias through role, portal, and global home-page selection. The earlier request-local `home_page` flag did not reliably control that resolver (Frappe explicitly ignores the flag while `frappe.in_test` is true). A website-path resolver now maps only the empty/index root path on GET/HEAD directly to the existing `index` landing page and delegates every other path to Frappe's normal resolver. `/garage` and `/platform_admin` remain explicit routes. Existing successful-login destination logic is unchanged: an eligible Owner gets `/garage`, and Platform Super Admin gets `/platform_admin`.

The browser process initially had a stale global `app_hooks` cache and did not register the new resolver. The isolated SQLite site's cache was refreshed, its `app_hooks` entry reloaded from the current app source, and the loopback server restarted before the successful browser checks. This cache-only refresh did not alter site configuration or business records.

**Automated evidence:** On `bike-garage-security-test.local` (SQLite), `bench --verbose --site bike-garage-security-test.local run-tests --app bike_garage` passed **48 integration + 155 unit tests (203 total)**. The expanded integration regression covers root GET/HEAD for Guest, Owner, and Platform Super Admin, login destinations, public Home link presence, explicit dashboard routes, and cross-role route denial. All five `apps/bike_garage/bike_garage/public/js/test_*.js` files passed **20/20 Node tests**. Python compilation passed for 88 source files, JSON parsing for 15 files, JavaScript syntax checks passed for all app JS files, and `git diff --check` plus changed-file whitespace checks passed. The existing Frappe `limit_page_length` deprecation warning appeared during the suite. Tests ran on SQLite, not MariaDB.

**Browser evidence:** Playwright 1.62.1 Chromium tested `http://127.0.0.1:18080/` on the isolated SQLite site, using existing synthetic Owner and Platform Super Admin accounts. Guest, Owner, and Platform Super Admin each received HTTP **200**, `X-Page-Name: index`, and the public landing title at root. HEAD `/` returned **200** for all three. The Owner login API returned **200** and routed to `/garage`; the Platform Super Admin login API returned **200** and routed to `/platform_admin`. From the landing page, each Dashboard link reached its matching route (HTTP **200**); the opposite role's dashboard returned **403**. Guest `/garage` and `/platform_admin` both returned **403**. The Owner's existing `/me` Home link navigated to `/` and rendered the landing page; its Dashboard link is `/garage`. Owner logout API returned **200**, after which `/garage` returned **403**. Platform Admin logout page and Frappe logout POST each returned **200**, after which `/platform_admin` returned **403**. The browser captured no JavaScript page exceptions or failed network requests; one generic console resource error was a missing `/favicon.ico` (404), unrelated to routing.

No application schema, role, permission, site configuration, staging/production, or demo/business data was changed. Full integration tests create isolated synthetic fixtures as part of their existing setup. No screenshot was produced in this phase. Exact foreign-garage document access was covered by the existing full integration suite, not repeated in this browser pass. MariaDB concurrency, staging, and production remain unverified; readiness is isolated SQLite plus the listed local browser flows only.

## Phase 19 final local handover (2026-10-15)

This dated addendum supersedes earlier statements in this document that said Phase 18 root-route browser verification was outstanding or blocked. Phase 18's exact test and browser evidence is recorded in `workflow-audit.md`; this Phase 19 pass did not change application code and did not rerun tests.

**Current evidence and security review:** The Phase 18 application/test source is unchanged since its final test run; the only Phase 18 changes after that run were audit-document updates. `logs/frappe.testing.log` records the successful isolated SQLite Bike Garage suite at 2026-10-15 16:57:46 (22.320 seconds; 48 integration + 155 unit = 203), with no failure summary; Phase 18 records five Node files, 20/20 tests, Python compilation (88 files), JSON parsing (15 files), JavaScript syntax checks, and `git diff --check` passing. This audit-only pass confirmed the log and inspected the current working tree. It did not rerun those commands.

Read-only source review found no new critical defect in the inspected paths: public onboarding creates a Pending `BG Garage` application without creating a user; approval, rejection, membership, status, and platform-dashboard APIs call the explicit Platform Super Admin guard; registration completion validates a single expiring token and creates/activates the Website User and Owner membership. Tenant document access resolves the active garage from session membership and fails closed on missing/ambiguous membership or ownership metadata; links and child rows are checked against garage ownership. Dashboard payment aggregates are included only when `can_read_payment_data` passes, while monthly and profit/loss endpoints require payment-read access. Payment receipt APIs separately enforce the Owner/Manager/Accountant policy and garage scope. The stock service writes audited source movements with balance changes and uses the same request transaction; Sale website creation remains disabled. These are code observations supported by tests, not a proof of complete security.

**Known incomplete or unverified work remains:** no Website Sale creation, payment-entry UI, refunds/reversals, legacy payment reconciliation, or ERPNext accounting postings; Job Card workflow/state and staff-assignment gaps; legacy stock movements/opening balances are incomplete; no MariaDB concurrency testing; no current staging or production verification. Supplier/cost movement history is readable by active members within their own garage, as previously documented; consider a deliberate role-policy decision before exposing it more broadly. Registration email queueing is not proof of delivery. Historical records have not been reconciled.

**Browser handover:** Phase 18 verified the public root for Guest, Owner, and Platform Super Admin, role-specific login destinations and dashboard access, cross-role/Guest dashboard denial, Owner Home navigation, and logout/session invalidation on `http://127.0.0.1:18080` using the isolated SQLite site. Exact cross-garage record denial was covered by the automated suite, not repeated in that browser pass. The one observed browser console resource error was `/favicon.ico` HTTP 404. No `.ico` or favicon asset exists in the app; the cause is a missing optional asset, but no existing favicon asset is available to serve. It was left unchanged rather than substituting an unrelated image or modifying shared Frappe assets. It is cosmetic and did not affect the tested flows.

**Readiness:** verified locally only, on the isolated SQLite site and for the enumerated browser flows. It is reasonable to plan a separately authorized staging smoke/acceptance test after confirming a deployable revision, backup/restore and recovery procedure, migration review, and safe test accounts. This is not staging approval, staging verification, or production readiness. No test-site, staging, or production records/configuration were changed in this audit.
