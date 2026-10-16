from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from bike_garage import stock
from bike_garage.bike_garage.doctype.bg_spare_part.bg_spare_part import BGSparePart
from bike_garage.bike_garage.doctype.bg_stock_movement.bg_stock_movement import BGStockMovement


# This test creates its own garage, customer, and parts. The stock lifecycle
# does not need global ERPNext Company/Warehouse or Maintenance Visit fixtures.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"BG Customer",
	"BG Bike",
	"BG Garage",
	"BG Spare Part",
	"Maintenance Visit",
]


class TestBikeGarageStock(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		token = frappe.generate_hash(length=8)
		self.garage = frappe.get_doc(
			{
				"doctype": "BG Garage",
				"garage_id": f"STOCK-{token}",
				"garage_name": f"Stock Test Garage {token}",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		self.customer = frappe.get_doc(
			{
				"doctype": "BG Customer",
				"customer_name": f"Stock Test Customer {token}",
				"phone": f"{token}1234",
				"garage": self.garage.name,
			}
		).insert()

	def make_part(self, part_name, stock_qty=10):
		part = frappe.get_doc(
			{
				"doctype": "BG Spare Part",
				"part_name": f"{part_name} {frappe.generate_hash(length=8)}",
				"selling_price": 10,
				"stock_qty": 0,
				"garage": self.garage.name,
			}
		).insert()
		if stock_qty:
			stock._apply_stock_changes({part.name: stock_qty}, garage=self.garage.name)
		return part

	def make_job_card(self, parts, **values):
		job_card = frappe.new_doc("BG Job Card")
		job_card.customer = self.customer.name
		job_card.garage = self.garage.name
		job_card.problem_description = "Stock lifecycle test"
		job_card.update(values)
		for part in parts:
			job_card.append("parts", part)
		job_card.insert()
		return job_card

	def source_movements(self, doctype, name):
		return frappe.get_all(
			"BG Stock Movement",
			filters={"source_doctype": doctype, "source_document": name},
			fields=["movement_type", "part", "qty", "stock_before", "stock_after", "source_event"],
			order_by="creation asc, name asc",
		)

	def test_child_quantities_must_be_positive(self):
		for doctype in ("BG Job Card Part", "BG Sale Item"):
			for qty in (0, -1):
				row = frappe.new_doc(doctype)
				row.qty = qty
				with self.subTest(doctype=doctype, qty=qty):
					with self.assertRaises(frappe.ValidationError):
						row.validate()

	def test_job_card_stock_edits_cancellation_and_delete(self):
		part_a = self.make_part("A Stock Edit")
		part_b = self.make_part("B Stock Edit")
		job_card = self.make_job_card([{"part": part_a.name, "qty": 2, "rate": 12.5}])
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 8)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 1)
		first_movement = self.source_movements("BG Job Card", job_card.name)[0]
		self.assertEqual(first_movement.movement_type, "Job Card Consumption")
		frappe.set_user("Administrator")
		from bike_garage.bike_garage.api import inventory
		with self.assertRaises(frappe.ValidationError):
			inventory.cancel_stock_movement(first_movement.name, reason="Must follow Job Card")
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 8)

		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 8)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 1)

		job_card.parts[0].qty = 4
		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 6)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 2)

		job_card.parts[0].part = part_b.name
		job_card.parts[0].qty = 3
		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 10)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty"), 7)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 4)

		job_card.append("parts", {"part": part_a.name, "qty": 1, "rate": 5})
		job_card.save()
		job_card.parts.pop(0)
		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 9)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty"), 10)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 6)

		job_card.status = "Cancelled"
		job_card.save()
		movement_count_after_cancel = len(self.source_movements("BG Job Card", job_card.name))
		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 10)
		self.assertEqual(movement_count_after_cancel, 7)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 7)

		job_card.status = "In Progress"
		job_card.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 9)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 8)

		job_card.status = "Cancelled"
		job_card.save()
		job_card.delete()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 10)
		self.assertEqual(len(self.source_movements("BG Job Card", job_card.name)), 9)
		self.assertEqual(self.source_movements("BG Job Card", job_card.name)[-1].source_event, "Cancelled")
		movements = self.source_movements("BG Job Card", job_card.name)
		self.assertEqual(
			sum(row.stock_after - row.stock_before for row in movements if row.part == part_a.name),
			frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty") - 10,
		)
		self.assertEqual(
			sum(row.stock_after - row.stock_before for row in movements if row.part == part_b.name),
			frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty") - 10,
		)

	def test_insufficient_stock_is_validated_before_any_part_is_updated(self):
		part_a = self.make_part("A Rollback", stock_qty=5)
		part_b = self.make_part("B Rollback", stock_qty=1)
		save_point = "before_insufficient_stock_test"
		frappe.db.savepoint(save_point)

		with self.assertRaises(frappe.ValidationError):
			self.make_job_card(
				[
					{"part": part_a.name, "qty": 2, "rate": 10},
					{"part": part_b.name, "qty": 2, "rate": 10},
				]
			)

		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 5)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty"), 1)
		frappe.db.rollback(save_point=save_point)
		self.assertFalse(
			frappe.db.exists(
				"BG Job Card",
				{"customer": self.customer.name, "problem_description": "Stock lifecycle test"},
			)
		)

	def test_stock_writes_roll_back_when_a_later_write_fails(self):
		part_a = self.make_part("A Save Failure")
		part_b = self.make_part("B Save Failure")
		original_save = BGSparePart.save
		save_count = 0
		save_point = "before_stock_save_failure_test"
		frappe.db.savepoint(save_point)

		def fail_on_second_stock_save(stock_doc, *args, **kwargs):
			nonlocal save_count
			save_count += 1
			if save_count == 2:
				raise RuntimeError("Simulated stock write failure")
			return original_save(stock_doc, *args, **kwargs)

		with patch.object(BGSparePart, "save", fail_on_second_stock_save):
			with self.assertRaisesRegex(RuntimeError, "Simulated stock write failure"):
				self.make_job_card(
					[
						{"part": part_a.name, "qty": 2, "rate": 10},
						{"part": part_b.name, "qty": 2, "rate": 10},
					]
				)

		# This integration assertion checks the database state immediately after the
		# caller catches the failure; the service savepoint must already have restored A.
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 10)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty"), 10)
		frappe.db.rollback(save_point=save_point)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_a.name, "stock_qty"), 10)
		self.assertEqual(frappe.db.get_value("BG Spare Part", part_b.name, "stock_qty"), 10)
		self.assertFalse(
			frappe.db.exists(
				"BG Job Card",
				{"customer": self.customer.name, "problem_description": "Stock lifecycle test"},
			)
		)

	def test_job_card_movement_write_failure_rolls_back_as_one_request(self):
		part = self.make_part("Audit Movement Failure")
		save_point = "before_source_movement_failure_test"
		frappe.db.savepoint(save_point)
		with patch.object(BGStockMovement, "insert", side_effect=RuntimeError("movement insert failed")):
			with self.assertRaisesRegex(RuntimeError, "movement insert failed"):
				self.make_job_card([{"part": part.name, "qty": 2, "rate": 10}])
		self.assertEqual(frappe.db.get_value("BG Spare Part", part.name, "stock_qty"), 10)
		frappe.db.rollback(save_point=save_point)
		self.assertFalse(
			frappe.db.exists(
				"BG Job Card",
				{"customer": self.customer.name, "problem_description": "Stock lifecycle test"},
			)
		)
		self.assertFalse(frappe.db.exists("BG Stock Movement", {"source_doctype": "BG Job Card", "part": part.name}))

	def test_job_card_billing_calculations_remain_unchanged(self):
		part = self.make_part("Billing Job")
		job_card = self.make_job_card(
			[{"part": part.name, "qty": 2, "rate": 12.5}],
			labour_charges=7.5,
			amount_paid=10,
		)
		self.assertAlmostEqual(job_card.parts_total, 25)
		self.assertAlmostEqual(job_card.grand_total, 32.5)
		self.assertEqual(job_card.payment_status, "Partially Paid")

	def test_sale_billing_stock_repeat_save_and_delete(self):
		part = self.make_part("Billing Sale")
		second_part = self.make_part("Billing Sale Replacement")
		sale = frappe.get_doc(
			{
				"doctype": "BG Sale",
				"customer": self.customer.name,
				"garage": self.garage.name,
				"labour_charges": 10,
				"items": [{"part": part.name, "qty": 2, "rate": 100, "gst_rate": 18}],
			}
		).insert()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part.name, "stock_qty"), 8)
		self.assertEqual(sale.payment_status, "Pending")
		self.assertFalse(sale.payment_mode)
		movements = self.source_movements("BG Sale", sale.name)
		self.assertEqual(len(movements), 1)
		self.assertEqual((movements[0].movement_type, movements[0].qty, movements[0].stock_before, movements[0].stock_after), ("Sale Consumption", 2, 10, 8))
		self.assertAlmostEqual(sale.subtotal, 20)
		self.assertAlmostEqual(sale.gst_amount, 3.6)
		self.assertAlmostEqual(sale.grand_total, 33.6)

		sale.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part.name, "stock_qty"), 8)
		self.assertEqual(len(self.source_movements("BG Sale", sale.name)), 1)
		sale.items[0].qty = 3
		sale.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part.name, "stock_qty"), 7)
		self.assertEqual(len(self.source_movements("BG Sale", sale.name)), 2)
		sale.items[0].part = second_part.name
		sale.save()
		self.assertEqual(frappe.db.get_value("BG Spare Part", part.name, "stock_qty"), 10)
		self.assertEqual(frappe.db.get_value("BG Spare Part", second_part.name, "stock_qty"), 7)
		self.assertEqual(len(self.source_movements("BG Sale", sale.name)), 4)
		frappe.set_user("Administrator")
		sale.delete()
		self.assertEqual(frappe.db.get_value("BG Spare Part", second_part.name, "stock_qty"), 10)
		movements = self.source_movements("BG Sale", sale.name)
		self.assertEqual(len(movements), 5)
		self.assertEqual(movements[-1].movement_type, "Sale Restoration")
		self.assertEqual(sum(m.stock_after - m.stock_before for m in movements), 0)
		for part in (part, second_part):
			part_movements = [movement for movement in movements if movement.part == part.name]
			self.assertEqual(
				sum(movement.stock_after - movement.stock_before for movement in part_movements),
				frappe.db.get_value("BG Spare Part", part.name, "stock_qty") - 10,
			)
