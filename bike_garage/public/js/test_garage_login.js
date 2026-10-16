const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "garage_login.js"), "utf8");
const homepage = fs.readFileSync(path.join(__dirname, "../../www/index.html"), "utf8");
const landingCss = fs.readFileSync(path.join(__dirname, "../css/landing.css"), "utf8");

function setupLoginPage({redirectTo = "", dashboardRoute = null, userType = "Website User", path = "/login"} = {}) {
	const documentListeners = {};
	const redirects = [];
	const originalCalls = [];
	const emailInput = {value: ""};
	const login = {
		login_handlers: {
			200(data, xhr) { originalCalls.push({data, xhr, thisValue: this}); },
			401(xhr, data) { originalCalls.push({data, xhr, thisValue: this}); },
		},
	};
	const document = {
		readyState: "loading",
		addEventListener(type, callback, options) {
			(documentListeners[type] ||= []).push({callback, options});
		},
		querySelector(selector) { return selector === "#login_email" ? emailInput : null; },
		querySelectorAll() { return []; },
	};
	const window = {
		login,
		location: {pathname: path, assign: (url) => redirects.push(url)},
		frappe: {
			boot: {user: {user_type: userType}},
			call: async () => ({message: dashboardRoute}),
			utils: {
				sanitise_redirect: (url) => url,
				get_url_arg: (name) => name === "redirect-to" ? redirectTo : null,
			},
		},
	};
	vm.runInNewContext(source, {document, window});
	for (const listener of documentListeners.DOMContentLoaded || []) listener.callback();
	return {
		document, documentListeners, emailInput, login, originalCalls, redirects,
		async success(data, xhr = {status: 200}) { return login.login_handlers[200](data, xhr); },
		async finishPageSetup() {
			for (const listener of documentListeners.DOMContentLoaded || []) listener.callback();
			await new Promise(setImmediate);
		},
	};
}

