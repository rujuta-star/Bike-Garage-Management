const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const template = fs.readFileSync(path.join(__dirname, "../../www/garage.html"), "utf8");

function extractFunction(name) {
	const start = template.indexOf(`function ${name}(`);
	assert.notEqual(start, -1, `${name} function is present`);
	const open = template.indexOf("{", start);
	let depth = 0;
	for (let index = open; index < template.length; index++) {
		if (template[index] === "{") depth++;
		if (template[index] === "}" && --depth === 0) return template.slice(start, index + 1);
	}
	throw new Error(`Unclosed function ${name}`);
}

function loadHelper(name, globals = {}) {
	return vm.runInNewContext(`(${extractFunction(name)})`, {
		URLSearchParams,
		location: {search: ""},
		...globals,
	});
}

test("direct invoice query parses encoded IDs and requested ID wins selection", () => {
	const getRequested = loadHelper("requestedInvoiceName");
	const preferred = loadHelper("preferredInvoiceName");
	const invoiceName = "INV/2026/0042";

	assert.equal(getRequested(`?view=invoice&invoice=${encodeURIComponent(invoiceName)}`), invoiceName);
	assert.equal(preferred(invoiceName, [{name: "INV/2026/0001"}]), invoiceName);
	assert.equal(preferred("", [{name: "INV/2026/0001"}]), "INV/2026/0001");
	assert.equal(preferred("", []), "");
});

test("ordinary invoice link click selects the invoice without a page reload", () => {
	const pushed = [];
	const opened = [];
	const handler = loadHelper("handleInvoiceOpenClick", {
		history: {pushState: (...args) => pushed.push(args)},
		viewInvoice: (name) => opened.push(name),
	});
	const link = {
		href: "/garage?invoice=INV-0042",
		dataset: {openInvoice: "INV-0042"},
	};
	let prevented = false;
	const event = {
		button: 0,
		metaKey: false,
		ctrlKey: false,
		shiftKey: false,
		altKey: false,
		target: {closest: (selector) => selector === "[data-open-invoice]" ? link : null},
		preventDefault: () => { prevented = true; },
	};

	assert.equal(handler(event), true);
	assert.equal(prevented, true);
	assert.deepEqual(pushed, [[null, "", link.href]]);
	assert.deepEqual(opened, ["INV-0042"]);
});

test("modified click retains the direct URL fallback", () => {
	const pushed = [];
	const opened = [];
	const handler = loadHelper("handleInvoiceOpenClick", {
		history: {pushState: (...args) => pushed.push(args)},
		viewInvoice: (name) => opened.push(name),
	});
	const event = {
		button: 0, metaKey: false, ctrlKey: true, shiftKey: false, altKey: false,
		target: {closest: () => ({href: "/garage?invoice=INV-0042", dataset: {openInvoice: "INV-0042"}})},
		preventDefault() { assert.fail("modified clicks must use the link destination"); },
	};

	assert.equal(handler(event), false);
	assert.deepEqual(pushed, []);
	assert.deepEqual(opened, []);
});
