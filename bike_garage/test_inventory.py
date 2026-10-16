"""Frappe-context tests for garage stock movements and unsafe sale writes."""

import uuid
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import update_password

from bike_garage.bike_garage.api import inventory
from bike_garage import permissions
from bike_garage.www.stock_receive import get_context as get_stock_receive_context


class TestGarageInventoryMovements(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.token = frappe.generate_hash(length=10).upper()
		cls.users = {}
		cls.garages = {}
		cls.customers = {}
		for tenant in ("A", "B"):
			garage = frappe.get_doc({
				"doctype": "BG Garage",
				"garage_id": f"INV-{cls.token}-{tenant}",
				"garage_name": f"Inventory Test Garage {tenant} {cls.token}",
				"status": "Active",
			}).insert(ignore_permissions=True)
			cls.garages[tenant] = garage.name
			email = f"inventory-{cls.token.lower()}-{tenant.lower()}@example.test"
			with (
				patch("frappe.utils.global_search.sync_value_in_queue"),
				patch("frappe.core.doctype.user.user.throttle_user_creation"),
			):
				user = frappe.get_doc({
					"doctype": "User", "email": email, "first_name": f"Inventory {tenant}",
					"user_type": "Website User", "enabled": 1, "send_welcome_email": 0,
				}).insert(ignore_permissions=True)
			update_password(user.name, "Temporary-Inventory-Test-42!")
			cls.users[tenant] = user.name
			frappe.get_doc({
				"doctype": "BG Garage Membership", "user": user.name, "garage": garage.name,
				"status": "Active", "membership_type": "Owner",
			}).insert(ignore_permissions=True)
			customer = frappe.get_doc({
				"doctype": "BG Customer", "customer_name": f"Inventory Customer {tenant} {cls.token}",
				"phone": f"91000{cls.token[:5]}{tenant}", "garage": garage.name,
			}).insert(ignore_permissions=True)
			cls.customers[tenant] = customer.name
		tech_email = f"inventory-tech-{cls.token.lower()}@example.test"
		with (
			patch("frappe.utils.global_search.sync_value_in_queue"),
			patch("frappe.core.doctype.user.user.throttle_user_creation"),
		):
			tech = frappe.get_doc({
				"doctype": "User", "email": tech_email, "first_name": "Inventory Technician",
				"user_type": "Website User", "enabled": 1, "send_welcome_email": 0,
			}).insert(ignore_permissions=True)
		cls.users["tech"] = tech.name
		frappe.get_doc({
			"doctype": "BG Garage Membership", "user": tech.name, "garage": cls.garages["A"],
			"status": "Active", "membership_type": "Technician",
		}).insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		super().tearDownClass()

	def setUp(self):
		self.key = str(uuid.uuid4())
		self.parts = {}
		frappe.set_user("Administrator")
		for tenant in ("A", "B"):
			part = frappe.get_doc({
				"doctype": "BG Spare Part",
				"part_name": f"Inventory Part {self.token} {uuid.uuid4().hex}",
				"selling_price": 10,
				"stock_qty": 0,
				"garage": self.garages[tenant],
			}).insert(ignore_permissions=True)
			self.parts[tenant] = part.name

	def receive(self, *, tenant="A", qty=5, unit_cost=12, key=None, **extra):
		return inventory.create_stock_movement(
			part=self.parts[tenant], movement_type="Purchase Receipt", qty=qty,
			reason="Test supplier delivery", unit_cost=unit_cost,
			submission_key=key or self.key, **extra,
		)

	def test_receipt_is_scoped_idempotent_and_cancelled_as_audited_reversal(self):
		frappe.set_user(self.users["A"])
		created = self.receive(supplier="Test Supplier", reference="PO-TEST-1")
		self.assertFalse(created["duplicate"])
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 5)
		movement = frappe.get_doc("BG Stock Movement", created["name"])
		self.assertEqual((movement.docstatus, movement.stock_before, movement.stock_after), (1, 0, 5))

		retry = self.receive(qty="5.0", supplier="Test Supplier", reference="PO-TEST-1")
		self.assertTrue(retry["duplicate"])
		self.assertEqual(retry["name"], created["name"])
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 5)
		with self.assertRaises(frappe.ValidationError):
			self.receive(qty=4, supplier="Test Supplier", reference="PO-TEST-1")
		with self.assertRaises(frappe.ValidationError):
			self.receive(qty=5, supplier="Changed Supplier", reference="PO-TEST-1")
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 5)

		inventory.cancel_stock_movement(created["name"], reason="Test reversal")
		movement.reload()
		self.assertEqual((movement.docstatus, movement.reversal_stock_before, movement.reversal_stock_after), (2, 5, 0))
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)
		with self.assertRaises(frappe.ValidationError):
			inventory.cancel_stock_movement(created["name"], reason="Second reversal")
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)

	def test_receipt_requires_positive_quantity_and_explicit_nonnegative_cost(self):
		frappe.set_user(self.users["A"])
		with self.assertRaises(frappe.ValidationError):
			self.receive(qty=0)
		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Purchase Receipt", qty=1,
				reason="Missing cost evidence", submission_key=str(uuid.uuid4()),
			)
		with self.assertRaises(frappe.ValidationError):
			self.receive(unit_cost=-1, key=str(uuid.uuid4()))
		for qty in (-1, "NaN", "Infinity", "not-a-number"):
			with self.assertRaises(frappe.ValidationError):
				self.receive(qty=qty, key=str(uuid.uuid4()))
		for unit_cost in ("NaN", "Infinity", "not-a-number"):
			with self.assertRaises(frappe.ValidationError):
				self.receive(unit_cost=unit_cost, key=str(uuid.uuid4()))
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)

	def test_technician_membership_cannot_read_or_change_inventory_movements(self):
		frappe.set_user(self.users["A"])
		movement = self.receive()
		frappe.set_user(self.users["tech"])
		with self.assertRaises(frappe.PermissionError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Positive Adjustment", qty=1,
				reason="Unauthorized adjustment", submission_key=self.key,
			)
		with self.assertRaises(frappe.PermissionError):
			inventory.get_stock_movement_history()
		self.assertEqual(
			permissions.get_permission_query_conditions(
				user=self.users["tech"], doctype="BG Stock Movement"
			),
			"1=0",
		)
		self.assertEqual(
			frappe.get_list("BG Stock Movement", filters={"name": movement["name"]}),
			[],
		)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.get("BG Stock Movement", movement["name"])
		with self.assertRaises(frappe.PermissionError):
			get_stock_receive_context(frappe._dict())

	def test_inventory_page_context_and_history_options_are_garage_scoped(self):
		frappe.set_user(self.users["A"])
		context = frappe._dict()
		get_stock_receive_context(context)
		self.assertEqual(context.garage, self.garages["A"])
		self.assertTrue(context.csrf_token)
		receipt = self.receive(supplier="A Supplier", reference="A-REF")
		options = inventory.get_stock_movement_options()
		part_names = {row.name for row in options["parts"]}
		self.assertIn(self.parts["A"], part_names)
		self.assertNotIn(self.parts["B"], part_names)
		self.assertIn(receipt["name"], {row.name for row in options["receipts"]})
		self.assertIn(receipt["name"], {row.name for row in inventory.get_stock_movement_history()})
		frappe.set_user(self.users["B"])
		self.assertIn(self.parts["B"], {row.name for row in inventory.get_stock_movement_options()["parts"]})
		self.assertNotIn(self.parts["A"], {row.name for row in inventory.get_stock_movement_options()["parts"]})
		self.assertNotIn(receipt["name"], {row.name for row in inventory.get_stock_movement_history()})

	def test_adjustments_cannot_create_negative_stock_and_cancellation_reverses_delta(self):
		frappe.set_user(self.users["A"])
		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Negative Adjustment", qty=1,
				reason="Counted stock", submission_key=self.key,
			)
		self.assertFalse(frappe.db.exists("BG Stock Movement", {"submission_key": self.key}))
		positive = inventory.create_stock_movement(
			part=self.parts["A"], movement_type="Positive Adjustment", qty=3,
			reason="Verified physical count", submission_key=str(uuid.uuid4()),
		)
		negative = inventory.create_stock_movement(
			part=self.parts["A"], movement_type="Negative Adjustment", qty=1,
			reason="Damaged item", submission_key=str(uuid.uuid4()),
		)
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 2)
		with self.assertRaises(frappe.ValidationError):
			inventory.cancel_stock_movement(positive["name"], reason="Test reversal")
		positive_doc = frappe.get_doc("BG Stock Movement", positive["name"])
		self.assertEqual(positive_doc.docstatus, 1)
		self.assertFalse(positive_doc.reversal_reason)
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 2)
		inventory.cancel_stock_movement(negative["name"], reason="Test reversal")
		inventory.cancel_stock_movement(positive["name"], reason="Test reversal")
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)

	def test_supplier_return_is_bounded_by_receipt_and_must_be_reversed_first(self):
		frappe.set_user(self.users["A"])
		receipt = self.receive(supplier="Supplier", reference="PURCHASE-7")
		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Supplier Return", qty=6,
				reason="Excess return", supplier="Supplier", reference="RETURN-EXCESS",
				against_receipt=receipt["name"], submission_key=str(uuid.uuid4()),
			)
		return_key = str(uuid.uuid4())
		returned = inventory.create_stock_movement(
			part=self.parts["A"], movement_type="Supplier Return", qty=5,
			reason="Return defective items", supplier="Supplier", reference="RETURN-7",
			against_receipt=receipt["name"], submission_key=return_key,
		)
		retry = inventory.create_stock_movement(
			part=self.parts["A"], movement_type="Supplier Return", qty=5,
			reason="Return defective items", supplier="Supplier", reference="RETURN-7",
			against_receipt=receipt["name"], submission_key=return_key,
		)
		self.assertTrue(retry["duplicate"])
		self.assertEqual(retry["name"], returned["name"])
		with self.assertRaises(frappe.ValidationError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Supplier Return", qty=5,
				reason="Duplicate return", supplier="Supplier", reference="RETURN-8",
				against_receipt=receipt["name"], submission_key=str(uuid.uuid4()),
			)
		with self.assertRaises(frappe.ValidationError):
			inventory.cancel_stock_movement(receipt["name"], reason="Test reversal")
		inventory.cancel_stock_movement(returned["name"], reason="Test reversal")
		inventory.cancel_stock_movement(receipt["name"], reason="Test reversal")
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)

	def test_exact_foreign_part_and_movement_ids_do_not_cross_garages(self):
		frappe.set_user(self.users["A"])
		with self.assertRaises(frappe.DoesNotExistError):
			inventory.create_stock_movement(
				part=self.parts["B"], movement_type="Positive Adjustment", qty=3,
				reason="Forged garage input", submission_key=self.key,
			)
		frappe.set_user(self.users["B"])
		foreign_movement = self.receive(tenant="B")
		frappe.set_user(self.users["A"])
		with self.assertRaises(frappe.PermissionError):
			inventory.create_stock_movement(
				part=self.parts["A"], movement_type="Supplier Return", qty=5,
				reason="Forged receipt", supplier="B Supplier", reference="B-RETURN",
				against_receipt=foreign_movement["name"], submission_key=str(uuid.uuid4()),
			)
		with self.assertRaises(frappe.DoesNotExistError):
			inventory.cancel_stock_movement(foreign_movement["name"], reason="Unauthorized reversal")
		own_history = inventory.get_stock_movement_history()
		self.assertNotIn(foreign_movement["name"], {row.name for row in own_history})
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["B"], "stock_qty"), 5)

	def test_source_movement_references_cannot_be_forged(self):
		frappe.set_user(self.users["A"])
		movement = frappe.get_doc({
			"doctype": "BG Stock Movement",
			"movement_type": "Sale Consumption",
			"part": self.parts["A"],
			"qty": 1,
			"reason": "Forged source",
			"garage": self.garages["A"],
			"source_doctype": "BG Sale",
			"source_document": "FORGED-SALE-ID",
			"source_event": "Updated",
		})
		with self.assertRaises(frappe.PermissionError):
			movement.insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)
		self.assertFalse(frappe.db.exists("BG Stock Movement", {"source_document": "FORGED-SALE-ID"}))

	def test_cross_garage_source_reference_is_rejected_even_in_source_audit_scope(self):
		frappe.set_user("Administrator")
		source = frappe.get_doc({
			"doctype": "BG Job Card",
			"customer": self.customers["B"],
			"garage": self.garages["B"],
			"problem_description": "Cross-garage audit boundary test",
		}).insert(ignore_permissions=True)
		frappe.set_user(self.users["A"])
		from bike_garage import stock
		movement = frappe.get_doc({
			"doctype": "BG Stock Movement",
			"movement_type": "Job Card Consumption",
			"part": self.parts["A"],
			"qty": 1,
			"reason": "Forged cross-garage source",
			"garage": self.garages["A"],
			"source_doctype": "BG Job Card",
			"source_document": source.name,
			"source_event": "Updated",
		})
		with stock._source_stock_audit_scope({
			"source_doctype": "BG Job Card",
			"source_document": source.name,
			"source_event": "Updated",
			"garage": self.garages["A"],
		}, self.parts["A"], 0, -1):
			with self.assertRaises(frappe.PermissionError):
				movement.insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)
		self.assertFalse(frappe.db.exists("BG Stock Movement", {"source_document": source.name}))

	def test_movement_and_balance_roll_back_if_audit_snapshot_write_fails(self):
		frappe.set_user(self.users["A"])
		key = str(uuid.uuid4())
		from bike_garage.bike_garage.doctype.bg_stock_movement.bg_stock_movement import BGStockMovement
		with patch.object(BGStockMovement, "db_set", side_effect=RuntimeError("snapshot write failed")):
			with self.assertRaisesRegex(RuntimeError, "snapshot write failed"):
				self.receive(key=key, supplier="Supplier", reference="PO-ROLLBACK")
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 0)
		self.assertFalse(frappe.db.exists("BG Stock Movement", {"submission_key": key}))

	def test_website_users_cannot_create_sales_and_new_sales_are_pending_without_a_mode(self):
		frappe.set_user(self.users["A"])
		sale = frappe.get_doc({
			"doctype": "BG Sale", "customer": self.customers["A"], "garage": frappe.db.get_value(
				"BG Garage Membership", {"user": self.users["A"], "status": "Active"}, "garage"
			), "payment_status": "Paid", "payment_mode": "Cash",
			"items": [{"part": self.parts["A"], "qty": 1, "rate": 999, "gst_rate": 0}],
		})
		self.assertFalse(permissions.has_permission(sale, "create", self.users["A"]))

		frappe.set_user("Administrator")
		from bike_garage import stock
		stock._apply_stock_changes({self.parts["A"]: 2}, garage=self.garages["A"])
		sale.insert(ignore_permissions=True)
		self.assertEqual(sale.payment_status, "Pending")
		self.assertFalse(sale.payment_mode)
		self.assertEqual((sale.items[0].rate, sale.items[0].gst_rate), (10, "18"))
		self.assertEqual(frappe.db.get_value("BG Spare Part", self.parts["A"], "stock_qty"), 1)
		sale.payment_status = "Paid"
		with self.assertRaises(frappe.PermissionError):
			sale.save(ignore_permissions=True)
