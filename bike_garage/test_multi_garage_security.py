"""Real HTTP/resource API isolation tests; run only on an isolated Frappe test site."""

import json
import re
import uuid
from urllib.parse import quote
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import make_request
from frappe.utils import get_test_client
from frappe.utils.password import update_password

from bike_garage import stock, tenancy


class TestMultiGarageResourceIsolation(IntegrationTestCase):
	"""Exercise ownership through Frappe's WSGI request and permission stack."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.token = frappe.generate_hash(length=10).upper()
		cls.password = "Temporary-Test-Password-42!"
		cls.garages = {}
		cls.users = {}
		cls.records = {"customers": {}, "bikes": {}, "parts": {}, "jobs": {}, "sales": {}, "expenses": {}, "movements": {}}
		cls.created = []

		for tenant in ("A", "B"):
			garage = frappe.get_doc(
				{
					"doctype": "BG Garage",
					"garage_id": f"SEC-{cls.token}-{tenant}",
					"garage_name": f"Security Test Garage {tenant} {cls.token}",
					"status": "Active",
				}
			).insert(ignore_permissions=True)
			cls.garages[tenant] = garage.name
			cls.created.append(("BG Garage", garage.name))

			user_email = f"security-{cls.token.lower()}-{tenant.lower()}@example.test"
			# User creation queues global-search work in test mode; keep setup independent
			# from Redis while retaining real User validation and contact creation.
			with (
				patch("frappe.utils.global_search.sync_value_in_queue"),
				patch("frappe.core.doctype.user.user.throttle_user_creation"),
			):
				user = frappe.get_doc(
					{
						"doctype": "User",
						"email": user_email,
						"first_name": f"Security Owner {tenant}",
						"user_type": "Website User",
						"enabled": 1,
						"send_welcome_email": 0,
					}
				).insert(ignore_permissions=True)
			update_password(user.name, cls.password)
			cls.users[tenant] = user.name

			membership = frappe.get_doc(
				{
					"doctype": "BG Garage Membership",
					"user": user.name,
					"garage": garage.name,
					"status": "Active",
					"membership_type": "Owner",
				}
			).insert(ignore_permissions=True)
			cls.created.append(("BG Garage Membership", membership.name))

			customer = frappe.get_doc(
				{
					"doctype": "BG Customer",
					"customer_name": f"Security Customer {tenant} {cls.token}",
					"phone": f"900000{cls.token[:4]}{tenant}",
					"garage": garage.name,
				}
			).insert(ignore_permissions=True)
			cls.records["customers"][tenant] = customer.name
			cls.created.append(("BG Customer", customer.name))

			bike = frappe.get_doc(
				{
					"doctype": "BG Bike",
					"customer": customer.name,
					"registration_no": f"SEC{cls.token}{tenant}",
					"bike_model": "Test Model",
					"garage": garage.name,
				}
			).insert(ignore_permissions=True)
			cls.records["bikes"][tenant] = bike.name
			cls.created.append(("BG Bike", bike.name))

			part = frappe.get_doc(
				{
					"doctype": "BG Spare Part",
					"part_name": f"Security Part {tenant} {cls.token}",
					"selling_price": 10,
					"garage": garage.name,
				}
			).insert(ignore_permissions=True)
			stock._apply_stock_changes({part.name: 5}, garage=garage.name)
			cls.records["parts"][tenant] = part.name
			cls.created.append(("BG Spare Part", part.name))

			job = frappe.get_doc(
				{
					"doctype": "BG Job Card",
					"customer": customer.name,
					"bike": bike.name,
					"problem_description": "Isolated security test",
					"garage": garage.name,
				}
			).insert(ignore_permissions=True)
			cls.records["jobs"][tenant] = job.name
			cls.created.append(("BG Job Card", job.name))

			sale = frappe.get_doc(
				{
					"doctype": "BG Sale",
					"customer": customer.name,
					"garage": garage.name,
					"payment_status": "Paid",
					"items": [{"part": part.name, "qty": 1, "rate": 10, "gst_rate": 0}],
				}
			).insert(ignore_permissions=True)
			cls.records["sales"][tenant] = sale.name
			cls.records.setdefault("sale_items", {})[tenant] = sale.items[0].name
			cls.created.extend([("BG Sale", sale.name), ("BG Sale Item", sale.items[0].name)])

			expense = frappe.get_doc(
				{
					"doctype": "BG Expense",
					"expense_type": "Miscellaneous",
					"description": f"Security test {tenant}",
					"date": frappe.utils.today(),
					"amount": 1,
					"garage": garage.name,
				}
			).insert(ignore_permissions=True)
			cls.records["expenses"][tenant] = expense.name
			cls.created.append(("BG Expense", expense.name))

			movement = frappe.get_doc({
				"doctype": "BG Stock Movement", "movement_type": "Positive Adjustment",
				"part": part.name, "qty": 1, "reason": "Draft security fixture",
				"garage": garage.name, "submission_key": frappe.generate_hash(length=32),
			}).insert(ignore_permissions=True)
			cls.records["movements"][tenant] = movement.name
			cls.created.append(("BG Stock Movement", movement.name))

		manager_email = f"security-manager-{cls.token.lower()}@example.test"
		with (
			patch("frappe.request", None),
			patch("frappe.utils.global_search.sync_value_in_queue"),
			patch("frappe.core.doctype.user.user.throttle_user_creation"),
		):
			manager = frappe.get_doc(
				{
					"doctype": "User",
					"email": manager_email,
					"first_name": "Security Test Manager",
					"user_type": "System User",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		with (
			patch("frappe.request", None),
			patch("frappe.utils.global_search.sync_value_in_queue"),
		):
			manager.add_roles("System Manager", tenancy.PLATFORM_SUPER_ADMIN_ROLE)
		update_password(manager.name, cls.password)
		cls.users["manager"] = manager.name

		# WSGI requests use separate connections, so commit only isolated test fixtures.
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		# WSGI requests run on separate SQLite connections. Keep their committed synthetic
		# fixtures on this dedicated test site rather than risk locked partial cleanup.
		super().tearDownClass()

	def login_client(self, tenant):
		client = get_test_client()
		response = make_request(
			target=client.post,
			args=("/api/method/login",),
			kwargs={
				"json": {"usr": self.users[tenant], "pwd": self.password},
				"headers": {"Host": frappe.local.site},
			},
			site=frappe.local.site,
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		return client

	def resource(self, doctype, name=None):
		path = f"/api/resource/{quote(doctype, safe='')}"
		if name:
			path += f"/{quote(name, safe='')}"
		return path

	def request(self, client, method, path, *, json_data=None, query_string=None, headers=None):
		request_headers = {"Host": frappe.local.site, **(headers or {})}
		kwargs = {"headers": request_headers}
		if json_data is not None:
			kwargs["json"] = json_data
		if query_string is not None:
			kwargs["query_string"] = query_string
		return make_request(
			target=getattr(client, method),
			args=(path,),
			kwargs=kwargs,
			site=frappe.local.site,
		)

	def test_owner_cannot_read_other_garage_records_or_forge_list_filters(self):
		client = self.login_client("A")
		for key, doctype in (
			("customers", "BG Customer"),
			("bikes", "BG Bike"),
			("parts", "BG Spare Part"),
			("jobs", "BG Job Card"),
			("sales", "BG Sale"),
			("expenses", "BG Expense"),
			("movements", "BG Stock Movement"),
		):
			own_response = self.request(client, "get", self.resource(doctype, self.records[key]["A"]))
			self.assertEqual(own_response.status_code, 200, doctype)
			response = self.request(client, "get", self.resource(doctype, self.records[key]["B"]))
			self.assertEqual(response.status_code, 403, doctype)

		for doctype in (
			"BG Customer", "BG Bike", "BG Spare Part", "BG Job Card", "BG Sale", "BG Expense", "BG Stock Movement"
		):
			response = self.request(
				client,
				"get",
				self.resource(doctype),
				query_string={
					"fields": json.dumps(["name", "garage"]),
					"filters": json.dumps([["garage", "=", self.garages["B"]]]),
					"limit_page_length": 0,
				},
			)
			self.assertEqual(response.status_code, 200, doctype)
			self.assertEqual(response.json["data"], [], doctype)

		response = self.request(client, "get", self.resource("BG Sale", self.records["sales"]["B"]))
		self.assertEqual(response.status_code, 403, "invoice navigation's BG Sale resource must be scoped")

	def test_owner_cannot_update_delete_or_create_cross_garage_records(self):
		client = self.login_client("A")
		csrf = client.get_cookie("csrf_token")
		headers = {"X-Frappe-CSRF-Token": csrf.value} if csrf else {}
		response = self.request(
			client,
			"put",
			self.resource("BG Customer", self.records["customers"]["B"]),
			json_data={"customer_name": "forged update", "garage": self.garages["A"]},
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)

		response = self.request(
			client,
			"post",
			self.resource("BG Stock Movement"),
			json_data={
				"movement_type": "Positive Adjustment", "part": self.records["parts"]["B"],
				"qty": 999, "reason": "Forged direct stock write", "garage": self.garages["A"],
				"stock_before": 0, "stock_after": 999, "stock_delta": 999,
			},
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)

		response = self.request(client, "delete", self.resource("BG Expense", self.records["expenses"]["B"]), headers=headers)
		self.assertEqual(response.status_code, 403)

		response = self.request(
			client,
			"post",
			self.resource("BG Customer"),
			json_data={
				"customer_name": f"Forged {self.token}",
				"phone": f"800000{self.token[:4]}A",
				"garage": self.garages["B"],
			},
			headers=headers,
		)
		self.assertGreaterEqual(response.status_code, 400)

		response = self.request(
			client,
			"post",
			self.resource("BG Bike"),
			json_data={
				"customer": self.records["customers"]["B"],
				"registration_no": f"FORGED{self.token}",
				"bike_model": "Test Model",
				"garage": self.garages["A"],
			},
			headers=headers,
		)
		self.assertGreaterEqual(response.status_code, 400)

		for doctype, payload in (
			(
				"BG Job Card",
				{
					"customer": self.records["customers"]["B"],
					"bike": self.records["bikes"]["B"],
					"problem_description": "Cross-garage link attempt",
					"garage": self.garages["A"],
				},
			),
			(
				"BG Sale",
				{
					"customer": self.records["customers"]["A"],
					"job_card": self.records["jobs"]["B"],
					"garage": self.garages["A"],
				},
			),
			(
				"BG Sale",
				{
					"customer": self.records["customers"]["A"],
					"garage": self.garages["A"],
					"items": [{"part": self.records["parts"]["B"], "qty": 1, "rate": 10}],
				},
			),
			(
				"BG Job Card",
				{
					"customer": self.records["customers"]["A"],
					"bike": self.records["bikes"]["A"],
					"problem_description": "Cross-garage child part attempt",
					"garage": self.garages["A"],
					"parts": [{"part": self.records["parts"]["B"], "qty": 1, "rate": 10}],
				},
			),
		):
			response = self.request(
				client,
				"post",
				self.resource(doctype),
				json_data=payload,
				headers=headers,
			)
			self.assertIn(response.status_code, (403, 417), doctype)

		self.assertEqual(
			frappe.db.get_value("BG Customer", self.records["customers"]["B"], ["customer_name", "garage"]),
			(f"Security Customer B {self.token}", self.garages["B"]),
		)
		self.assertFalse(frappe.db.exists("BG Customer", f"Forged {self.token}"))
		self.assertFalse(frappe.db.exists("BG Bike", {"registration_no": f"FORGED{self.token}"}))
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.records["parts"]["B"], "stock_qty"), 4)

	def test_website_user_cannot_create_or_edit_sales_through_resource_api(self):
		client = self.login_client("A")
		csrf = client.get_cookie("csrf_token")
		headers = {"X-Frappe-CSRF-Token": csrf.value} if csrf else {}
		response = self.request(
			client,
			"post",
			self.resource("BG Sale"),
			json_data={
				"customer": self.records["customers"]["A"],
				"garage": self.garages["A"],
				"items": [],
			},
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)

		response = self.request(
			client,
			"put",
			self.resource("BG Sale", self.records["sales"]["A"]),
			json_data={"payment_status": "Paid", "payment_mode": "Cash"},
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)

		response = self.request(
			client,
			"delete",
			self.resource("BG Sale", self.records["sales"]["A"]),
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(
			self.request(client, "get", self.resource("BG Sale", self.records["sales"]["A"])).status_code,
			200,
			"invoice reads remain available",
		)

	def test_child_rows_require_authorized_parent_access(self):
		client = self.login_client("A")
		child_name = self.records["sale_items"]["B"]
		response = self.request(client, "get", self.resource("BG Sale Item", child_name))
		self.assertEqual(response.status_code, 403)

		csrf = client.get_cookie("csrf_token")
		headers = {"X-Frappe-CSRF-Token": csrf.value} if csrf else {}
		response = self.request(
			client,
			"put",
			self.resource("BG Sale Item", child_name),
			json_data={"qty": 100},
			headers=headers,
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(frappe.db.get_value("BG Sale Item", child_name, "qty"), 1)

	def test_dashboard_is_membership_scoped_and_private_api_denies_guest(self):
		client_a = self.login_client("A")
		client_b = self.login_client("B")
		method = "/api/method/bike_garage.bike_garage.api.dashboard.get_dashboard_stats"
		for tenant, client in (("A", client_a), ("B", client_b)):
			response = self.request(client, "get", method)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.json["message"]["total_customers"], 1)
			self.assertEqual(response.json["message"]["total_parts"], 1)
			self.assertEqual(response.json["message"]["active_jobs"], 1)
			self.assertEqual(response.json["message"]["recent_jobs"][0]["name"], self.records["jobs"][tenant])

		guest = get_test_client()
		response = self.request(guest, "get", method)
		self.assertEqual(response.status_code, 403)

		platform = self.login_client("manager")
		response = self.request(platform, "get", method)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json["message"]["total_customers"], frappe.db.count("BG Customer"))

	def test_real_memberships_resolve_each_owner_to_only_the_assigned_garage(self):
		for tenant in ("A", "B"):
			frappe.set_user(self.users[tenant])
			self.assertEqual(tenancy.get_current_garage(), self.garages[tenant])
		frappe.set_user("Administrator")

	def test_website_root_and_authorized_dashboard_routes(self):
		guest = get_test_client()
		for tenant, destination in (("A", "/garage"), ("manager", "platform_admin")):
			login = self.request(
				get_test_client(),
				"post",
				"/api/method/login",
				json_data={"usr": self.users[tenant], "pwd": self.password},
			)
			self.assertEqual(login.status_code, 200)
			self.assertEqual(login.json["home_page"], destination)

		owner = self.login_client("A")
		platform_admin = self.login_client("manager")

		for role, client, dashboard in (
			("Guest", guest, None),
			("Garage Owner", owner, "/garage"),
			("Platform Super Admin", platform_admin, "/platform_admin"),
		):
			with self.subTest(role=role):
				root = self.request(client, "get", "/")
				self.assertEqual(root.status_code, 200)
				self.assertIn(b"Built for independent workshops", root.data)
				self.assertIn(b'href="/"', root.data)
				if dashboard:
					self.assertIn(f'href="{dashboard}"'.encode(), root.data)
				head = self.request(client, "head", "/")
				self.assertEqual(head.status_code, 200)

		for client, path, expected_status in (
			(owner, "/garage", 200),
			(owner, "/platform_admin", 403),
			(platform_admin, "/platform_admin", 200),
			(platform_admin, "/garage", 403),
			(guest, "/garage", 403),
			(guest, "/platform_admin", 403),
		):
			response = self.request(client, "get", path)
			self.assertEqual(response.status_code, expected_status, path)

	def test_global_garage_settings_are_denied_to_website_users_and_available_to_system_manager(self):
		website = self.login_client("A")
		response = self.request(website, "get", self.resource("BG Garage Settings", "BG Garage Settings"))
		self.assertEqual(response.status_code, 403)

		manager = self.login_client("manager")
		response = self.request(manager, "get", self.resource("BG Garage Settings", "BG Garage Settings"))
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

	def test_website_expense_creation_is_tenant_scoped_and_idempotent(self):
		guest = get_test_client()
		self.assertEqual(self.request(guest, "get", "/expense_new").status_code, 403)
		client = self.login_client("A")
		form_page = self.request(client, "get", "/expense_new")
		self.assertEqual(form_page.status_code, 200, form_page.get_data(as_text=True))
		self.assertIn(b'name="csrf-token"', form_page.data)
		self.assertIn(b"create_expense", form_page.data)
		csrf_match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', form_page.data)
		self.assertIsNotNone(csrf_match)
		headers = {"X-Frappe-CSRF-Token": csrf_match.group(1).decode()}
		key = str(uuid.uuid4())
		method = "/api/method/bike_garage.bike_garage.api.expenses.create_expense"
		payload = {
			"expense_type": "Miscellaneous",
			"description": f"Website expense {self.token}",
			"date": frappe.utils.today(),
			"amount": 12.5,
			"payment_mode": "UPI",
			"submission_key": key,
		}
		before = frappe.db.count("BG Expense", {"garage": self.garages["A"]})
		first = self.request(client, "post", method, json_data=payload, headers=headers)
		self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
		self.assertFalse(first.json["message"]["duplicate"])
		name = first.json["message"]["name"]
		# The WSGI request commits on a separate SQLite connection; close this test
		# transaction before asserting its persisted row from the integration connection.
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("BG Expense", name, "garage"), self.garages["A"])

		retry = self.request(client, "post", method, json_data=payload, headers=headers)
		self.assertEqual(retry.status_code, 200, retry.get_data(as_text=True))
		self.assertEqual(retry.json["message"], {"name": name, "duplicate": True})
		self.assertEqual(frappe.db.count("BG Expense", {"garage": self.garages["A"]}), before + 1)

		own_detail = self.request(
			client, "get", "/api/method/bike_garage.bike_garage.api.expenses.get_expense", query_string={"name": name}
		)
		self.assertEqual(own_detail.status_code, 200)
		own_page = self.request(client, "get", f"/expense_view?name={quote(name)}")
		self.assertEqual(own_page.status_code, 200, own_page.get_data(as_text=True))
		self.assertIn(payload["description"].encode(), own_page.data)
		other_detail = self.request(
			client, "get", "/api/method/bike_garage.bike_garage.api.expenses.get_expense",
			query_string={"name": self.records["expenses"]["B"]},
		)
		self.assertGreaterEqual(other_detail.status_code, 400)
		other_page = self.request(
			client, "get", f"/expense_view?name={quote(self.records['expenses']['B'])}"
		)
		self.assertIn(other_page.status_code, (403, 404))

		forged = dict(payload, submission_key=str(uuid.uuid4()), garage=self.garages["B"])
		forged_result = self.request(client, "post", method, json_data=forged, headers=headers)
		self.assertEqual(forged_result.status_code, 200, forged_result.get_data(as_text=True))
		frappe.db.commit()
		self.assertEqual(
			frappe.db.get_value("BG Expense", forged_result.json["message"]["name"], "garage"),
			self.garages["A"],
		)
		self.assertEqual(frappe.db.count("BG Expense", {"garage": self.garages["A"]}), before + 2)

	def test_website_customer_and_bike_creation_derive_garage_and_validate_links(self):
		client = self.login_client("A")
		guest = get_test_client()
		self.assertEqual(self.request(guest, "get", "/customer_new").status_code, 403)
		self.assertEqual(self.request(guest, "get", "/bike_new").status_code, 403)

		customer_form = self.request(client, "get", "/customer_new")
		self.assertEqual(customer_form.status_code, 200, customer_form.get_data(as_text=True))
		csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', customer_form.data).group(1).decode()
		headers = {"X-Frappe-CSRF-Token": csrf}
		customer_response = self.request(
			client,
			"post",
			"/api/method/bike_garage.bike_garage.api.customers.create_customer",
			json_data={"customer_name": f"Website Customer {self.token}", "phone": "9000000000", "garage": self.garages["B"]},
			headers=headers,
		)
		self.assertEqual(customer_response.status_code, 200, customer_response.get_data(as_text=True))
		customer = customer_response.json["message"]["name"]
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("BG Customer", customer, "garage"), self.garages["A"])
		self.assertEqual(self.request(client, "get", f"/customer_view?name={quote(customer)}").status_code, 200)
		self.assertIn(
			self.request(client, "get", f"/customer_view?name={quote(self.records['customers']['B'])}").status_code,
			(403, 404),
		)

		bike_form = self.request(client, "get", "/bike_new")
		self.assertEqual(bike_form.status_code, 200, bike_form.get_data(as_text=True))
		self.assertIn(customer.encode(), bike_form.data)
		csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', bike_form.data).group(1).decode()
		headers = {"X-Frappe-CSRF-Token": csrf}
		bike_response = self.request(
			client,
			"post",
			"/api/method/bike_garage.bike_garage.api.bikes.create_bike",
			json_data={
				"customer": customer,
				"registration_no": f"WEB{self.token}",
				"bike_model": "Test Model",
				"garage": self.garages["B"],
			},
			headers=headers,
		)
		self.assertEqual(bike_response.status_code, 200, bike_response.get_data(as_text=True))
		bike = bike_response.json["message"]["name"]
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("BG Bike", bike, "garage"), self.garages["A"])
		self.assertEqual(self.request(client, "get", f"/bike_view?name={quote(bike)}").status_code, 200)
		self.assertIn(
			self.request(client, "get", f"/bike_view?name={quote(self.records['bikes']['B'])}").status_code,
			(403, 404),
		)

		foreign_link = self.request(
			client,
			"post",
			"/api/method/bike_garage.bike_garage.api.bikes.create_bike",
			json_data={
				"customer": self.records["customers"]["B"],
				"registration_no": f"FORGED{self.token}",
				"bike_model": "Test Model",
			},
			headers=headers,
		)
		self.assertGreaterEqual(foreign_link.status_code, 400)
		self.assertFalse(frappe.db.exists("BG Bike", {"registration_no": f"FORGED{self.token}"}))

	def test_website_part_catalog_creation_cannot_set_initial_stock(self):
		guest = get_test_client()
		self.assertEqual(self.request(guest, "get", "/part_new").status_code, 403)
		client = self.login_client("A")
		page = self.request(client, "get", "/part_new")
		self.assertEqual(page.status_code, 200, page.get_data(as_text=True))
		csrf = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
		response = self.request(
			client,
			"post",
			"/api/method/bike_garage.bike_garage.api.spare_parts.create_spare_part",
			json_data={
				"part_name": f"Website Part {self.token}",
				"category": "Brakes",
				"selling_price": 25,
				"garage": self.garages["B"],
				"stock_qty": 99,
			},
			headers={"X-Frappe-CSRF-Token": csrf},
		)
		self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
		name = response.json["message"]["name"]
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("BG Spare Part", name, ["garage", "stock_qty"]), (self.garages["A"], 0))
