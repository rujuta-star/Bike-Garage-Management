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

test("New Sale explains why Website Users cannot create stock-consuming sales", () => {
	assert.match(template, /<button type="button" class="btn" data-sale-unavailable>\+ New Sale<\/button>/);
	assert.doesNotMatch(template, /href="\/app\/bg-sale\/new-bg-sale-1"/);
	assert.match(template, /querySelector\('\[data-sale-unavailable\]'\).*showSaleCreationBlocker/);

	const message = {textContent: "", hidden: true};
	const showBlocker = vm.runInNewContext(`(${extractFunction("showSaleCreationBlocker")})`, {
		document: {getElementById: () => message},
		translateText: (text) => text,
	});
	showBlocker();
	assert.equal(message.hidden, false);
	assert.match(message.textContent, /verified stock receiving and payment recording/);
});
