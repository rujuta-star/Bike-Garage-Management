from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage import tenancy
from bike_garage.www import garage


class TestGaragePageContext(unittest.TestCase):
	def test_dashboard_translation_catalogs_load_from_app_csv_files(self):
		maps = garage._get_dashboard_translation_maps()
		self.assertEqual(maps["hi"]["Dashboard"], "डैशबोर्ड")
		self.assertEqual(maps["mr"]["Dashboard"], "डॅशबोर्ड")
		self.assertIn("Recent Job Cards", maps["hi"])
		self.assertIn("Recent Job Cards", maps["mr"])
		self.assertIn("This invoice could not be found or is not available to your garage.", maps["hi"])
		self.assertIn("This invoice could not be found or is not available to your garage.", maps["mr"])
		self.assertIn("💰 Operating Summary — This Month (Estimate)", maps["hi"])
		self.assertIn("💰 Operating Summary — This Month (Estimate)", maps["mr"])
		self.assertIn("Financial details are available to the garage owner, manager, or accountant.", maps["hi"])
		self.assertIn("Financial details are available to the garage owner, manager, or accountant.", maps["mr"])

	def test_dashboard_language_and_account_controls_are_wired(self):
		template = (Path(__file__).parent / "www" / "garage.html").read_text()
		self.assertIn('onchange="changeLanguage(this.value)"', template)
		self.assertIn("api.preferences.set_dashboard_language", template)
		self.assertIn("payload.message?.language!==language", template)
		self.assertIn("location.reload()", template)
		self.assertIn('aria-expanded="false" aria-controls="profile-menu"', template)
		self.assertIn("DASHBOARD_CAN_VIEW_FINANCIALS", template)
		self.assertIn("financialPages.has(p)&&!DASHBOARD_CAN_VIEW_FINANCIALS", template)
		self.assertIn("event.key==='Escape'&&!profileMenu.hidden", template)
		self.assertIn("href=\"/me\"", template)
		self.assertIn("fetch('/api/method/logout'", template)
		self.assertIn("DASHBOARD_USER_TYPE==='Website User'", template)
		self.assertIn("data-desk-unavailable", template)
		self.assertIn("[data-no-translate]", template)

	def test_mobile_sidebar_destinations_are_keyboard_accessible_and_close_cleanly(self):
		template = (Path(__file__).parent / "www" / "garage.html").read_text()
		sidebar = template.split('<!-- ══ SIDEBAR ══ -->', 1)[1].split('<!-- ══ TOPBAR ══ -->', 1)[0]
		self.assertNotRegex(sidebar, r'<div class="menu-item[^>]*onclick=')
		self.assertIn("garageSidebar.inert=mobileSidebarQuery.matches", template)
		self.assertIn("sidebarScrim?.addEventListener('click',()=>closeGarageSidebar(true))", template)
		self.assertIn("event.key==='Escape'&&document.body.classList.contains('garage-nav-open')", template)
		self.assertIn("function showPage(p,{skipLoad=false}={}){\n  closeGarageSidebar(true);", template)

	def test_invoice_open_action_uses_the_garage_scoped_invoice_view(self):
		template = (Path(__file__).parent / "www" / "garage.html").read_text()
		self.assertIn('href="/garage?invoice=${encodeURIComponent(sale.name)}"', template)
		self.assertIn('data-open-invoice="${esc(sale.name)}"', template)
		self.assertIn("if(handleInvoiceOpenClick(event))return;", template)
		self.assertIn("history.pushState(null,'',invoiceLink.href)", template)
		self.assertIn("preferredInvoiceName(requestedInvoiceName(),allSales)", template)
		self.assertIn('get(`/api/resource/BG Sale/${encodeURIComponent(name)}`)', template)
		self.assertIn("This invoice could not be found or is not available to your garage.", template)
		self.assertNotIn('href="/app/bg-sale/${encodeURIComponent(sale.name)}"', template)

	def test_stock_page_is_linked_from_inventory_and_sale_creation_stays_disabled(self):
		template = (Path(__file__).parent / "www" / "garage.html").read_text()
		part_form = (Path(__file__).parent / "www" / "part_new.html").read_text()
		self.assertIn('href="/stock_receive"', template)
		self.assertIn('href="/stock_receive"', part_form)
		self.assertIn('data-sale-unavailable', template)
		self.assertNotIn('href="/app/bg-sale/new-bg-sale-1"', template)

	def test_profile_has_real_home_and_dashboard_navigation(self):
		web_asset = (Path(__file__).parent / "public" / "js" / "garage_login.js").read_text()
		frappe_path = Path(__file__).resolve().parents[3] / "apps" / "frappe" / "frappe"
		profile = (frappe_path / "www" / "me.html").read_text()
		edit_profile = (frappe_path / "core" / "web_form" / "edit_profile" / "edit_profile.json").read_text()
		self.assertIn('href="/"', profile)
		self.assertIn('href="/logout"', profile)
		self.assertIn('method: "bike_garage.website.get_dashboard_route"', web_asset)
		self.assertIn('window.location?.pathname', web_asset)
		self.assertIn('href="/logout">Logout', web_asset)
		self.assertIn('"route": "update-profile"', edit_profile)

	def test_financial_labels_exclude_unverified_legacy_sale_payments(self):
		template = (Path(__file__).parent / "www" / "garage.html").read_text()
		self.assertIn("Today's Sales Marked Paid", template)
		self.assertIn("Operating Summary — This Month (Estimate)", template)
		self.assertIn("Payments are not reconciled", template)
		self.assertIn("const unverifiedSales=sales.filter(s=>s.payment_ledger_status!=='Tracked')", template)
		self.assertIn("their due amounts are excluded", template)
		self.assertIn("payment_ledger_status==='Tracked'", template)
		self.assertIn("get_daily_collections", template)
		self.assertNotIn("Profit &amp; Loss — This Month", template)

	def test_guest_is_denied_before_garage_lookup(self):
		with (
			patch.object(frappe, "session", SimpleNamespace(user="Guest")),
			patch.object(frappe, "get_doc") as get_doc,
			self.assertRaises(frappe.PermissionError),
		):
			garage.get_context(SimpleNamespace())

		get_doc.assert_not_called()

	def test_embedded_garage_json_cannot_close_its_script_element(self):
		garage_doc = SimpleNamespace(
			status="Active",
			garage_name="</script><script>alert(1)</script>",
			owner_name="",
			phone="",
			address="",
			city="",
			state="",
			pin_code="",
			gstin="",
			invoice_footer_note="",
		)
		with (
			patch.object(frappe, "session", SimpleNamespace(user="garage.user@example.test")),
			patch.object(frappe, "get_doc", return_value=garage_doc),
			patch.object(frappe, "get_cached_value", return_value="Website User"),
			patch.object(tenancy, "get_current_garage", return_value="GARAGE-1"),
			patch.object(frappe.utils, "today", return_value="2026-10-13"),
			patch("bike_garage.www.garage.get_csrf_token", return_value="csrf"),
			patch.object(frappe.local, "lang", "mr", create=True),
		):
			context = SimpleNamespace()
			garage.get_context(context)

		self.assertNotIn("</script>", context.garage_json.lower())
		self.assertEqual(context.language, "mr")
		self.assertEqual(context.user_type, "Website User")
