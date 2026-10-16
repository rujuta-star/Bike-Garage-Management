// Keep Frappe's own login and password-reset implementation while routing
// optional sign-up links to the garage application workflow.
(() => {
	const dashboardRoute = async () => {
		if (typeof window.frappe?.call !== "function") return null;
		try {
			const response = await window.frappe.call({method: "bike_garage.website.get_dashboard_route"});
			const route = response?.message;
			return route === "/garage" || route === "/garage_admin" || route === "/platform_admin" ? route : null;
		} catch (_error) {
			return null;
		}
	};

	const installDashboardRedirect = () => {
		const loginHandlers = window.login?.login_handlers;
		const originalSuccessHandler = loginHandlers?.[200];

		if (typeof originalSuccessHandler !== "function") return;

		loginHandlers[200] = function (data) {
			const requestedRedirect = window.frappe?.utils?.sanitise_redirect(
				window.frappe?.utils?.get_url_arg?.("redirect-to"),
			);
			const websiteLogin = data?.message === "No App";
			const systemLogin = data?.message === "Logged In";
			const needsDashboardResolution = (websiteLogin || systemLogin)
				&& !data.verification
				&& !data.redirect_to
				&& (!requestedRedirect || requestedRedirect === "/garage" || requestedRedirect === "/garage_admin" || requestedRedirect === "/platform_admin");

			if (needsDashboardResolution) {
				// Resolve after authentication so role and active membership come from
				// the server. This also prevents a stale last_visited value from winning.
				return dashboardRoute().then((route) => {
					if (route) {
						window.location.assign(route);
						return;
					}
					if (websiteLogin) {
						window.location.assign("/");
						return;
					}
					return originalSuccessHandler.apply(this, arguments);
				});
			}

			return originalSuccessHandler.apply(this, arguments);
		};
	};

	// hooks.py loads this asset before Frappe's inline login script. Install the
	// wrapper after that script has defined login.login_handlers.
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", installDashboardRedirect, {once: true});
	} else {
		installDashboardRedirect();
	}

	const installAccountNavigation = () => {
		const profile = document.querySelector(".portal-container:has(.my-account-avatar)");
		const editProfile = /^\/update-profile\/[^/]+\/?$/.test(window.location?.pathname || "");
		if (!profile && !editProfile) return;

		const desktopLink = document.querySelector(".portal-footer a[href='/desk']");
		const user = window.frappe?.boot?.user;
		const websiteUser = user?.user_type === "Website User";
		const platformAdmin = Array.isArray(user?.roles) && user.roles.includes("Platform Super Admin");
		if (profile) {
			const homeLink = document.querySelector(".portal-footer a[href='/']");
			if (homeLink) homeLink.href = "/";
		}
		if (desktopLink && (websiteUser || platformAdmin)) {
			// Do not briefly expose the Desk URL while the server checks the
			// authenticated user's dashboard eligibility.
			desktopLink.removeAttribute("href");
			desktopLink.textContent = "Checking dashboard access…";
			desktopLink.setAttribute("aria-busy", "true");
		}

		let editNavigation;
		if (editProfile) {
			const container = document.querySelector(".web-form-container");
			if (!container || container.querySelector(".bg-edit-profile-navigation")) return;
			editNavigation = document.createElement("nav");
			editNavigation.className = "bg-edit-profile-navigation";
			editNavigation.setAttribute("aria-label", "Account navigation");
			editNavigation.innerHTML = '<a href="/">Home</a><a href="/logout">Logout</a>';
			container.prepend(editNavigation);
		}

		dashboardRoute().then((route) => {
			if (desktopLink) {
				if (route) {
					desktopLink.href = route;
					desktopLink.textContent = "Dashboard";
					desktopLink.setAttribute("aria-label", "Dashboard");
				desktopLink.removeAttribute("aria-busy");
				} else if (window.frappe?.boot?.user?.user_type === "Website User") {
					desktopLink.remove();
				}
			}
			if (editNavigation && route) {
				const dashboard = document.createElement("a");
				dashboard.href = route;
				dashboard.textContent = "Dashboard";
				editNavigation.insertBefore(dashboard, editNavigation.lastElementChild);
			}
		});
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", installAccountNavigation, {once: true});
	} else {
		installAccountNavigation();
	}

	const loginPage = document.querySelector(".for-login");
	if (!loginPage) return;
	const loginCard = loginPage.querySelector(".login-content.page-card");
	if (loginCard && !loginCard.querySelector(".bg-login-brand")) {
		const brand = document.createElement("p");
		brand.className = "bg-login-brand";
		brand.textContent = "Bike Garage · Workshop management";
		loginCard.insertBefore(brand, loginCard.firstChild);
	}
	for (const link of loginPage.querySelectorAll('a[href="#signup"]')) {
		link.href = "/#registration-title";
		link.textContent = "Request garage access";
	}
	if (!loginPage.querySelector('a[href="/#registration-title"]')) {
		const register = document.createElement("p");
		register.className = "bg-login-register-link";
		register.innerHTML = 'New to Bike Garage? <a href="/#registration-title">Request garage access</a>';
		loginCard?.append(register);
	}
})();
