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

const filterCustomersByQuery = vm.runInNewContext(
	`(${extractFunction("filterCustomersByQuery")})`,
);
const customers = [
	{customer_name: "Asha Rao", phone: "+91 555 100", address: "Pune"},
	{customer_name: "Bike [Works]", phone: "555.200", address: "Mumbai"},
];

test("customer search matches name, phone, and address case-insensitively", () => {
	assert.deepEqual(filterCustomersByQuery(customers, "ASHA"), [customers[0]]);
	assert.deepEqual(filterCustomersByQuery(customers, "555 100"), [customers[0]]);
	assert.deepEqual(filterCustomersByQuery(customers, "mUmBaI"), [customers[1]]);
});

test("clearing or entering whitespace restores all customers", () => {
	assert.equal(filterCustomersByQuery(customers, ""), customers);
	assert.equal(filterCustomersByQuery(customers, "   \t "), customers);
});

test("special characters are treated literally and unmatched queries return no rows", () => {
	assert.deepEqual(filterCustomersByQuery(customers, "[Works]"), [customers[1]]);
	assert.deepEqual(filterCustomersByQuery(customers, "no such customer"), []);
});

test("customer data finishing its load applies the current query", () => {
	assert.match(template, /async function loadCustomers\(\)[\s\S]*?filterCustomers\(\);/);
	assert.match(template, /No customers match this search\./);
});
