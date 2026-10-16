const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "../..");
const dashboard = fs.readFileSync(path.join(root, "www/garage.html"), "utf8");
const form = fs.readFileSync(path.join(root, "www/stock_receive.html"), "utf8");
const catalog = fs.readFileSync(path.join(root, "www/part_new.html"), "utf8");

test("inventory navigation goes to the protected movement page and catalog starts at zero", () => {
	assert.match(dashboard, /href="\/stock_receive"[^>]*>Receive \/ Adjust Stock/);
	assert.match(catalog, /New catalog entries start at zero stock/);
	assert.match(catalog, /href="\/stock_receive"/);
	assert.doesNotMatch(catalog, /name="stock_qty"/);
});

test("movement form uses CSRF, a retry key, garage APIs, and explicit reversal reasons", () => {
	assert.match(form, /meta name="csrf-token"/);
	assert.match(form, /crypto\.randomUUID\(\)/);
	assert.match(form, /create_stock_movement/);
	assert.match(form, /get_stock_movement_history/);
	assert.match(form, /row\.source_document/);
	assert.match(form, /row\.docstatus===1&&!row\.source_document/);
	assert.match(form, /cancel_stock_movement/);
	assert.match(form, /Why is this stock movement being reversed\?/);
	assert.match(form, /role="status" aria-live="polite"/);
});

test("New Sale stays unavailable while new sales require a verified lifecycle", () => {
	assert.match(dashboard, /data-sale-unavailable/);
	assert.doesNotMatch(dashboard, /href="\/app\/bg-sale\/new-bg-sale-1"/);
	assert.match(dashboard, /verified stock receiving and payment recording/);
});
