const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const template = fs.readFileSync(path.join(__dirname, "../../www/garage.html"), "utf8");
const catalogStart = template.indexOf("const WHATSAPP_MESSAGES=");
const helperStart = template.indexOf("function whatsappMessage(", catalogStart);
assert.notEqual(catalogStart, -1);
assert.notEqual(helperStart, -1);
const catalogSource = template.slice(catalogStart, helperStart).trim().replace(/;\s*$/, "");
const helperStartBrace = template.indexOf("{", helperStart);
let depth = 0;
let helperEnd = -1;
for (let i = helperStartBrace; i < template.length; i++) {
	if (template[i] === "{") depth++;
	if (template[i] === "}" && --depth === 0) {
		helperEnd = i + 1;
		break;
	}
}
assert.notEqual(helperEnd, -1);

function loadMessageHelper(language) {
	return vm.runInNewContext(`(() => { ${catalogSource}; return (${template.slice(helperStart, helperEnd)}); })()`, {
		GARAGE: {name: "Garage A", addr: "Pune", owner: "+91 1234567890"},
		document: {documentElement: {lang: language}},
	});
}

test("invoice, payment, and service WhatsApp messages use all selected languages", () => {
	const samples = {
		invoice: {customer: "Asha", invoice: "INV-0042", amount: 1250},
		payment: {customer: "Asha", document: "JOB-007", amount: 250},
		service: {customer: "Asha", registration: "MH12AB1234"},
	};
	const greetings = {en: "Dear Asha", hi: "प्रिय Asha", mr: "प्रिय Asha"};
	const localizedPhrases = {
		en: {invoice: "Thank you for your visit", payment: "gentle reminder", service: "due for its periodic service"},
		hi: {invoice: "आने के लिए धन्यवाद", payment: "विनम्र याद दिलाना", service: "नियमित सर्विस का समय"},
		mr: {invoice: "भेट दिल्याबद्दल धन्यवाद", payment: "नम्र आठवण", service: "नियमित सर्व्हिस करण्याची वेळ"},
	};
	for (const language of ["en", "hi", "mr"]) {
		const message = loadMessageHelper(language);
		for (const [kind, values] of Object.entries(samples)) {
			const text = message(kind, values);
			assert.ok(text.includes(greetings[language]), `${language} ${kind} greeting`);
			assert.ok(text.includes(localizedPhrases[language][kind]), `${language} ${kind} phrase`);
			for (const value of Object.values(values)) {
				if (typeof value === "number") continue;
				assert.ok(text.includes(String(value)));
			}
			if (kind !== "service") assert.ok(text.includes("1,250") || text.includes("250"));
		}
	}
});

test("missing, unsupported, and unknown message languages safely fall back to English", () => {
	const samples = {customer: "Asha", invoice: "INV-0042", amount: 1250};
	for (const language of [undefined, "", "fr"]) {
		const message = loadMessageHelper(language);
		assert.match(message("invoice", samples), /Dear Asha/);
		assert.match(message("invoice", samples), /Thank you for your visit/);
	}
	assert.throws(() => loadMessageHelper("mr")("unknown", samples), /Unsupported WhatsApp message type/);
});

test("multiple messages consistently use the currently selected language", () => {
	const message = loadMessageHelper("hi");
	const first = message("payment", {customer: "Asha", document: "SALE-01", amount: 100});
	const second = message("service", {customer: "Ravi", registration: "MH12CD5678"});
	assert.match(first, /विनम्र याद दिलाना/);
	assert.match(second, /नियमित सर्विस/);
	assert.ok(first.includes("SALE-01"));
	assert.ok(second.includes("MH12CD5678"));
});
