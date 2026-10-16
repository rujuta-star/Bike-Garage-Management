const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const appRoot = path.resolve(__dirname, "../..");
const template = fs.readFileSync(path.join(appRoot, "www/platform_admin.html"), "utf8");
const styles = fs.readFileSync(path.join(appRoot, "public/css/platform_admin.css"), "utf8");
const onboarding = fs.readFileSync(path.join(appRoot, "bike_garage/api/onboarding.py"), "utf8");

test("platform admin navigation targets implemented dashboard sections", () => {
	for (const section of ["overview", "garage-management", "garage-list", "membership-management", "platform-reports", "subscription-management", "garage-subscriptions-heading"]) {
		assert.match(template, new RegExp(`href="#${section}"`));
		assert.match(template, new RegExp(`id="${section}"`));
	}
	assert.doesNotMatch(template, /href="#settings"/i);
	assert.match(template, /href="\/logout"/);
	assert.match(template, /\{\{ user\|e \}\}/);
});

test("platform summaries and status chart use authorized server counts", () => {
	assert.match(template, /api\('get_platform_dashboard'\)/);
	assert.match(template, /renderStatusReport\(data\.counts\)/);
	for (const count of ["garages", "pending_garages", "approved_garages", "active_garages", "suspended_garages", "memberships"]) {
		assert.match(template, new RegExp(`data\.counts\.${count}`));
	}
	assert.match(styles, /\.status-report/);
	assert.match(template, /count\/total\*100/);
});

test("platform admin uses the responsive workspace shell with functional platform shortcuts", () => {
	assert.match(template, /id="garage-search"[^>]*type="search"/);
	assert.match(template, /class="platform-sidebar"/);
	assert.match(template, /class="quick-actions"[\s\S]*?href="#garage-management"[\s\S]*?href="#garage-list"[\s\S]*?href="#membership-management"/);
	assert.match(template, /quick-review'[\s\S]*?reviewPending\(\)/);
	assert.match(template, /\['Memberships',data\.counts\.memberships/);
	assert.match(template, /data\.counts\.pending_memberships/);
	assert.match(styles, /\.count-grid\s*\{[^}]*repeat\(6, minmax\(0, 1fr\)\)/);
	assert.match(styles, /@media \(max-width: 760px\)[\s\S]*?\.quick-actions/);
	assert.doesNotMatch(template, /Appointments|Revenue & Service Trend/);
});

test("state-changing platform controls require confirmation and use CSRF-protected POST requests", () => {
	for (const label of ["Approve", "Reject", "Suspend", "Reactivate", "Resend registration link"]) {
		assert.match(template, new RegExp(`action\\('${label}'`));
	}
	assert.match(template, /confirmation&&!window\.confirm\(confirmation\)/);
	assert.match(template, /X-Frappe-CSRF-Token/);
	assert.match(template, /method: data \? 'POST' : 'GET'/);
	assert.match(template, /A one-time registration link will be generated/);
	assert.match(template, /Payment is not collected or verified/);
});

test("application review is server-authorized and rejection preserves user records", () => {
	assert.match(onboarding, /def _require_platform_super_admin\(\)/);
	assert.match(onboarding, /def approve_garage_application\(garage_name\):[\s\S]*?_require_platform_super_admin\(\)/);
	assert.match(onboarding, /def reject_garage_application\(garage_name\):[\s\S]*?membership\.status = "Suspended"/);
	const rejection = onboarding.split("def reject_garage_application(garage_name):")[1].split("@frappe.whitelist(methods=[\"POST\"])")[0];
	assert.doesNotMatch(rejection, /delete_doc\(/);
});

test("dynamic garage and membership content is inserted as text", () => {
	assert.match(template, /function cell\(row, text\)[\s\S]*?td\.textContent = text/);
	assert.match(template, /description\.textContent=value\|\|/);
	assert.match(template, /document\.createElement\('tr'\)/);
});

test("public access requests prevent concurrent submission and report persistence separately from email", () => {
	const landing = fs.readFileSync(path.join(appRoot, "www/index.html"), "utf8");
	assert.match(landing, /if \(submitButton\.disabled\) return/);
	assert.match(landing, /submitButton\.disabled = true/);
	assert.match(landing, /form\.removeAttribute\('aria-busy'\)/);
	assert.match(onboarding, /saved as Pending review[\s\S]*?No email is sent at this stage/);
});
