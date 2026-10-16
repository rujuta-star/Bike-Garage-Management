"""Frappe-context coverage for the garage-scoped Sale receipt ledger."""

import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bike_garage import payments, permissions, tenancy
from bike_garage.bike_garage.api import dashboard, expenses, garage_job_cards, inventory
from bike_garage.bike_garage.doctype.bg_sale_payment.bg_sale_payment import BGSalePayment


class TestSalePaymentLedger(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.token = frappe.generate_hash(length=10).upper()
		cls.garages = {}
		cls.customers = {}
		cls.users = {}
		for tenant in ("A", "B"):
			garage = frappe.get_doc({
				"doctype": "BG Garage",
				"garage_id": f"PAY-{cls.token}-{tenant}",
				"garage_name": f"Payment Test Garage {tenant} {cls.token}",
				"status": "Active",
			}).insert(ignore_permissions=True)
			cls.garages[tenant] = garage.name
			customer = frappe.get_doc({
				"doctype": "BG Customer",
				"customer_name": f"Payment Customer {tenant} {cls.token}",
				"phone": f"92000{cls.token[:5]}{tenant}",
				"garage": garage.name,
			}).insert(ignore_permissions=True)
			cls.customers[tenant] = customer.name
			for membership_type in (("Owner", "Accountant", "Technician") if tenant == "A" else ("Owner",)):
				email = f"payment-{cls.token.lower()}-{tenant.lower()}-{membership_type.lower()}@example.test"
				with (
					patch("frappe.utils.global_search.sync_value_in_queue"),
					patch("frappe.core.doctype.user.user.throttle_user_creation"),
				):
					user = frappe.get_doc({
						"doctype": "User", "email": email, "first_name": f"{tenant} {membership_type}",
						"user_type": "Website User", "enabled": 1, "send_welcome_email": 0,
					}).insert(ignore_permissions=True)
				cls.users[(tenant, membership_type)] = user.name
				frappe.get_doc({
					"doctype": "BG Garage Membership", "user": user.name, "garage": garage.name,
					"status": "Active", "membership_type": membership_type,
				}).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.sale = self.make_sale("A", 100)
		self.sale_b = self.make_sale("B", 100)

	def make_sale(self, tenant, total):
		return frappe.get_doc({
			"doctype": "BG Sale",
			"customer": self.customers[tenant],
			"garage": self.garages[tenant],
			"labour_charges": total,
		}).insert(ignore_permissions=True)

	def record(self, sale=None, amount=25, key=None, user=None, **values):
		frappe.set_user(user or self.users[("A", "Owner")])
		return payments.record_sale_payment(
			sale=(sale or self.sale.name),
			amount=amount,
			payment_mode=values.pop("payment_mode", "UPI"),
			submission_key=key or str(uuid.uuid4()),
			**values,
		)

	def test_partial_full_payment_status_balance_and_idempotent_retry(self):
		key = str(uuid.uuid4())
		partial = self.record(amount="35.00", key=key, reference="UPI-1")
		self.assertEqual((partial["amount_paid"], partial["outstanding"], partial["payment_status"]), (35, 65, "Partially Paid"))
		retry = self.record(amount="35.0", key=key, reference="UPI-1")
		self.assertTrue(retry["duplicate"])
		self.assertEqual(retry["amount_paid"], 35)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 1)
		with self.assertRaises(frappe.ValidationError):
			self.record(amount=34, key=key, reference="UPI-1")
		full = self.record(amount=65, reference="CASH-2", payment_mode="Cash")
		self.assertEqual((full["amount_paid"], full["outstanding"], full["payment_status"]), (100, 0, "Paid"))
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale.name, "payment_status"), "Paid")
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale.name, "amount_paid"), 100)

	def test_amount_validation_precision_and_overpayment(self):
		for amount in (0, -1, "NaN", "Infinity", True, "not-money"):
			with self.subTest(amount=amount), self.assertRaises(frappe.ValidationError):
				self.record(amount=amount)
		with self.assertRaises(frappe.ValidationError):
			self.record(amount=101)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 0)
		precision = frappe.get_precision("BG Sale", "grand_total")
		from frappe.utils import flt
		result = self.record(amount="12.345")
		self.assertEqual(result["amount_paid"], flt("12.345", precision=precision))

	def test_unauthorized_role_invalid_method_and_direct_record_forgery_are_denied(self):
		with self.assertRaises(frappe.PermissionError):
			self.record(user=self.users[("A", "Technician")])
		frappe.set_user(self.users[("A", "Technician")])
		with self.assertRaises(frappe.PermissionError):
			payments.get_sale_payment_history(self.sale.name)
		with self.assertRaises(frappe.ValidationError):
			self.record(payment_mode="Crypto")
		frappe.set_user(self.users[("A", "Owner")])
		forged = frappe.get_doc({
			"doctype": "BG Sale Payment", "sale": self.sale.name,
			"garage": self.garages["B"], "amount": 1, "payment_mode": "Cash",
			"submission_key": str(uuid.uuid4()), "request_fingerprint": "forged",
		})
		with self.assertRaises(frappe.PermissionError):
			forged.insert(ignore_permissions=True)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 0)

	def test_expense_access_requires_financial_membership_for_api_and_documents(self):
		frappe.set_user("Administrator")
		expense = frappe.get_doc({
			"doctype": "BG Expense",
			"expense_type": "Miscellaneous",
			"description": f"Expense role test {self.token}",
			"date": frappe.utils.today(),
			"amount": 25,
			"garage": self.garages["A"],
		}).insert(ignore_permissions=True)

		technician = self.users[("A", "Technician")]
		frappe.set_user(technician)
		self.assertEqual(
			permissions.get_permission_query_conditions(user=technician, doctype="BG Expense"),
			"1=0",
		)
		self.assertFalse(permissions.has_permission(expense, ptype="read", user=technician))
		self.assertFalse(permissions.has_permission(expense, ptype="write", user=technician))
		self.assertEqual(frappe.get_list("BG Expense", filters={"name": expense.name}), [])
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("BG Expense", expense.name)
		with self.assertRaises(frappe.PermissionError):
			expenses.get_expense(expense.name)
		with self.assertRaises(frappe.PermissionError):
			expenses.create_expense(
				"Miscellaneous", "Unauthorized expense", frappe.utils.today(), 1,
				submission_key=str(uuid.uuid4()),
			)

		accountant = self.users[("A", "Accountant")]
		frappe.set_user(accountant)
		self.assertEqual(expenses.get_expense(expense.name).name, expense.name)
		created = expenses.create_expense(
			"Miscellaneous", "Accountant expense", frappe.utils.today(), 10,
			submission_key=str(uuid.uuid4()),
		)
		self.assertFalse(created["duplicate"])

	def test_payment_rows_and_sale_summaries_cannot_be_forged_or_rewritten(self):
		result = self.record(amount=10)
		frappe.set_user(self.users[("A", "Owner")])
		payment = frappe.get_doc("BG Sale Payment", result["name"])
		payment.amount = 90
		with self.assertRaises(frappe.PermissionError):
			payment.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			payment.delete(ignore_permissions=True)
		frappe.set_user("Administrator")
		sale = frappe.get_doc("BG Sale", self.sale.name)
		sale.amount_paid = 90
		with self.assertRaises(frappe.PermissionError):
			sale.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale.name, "amount_paid"), 10)
		self.assertTrue(frappe.db.exists("BG Sale Payment", result["name"]))

	def test_cross_garage_sale_payment_read_and_create_are_denied(self):
		key = str(uuid.uuid4())
		foreign = self.record(sale=self.sale_b.name, user=self.users[("B", "Owner")], key=key)
		frappe.set_user(self.users[("A", "Owner")])
		with self.assertRaises(frappe.DoesNotExistError):
			payments.get_sale_payment_history(self.sale_b.name)
		self.assertEqual(frappe.get_list("BG Sale Payment", filters={"name": foreign["name"]}), [])
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("BG Sale Payment", foreign["name"])
		with self.assertRaises(frappe.DoesNotExistError):
			payments.record_sale_payment(
				sale=self.sale_b.name, amount=1, payment_mode="Cash", submission_key=str(uuid.uuid4())
			)
		with self.assertRaises(frappe.PermissionError):
			payments.record_sale_payment(
				sale=self.sale.name, amount=25, payment_mode="UPI", submission_key=key
			)
		accountant_payment = self.record(
			amount=5, user=self.users[("A", "Accountant")], key=str(uuid.uuid4())
		)
		self.assertFalse(accountant_payment["duplicate"])

	def test_legacy_sale_is_unverified_and_rejected_without_reconciliation(self):
		frappe.db.set_value(
			"BG Sale", self.sale.name,
			{"payment_ledger_status": "Unverified", "amount_paid": None, "payment_status": "Paid"},
			update_modified=False,
		)
		frappe.set_user(self.users[("A", "Owner")])
		summary = payments.get_sale_payment_history(self.sale.name)
		self.assertEqual(summary["payment_ledger_status"], "Unverified")
		self.assertEqual(summary["payment_status"], "Paid")
		self.assertIsNone(summary["amount_paid"])
		self.assertIsNone(summary["outstanding"])
		with self.assertRaises(frappe.ValidationError):
			self.record(amount=10)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 0)

	def test_historical_sale_import_preserves_status_but_marks_payment_unverified(self):
		frappe.set_user("Administrator")
		previous_import_flag = getattr(frappe.flags, "in_import", False)
		frappe.flags.in_import = True
		try:
			sale = frappe.get_doc({
				"doctype": "BG Sale",
				"customer": self.customers["A"],
				"garage": self.garages["A"],
			"date": frappe.utils.today(),
				"payment_status": "Paid",
				"payment_mode": "Cash",
				"labour_charges": 100,
			}).insert(ignore_permissions=True)
		finally:
			frappe.flags.in_import = previous_import_flag
		self.assertEqual((sale.payment_status, sale.payment_mode), ("Paid", "Cash"))
		self.assertEqual(sale.payment_ledger_status, "Unverified")
		self.assertIsNone(sale.amount_paid)

	def test_collection_reports_use_receipts_not_legacy_paid_status(self):
		frappe.set_user(self.users[("A", "Owner")])
		daily_before = payments.get_daily_collections(frappe.utils.today())
		from bike_garage.bike_garage.api import dashboard
		monthly_before = sum(row["total"] for row in dashboard.get_monthly_revenue())
		self.record(amount=25, payment_mode="UPI")
		frappe.db.set_value(
			"BG Sale", self.sale_b.name,
			{"payment_ledger_status": "Unverified", "amount_paid": None, "payment_status": "Paid"},
			update_modified=False,
		)
		frappe.set_user(self.users[("A", "Owner")])
		report = payments.get_daily_collections(frappe.utils.today())
		self.assertEqual(report["total"], daily_before["total"] + 25)
		self.assertEqual(report["by_mode"]["UPI"], daily_before["by_mode"]["UPI"] + 25)
		month_rows = dashboard.get_monthly_revenue()
		self.assertEqual(sum(row["total"] for row in month_rows), monthly_before + 25)
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale_b.name, "payment_status"), "Paid")

	def test_sale_with_payment_cannot_be_deleted_or_reduced_below_paid_total(self):
		self.record(amount=40)
		self.sale.reload()
		self.sale.labour_charges = 30
		with self.assertRaises(frappe.ValidationError):
			self.sale.save(ignore_permissions=True)
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			self.sale.delete(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("BG Sale", self.sale.name))
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 1)

	def test_payment_persistence_failure_rolls_back_and_payment_does_not_touch_stock_or_accounting(self):
		before_movements = frappe.db.count("BG Stock Movement")
		before_invoices = frappe.db.count("Sales Invoice") if frappe.db.table_exists("Sales Invoice") else None
		with patch.object(BGSalePayment, "insert", side_effect=RuntimeError("receipt insert failed")):
			with self.assertRaisesRegex(RuntimeError, "receipt insert failed"):
				self.record(amount=20)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 0)
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale.name, "amount_paid"), 0)
		with patch.object(frappe.db, "set_value", side_effect=RuntimeError("summary update failed")):
			with self.assertRaisesRegex(RuntimeError, "summary update failed"):
				self.record(amount=20)
		self.assertEqual(frappe.db.count("BG Sale Payment", {"sale": self.sale.name}), 0)
		self.assertEqual(frappe.db.get_value("BG Sale", self.sale.name, "amount_paid"), 0)
		result = self.record(amount=20)
		self.assertFalse(result["duplicate"])
		self.assertEqual(frappe.db.count("BG Stock Movement"), before_movements)
		if before_invoices is not None:
			self.assertEqual(frappe.db.count("Sales Invoice"), before_invoices)
		self.assertFalse(frappe.db.get_value("BG Sale", self.sale.name, "erpnext_sales_invoice"))

	def test_payment_path_requests_sale_row_lock(self):
		original_get_doc = frappe.get_doc
		locked_sales = []
		def tracked_get_doc(*args, **kwargs):
			if args and args[0] == "BG Sale":
				locked_sales.append(kwargs.get("for_update"))
			return original_get_doc(*args, **kwargs)
		with patch("bike_garage.payments.frappe.get_doc", side_effect=tracked_get_doc):
			self.record(amount=10)
		self.assertIn(True, locked_sales)

	def test_dashboard_and_resource_payment_fields_follow_payment_role_policy(self):
		self.record(amount=25)
		job = frappe.get_doc({
			"doctype": "BG Job Card",
			"customer": self.customers["A"],
			"garage": self.garages["A"],
			"date": frappe.utils.today(),
			"problem_description": "Payment authorization regression fixture",
			"parts": [],
		}).insert(ignore_permissions=True)

		frappe.set_user(self.users[("A", "Technician")])
		with self.assertRaises(frappe.PermissionError):
			payments.get_daily_collections(frappe.utils.today())
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_monthly_revenue()
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_profit_loss()

		with patch.object(payments, "collection_rows") as collections:
			stats = dashboard.get_dashboard_stats()
		collections.assert_not_called()
		self.assertFalse(stats["financial_access"])
		self.assertIsNone(stats["today_revenue"])
		self.assertIsNone(stats["outstanding"])

		self.assertEqual(frappe.get_list(
			"BG Sale", filters={"name": self.sale.name}, fields=["name", "amount_paid", "payment_status"]
		), [])
		self.assertEqual(frappe.get_list(
			"BG Job Card", filters={"name": job.name}, fields=["name", "amount_paid", "payment_status"]
		), [])
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("BG Sale", self.sale.name)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("BG Job Card", job.name)

		# The staff-safe operational Job Card endpoint remains available, but omits
		# all amount and payment-status fields.
		staff_jobs = garage_job_cards.get_job_cards()
		self.assertTrue(any(row["name"] == job.name for row in staff_jobs))
		self.assertFalse({"grand_total", "amount_paid", "payment_status"} & set(staff_jobs[0]))

		# Garage IDs are never accepted as caller-selected report scope.
		for endpoint, args in (
			(dashboard.get_dashboard_stats, ()),
			(dashboard.get_monthly_revenue, ()),
			(dashboard.get_profit_loss, ()),
			(payments.get_daily_collections, (frappe.utils.today(),)),
		):
			with self.subTest(endpoint=endpoint.__name__), self.assertRaises(TypeError):
				endpoint(*args, garage=self.garages["B"])

		frappe.set_user(self.users[("A", "Owner")])
		self.assertTrue(dashboard.get_dashboard_stats()["financial_access"])
		self.assertTrue(frappe.get_list(
			"BG Sale", filters={"name": self.sale.name}, fields=["name", "amount_paid", "payment_status"]
		))
		self.assertEqual(frappe.get_list(
			"BG Sale", filters={"name": self.sale_b.name}, fields=["name", "amount_paid"]
		), [])

	def test_explicit_platform_super_admin_uses_global_read_path_without_membership(self):
		frappe.set_user(self.users[("A", "Technician")])
		self.record(amount=15)
		frappe.set_user(self.users[("A", "Technician")])
		with (
			patch.object(tenancy, "is_platform_super_admin", return_value=True),
			patch.object(tenancy, "get_current_garage", side_effect=AssertionError("platform path must not need membership")),
		):
			self.assertTrue(payments.can_read_payment_data())
			self.assertEqual(payments.get_sale_payment_history(self.sale.name)["amount_paid"], 15)
			self.assertTrue(dashboard.get_dashboard_stats()["financial_access"])
			self.assertIsInstance(dashboard.get_monthly_revenue(), list)
			self.assertIn("total", payments.get_daily_collections(frappe.utils.today()))
			with patch.object(permissions, "_has_platform_access", return_value=True):
				self.assertEqual(
					permissions.get_permission_query_conditions(
						user=self.users[("A", "Technician")], doctype="BG Expense"
					),
					"",
				)
				self.assertEqual(
					permissions.get_permission_query_conditions(
						user=self.users[("A", "Technician")], doctype="BG Stock Movement"
					),
					"",
				)
				self.assertTrue(permissions.has_permission(
					frappe._dict({"doctype": "BG Expense", "garage": "ANY"}), ptype="read"
				))
				self.assertTrue(permissions.has_permission(
					frappe._dict({"doctype": "BG Stock Movement", "garage": "ANY"}), ptype="read"
				))
				self.assertFalse(permissions.has_permission(
					frappe._dict({"doctype": "BG Sale Payment"}), ptype="write"
				))

	def test_guest_cannot_read_payment_dashboard_data(self):
		frappe.set_user("Guest")
		for method in (
			dashboard.get_dashboard_stats,
			dashboard.get_monthly_revenue,
			dashboard.get_profit_loss,
			lambda: payments.get_daily_collections(frappe.utils.today()),
		):
			with self.subTest(method=getattr(method, "__name__", "daily")), self.assertRaises(frappe.PermissionError):
				method()