test("the Frappe homepage keeps Lovable design assets and the existing Request Access flow", () => {
	assert.match(homepage, /\{% block navbar %\}\{% endblock %\}/);
	assert.match(homepage, /class="bg-lovable-landing no-js"/);
	assert.match(homepage, /href="\/login"/);
	assert.match(homepage, /href="\{\{ dashboard_route \}\}"/);
	assert.match(homepage, /href="\/me"/);
	assert.match(homepage, /href="#registration-title">Request Access/);
	assert.match(homepage, /lovable-v3-hero-bg\.mp4/);
	assert.match(homepage, /lovable-v3-workshop\.jpg/);
	assert.doesNotMatch(homepage, /href="\/(?:app|request-access)"/);

	const registration = homepage.match(/<form id="garage-registration"[^>]*>([\s\S]*?)<\/form>/);
	assert.ok(registration, "homepage has the existing garage registration form");
	assert.deepEqual(
		[...registration[1].matchAll(/\bname="([^"]+)"/g)].map((match) => match[1]),
		["garage_name", "owner_name", "email", "phone", "address", "city", "state", "pin_code"],
	);
	assert.match(registration[1], /required/);
	assert.match(homepage, /X-Frappe-CSRF-Token/);
	assert.match(homepage, /bike_garage\.bike_garage\.api\.onboarding\.submit_garage_registration/);
	assert.match(homepage, /heroVideo\.play\(\)/);
	assert.match(homepage, /document\.addEventListener\("visibilitychange"/);
	assert.doesNotMatch(homepage, /heroVideo\.pause\(\)|prefers-reduced-motion: reduce/);
	assert.doesNotMatch(landingCss, /\.bg-lovable-landing \*\{[^}]*animation:none!important/);
	assert.match(landingCss, /\.bg-lovable-landing\[data-theme=dark\] h1,[\s\S]*?color: var\(--text\);/);
	assert.match(landingCss, /\.bg-lovable-landing\[data-theme=dark\] \.preview \.section-head h2/);
	assert.match(landingCss, /\.bg-lovable-landing \.preview \.section-head h2,[\s\S]*?color: #fff;/);
});

test("verified garage membership overrides Frappe's stale homepage after Website User login", async () => {
	const page = setupLoginPage({dashboardRoute: "/garage"});
	await page.success({message: "No App", home_page: "/me"});
	assert.deepEqual(page.redirects, ["/garage"]);
	assert.equal(page.originalCalls.length, 0);
});

test("Garage Manager receives the main garage workspace", async () => {
	const page = setupLoginPage({dashboardRoute: "/garage"});
	await page.success({message: "No App", home_page: "/me"});
	assert.deepEqual(page.redirects, ["/garage"]);
	assert.equal(page.originalCalls.length, 0);
});

test("failed password login responses stay with Frappe", () => {
	const page = setupLoginPage();
	const response = {message: "Invalid login credentials"};
	const xhr = {status: 401};
	page.login.login_handlers[401](xhr, response);
	assert.equal(page.originalCalls.length, 1);
	assert.equal(page.originalCalls[0].data, response);
	assert.deepEqual(page.redirects, []);
});

test("Platform Super Admin receives the server-authorized platform route", async () => {
	const page = setupLoginPage({dashboardRoute: "/platform_admin", userType: "System User"});
	await page.success({message: "Logged In", home_page: "/desk"});
	assert.deepEqual(page.redirects, ["/platform_admin"]);
	assert.equal(page.originalCalls.length, 0);
});

test("Website Users without valid membership return to the public homepage", async () => {
	const page = setupLoginPage({dashboardRoute: null});
	await page.success({message: "No App", home_page: "/me"});
	assert.deepEqual(page.redirects, ["/"]);
	assert.equal(page.originalCalls.length, 0);
});

test("verification and server-directed login flows retain Frappe's original handler", async () => {
	for (const response of [
		{message: "No App", verification: {method: "Email"}},
		{message: "No App", redirect_to: "/update-password"},
	]) {
		const page = setupLoginPage({dashboardRoute: "/garage"});
		await page.success(response);
		assert.deepEqual(page.redirects, []);
		assert.equal(page.originalCalls.length, 1);
		assert.equal(page.originalCalls[0].data, response);
	}
});

test("sanitized non-dashboard redirect targets stay with Frappe", async () => {
	const page = setupLoginPage({redirectTo: "/update-profile/user@example.test", dashboardRoute: "/garage"});
	await page.success({message: "No App", home_page: "/me"});
	assert.deepEqual(page.redirects, []);
	assert.equal(page.originalCalls.length, 1);
});

test("profile Home stays public and Dashboard follows the authorized server route", async () => {
	const desktopLink = {
		href: "/desk", textContent: "Desktop", attributes: {},
		setAttribute(name, value) { this.attributes[name] = value; },
		removeAttribute(name) { delete this.attributes[name]; if (name === "href") this.href = ""; },
		remove() { this.removed = true; },
	};
	const homeLink = {href: "/", textContent: "Home"};
	const profile = {querySelector: () => null};
	const document = {
		readyState: "complete", addEventListener() {}, querySelectorAll() { return []; },
		querySelector(selector) {
			if (selector === ".portal-container:has(.my-account-avatar)") return profile;
			if (selector === ".portal-footer a[href='/desk']") return desktopLink;
			if (selector === ".portal-footer a[href='/']") return homeLink;
			return null;
		},
		createElement() { return {setAttribute() {}, innerHTML: ""}; },
	};
	vm.runInNewContext(source, {
		document,
		window: {
			location: {pathname: "/me"},
			frappe: {boot: {user: {user_type: "Website User"}}, call: async () => ({message: "/garage"})},
		},
	});
	assert.equal(desktopLink.href, "");
	assert.equal(desktopLink.textContent, "Checking dashboard access…");
	await new Promise(setImmediate);
	assert.equal(homeLink.href, "/");
	assert.equal(desktopLink.href, "/garage");
	assert.equal(desktopLink.textContent, "Dashboard");
});

test("edit-profile page provides absolute Home and supported Logout links", async () => {
	const nav = {
		className: "", children: [],
		setAttribute() {},
		set innerHTML(value) { this.markup = value; this.lastElementChild = {name: "logout"}; },
		insertBefore(element) { this.children.push(element); },
	};
	const container = {querySelector: () => null, prepend(element) { this.nav = element; }};
	const document = {
		readyState: "complete", addEventListener() {}, querySelectorAll() { return []; },
		querySelector(selector) { return selector === ".web-form-container" ? container : null; },
		createElement(tag) { return tag === "nav" ? nav : {href: "", textContent: ""}; },
	};
	vm.runInNewContext(source, {
		document,
		window: {location: {pathname: "/update-profile/user@example.test"}, frappe: {call: async () => ({message: "/garage"})}},
	});
	await new Promise(setImmediate);
	assert.equal(container.nav, nav);
	assert.match(nav.markup, /href="\/">Home/);
	assert.match(nav.markup, /href="\/logout">Logout/);
	assert.equal(nav.children[0].href, "/garage");
});

test("logout controls use Frappe's existing session-invalidating logout route", () => {
	const frappeRoot = path.resolve(__dirname, "../../../../frappe/frappe");
	const logoutPage = fs.readFileSync(path.join(frappeRoot, "www/logout.html"), "utf8");
	const logoutClient = fs.readFileSync(path.join(frappeRoot, "public/js/frappe/utils/logout.js"), "utf8");
	const logoutHandler = fs.readFileSync(path.join(frappeRoot, "handler.py"), "utf8");
	assert.match(source, /href="\/logout">Logout/);
	assert.match(logoutPage, /frappe\.logout\(\)/);
	assert.match(logoutClient, /method: "logout"/);
	assert.match(logoutHandler, /frappe\.local\.login_manager\.logout\(\)/);
});
