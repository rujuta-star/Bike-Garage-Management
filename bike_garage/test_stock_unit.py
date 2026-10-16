from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import frappe

from bike_garage import stock
from bike_garage.bike_garage.doctype.bg_job_card.bg_job_card import BGJobCard
from bike_garage.bike_garage.doctype.bg_job_card_part.bg_job_card_part import BGJobCardPart
from bike_garage.bike_garage.doctype.bg_sale.bg_sale import BGSale
from bike_garage.bike_garage.doctype.bg_sale_item.bg_sale_item import BGSaleItem
from bike_garage.bike_garage.doctype.bg_spare_part.bg_spare_part import BGSparePart


class FakeStockPart:
	def __init__(self, part, balances, save_counts, garage="GARAGE-A"):
		self.name = part
		self.garage = garage
		self.part_name = part
		self.stock_qty = balances[part]
		self._part = part
		self._balances = balances
		self._save_counts = save_counts
		self._before_stock_qty = balances[part]
		self.purchase_price = 0
		self.selling_price = 0
		self.min_stock_qty = 0
		self.gst_rate = "0"

	def get(self, fieldname):
		return getattr(self, fieldname, None)

	def is_new(self):
		return False

	def get_doc_before_save(self):
		return SimpleNamespace(stock_qty=self._before_stock_qty)

	def save(self, ignore_permissions=False):
		BGSparePart.validate(self)
		self._balances[self._part] = self.stock_qty
		self._save_counts[self._part] = self._save_counts.get(self._part, 0) + 1
		self._before_stock_qty = self.stock_qty


class FakeDocument:
	def __init__(
		self,
		*,
		parts=None,
		items=None,
		status="Pending",
		before=None,
		doctype="BG Job Card",
		name="TRANSACTION-1",
		garage="GARAGE-A",
	):
		self.parts = parts or []
		self.items = items or []
		self.status = status
		self.before = before
		self.doctype = doctype
		self.name = name
		self.garage = garage

	def get(self, fieldname):
		return getattr(self, fieldname)

	def get_doc_before_save(self):
		return self.before

	def snapshot(self):
		return FakeDocument(
			parts=deepcopy(self.parts),
			items=deepcopy(self.items),
			status=self.status,
			doctype=self.doctype,
			name=self.name,
			garage=self.garage,
		)


class TestStockUnit(unittest.TestCase):
	def setUp(self):
		self.balances = {"A": 10, "B": 10}
		self.save_counts = {}
		self.part_garages = {"A": "GARAGE-A", "B": "GARAGE-A"}
		self.source_audit_patch = patch.object(stock, "_record_source_stock_movements")
		self.source_audit_patch.start()
		self.addCleanup(self.source_audit_patch.stop)
		self.get_doc_patch = patch.object(frappe, "get_doc", side_effect=self.get_stock_part)
		self.get_doc_mock = self.get_doc_patch.start()
		self.addCleanup(self.get_doc_patch.stop)
		self.savepoint_patch = patch.object(frappe.db, "savepoint")
		self.savepoint = self.savepoint_patch.start()
		self.addCleanup(self.savepoint_patch.stop)
		self.release_savepoint_patch = patch.object(frappe.db, "release_savepoint")
		self.release_savepoint = self.release_savepoint_patch.start()
		self.addCleanup(self.release_savepoint_patch.stop)
		self.rollback_patch = patch.object(frappe.db, "rollback")
		self.rollback_patch.start()
		self.addCleanup(self.rollback_patch.stop)
		self.transaction_garage_patch = patch.object(
			frappe.db, "get_value", return_value="GARAGE-A"
		)
		self.transaction_garage_patch.start()
		self.addCleanup(self.transaction_garage_patch.stop)
		self.garage_exists_patch = patch.object(frappe.db, "exists", return_value=True)
		self.garage_exists_patch.start()
		self.addCleanup(self.garage_exists_patch.stop)
		self.ownership_meta_patch = patch.object(
			frappe,
			"get_meta",
			return_value=SimpleNamespace(
				get_field=lambda fieldname: SimpleNamespace(
					fieldtype="Link", options="BG Garage"
				)
				if fieldname == "garage"
				else None
			),
		)
		self.ownership_meta_patch.start()
		self.addCleanup(self.ownership_meta_patch.stop)
		self.ownership_column_patch = patch.object(frappe.db, "has_column", return_value=True)
		self.ownership_column_patch.start()
		self.addCleanup(self.ownership_column_patch.stop)

	def get_stock_part(self, doctype, part, for_update=False):
		self.assertEqual(doctype, "BG Spare Part")
		self.assertTrue(for_update)
		return FakeStockPart(part, self.balances, self.save_counts, self.part_garages[part])

	def test_direct_stock_qty_change_is_rejected_even_with_client_flag(self):
		stock_doc = FakeStockPart("A", self.balances, self.save_counts)
		stock_doc.stock_qty = 8
		stock_doc.flags = SimpleNamespace(stock_qty_update_authorized=True)

		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				BGSparePart.validate(stock_doc)

	def test_numeric_stock_strings_are_normalized(self):
		stock_doc = FakeStockPart("A", self.balances, self.save_counts)
		stock_doc.stock_qty = "10"
		BGSparePart.validate(stock_doc)

		new_part = SimpleNamespace(
			stock_qty="0", purchase_price=0, selling_price=0, min_stock_qty=0,
			gst_rate="0", is_new=lambda: True
		)
		BGSparePart.validate(new_part)

		stock_doc.stock_qty = "9"
		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				BGSparePart.validate(stock_doc)

	def test_stock_update_scope_is_bound_to_part_name(self):
		stock_doc = FakeStockPart("B", self.balances, self.save_counts)
		stock_doc.stock_qty = 9

		with stock._stock_qty_update_scope("A"):
			self.assertTrue(stock._is_stock_qty_update_authorized("A"))
			self.assertFalse(stock._is_stock_qty_update_authorized("B"))
			with patch.object(frappe, "throw", side_effect=ValueError):
				with self.assertRaises(ValueError):
					BGSparePart.validate(stock_doc)

		self.assertFalse(stock._is_stock_qty_update_authorized("A"))

	def test_unchanged_stock_qty_can_be_saved(self):
		stock_doc = FakeStockPart("A", self.balances, self.save_counts)

		BGSparePart.validate(stock_doc)

	def test_new_spare_part_must_start_with_zero_stock(self):
		new_part = SimpleNamespace(
			stock_qty=4, purchase_price=0, selling_price=0, min_stock_qty=0,
			gst_rate="0", is_new=lambda: True
		)

		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				BGSparePart.validate(new_part)

		new_part.stock_qty = 0
		BGSparePart.validate(new_part)

	def test_stock_service_can_update_balance(self):
		stock._apply_stock_changes({"A": -2}, garage="GARAGE-A")

		self.assertEqual(self.balances["A"], 8)
		self.assertEqual(self.save_counts, {"A": 1})

	def test_no_parts_job_card_does_not_touch_inventory(self):
		doc = FakeDocument(parts=[])
		stock.update_stock_from_job_card(doc)

		self.assertEqual(self.balances, {"A": 10, "B": 10})
		self.assertEqual(self.save_counts, {})
		self.savepoint.assert_not_called()

	def test_stock_service_rejects_unassigned_or_forged_transaction_garage(self):
		doc = FakeDocument(parts=[{"part": "A", "qty": 1}])
		for stored_garage, supplied_garage in ((None, "GARAGE-A"), ("GARAGE-A", "GARAGE-B")):
			with self.subTest(stored_garage=stored_garage, supplied_garage=supplied_garage):
				doc.garage = supplied_garage
				with patch.object(frappe.db, "get_value", return_value=stored_garage):
					with self.assertRaises(frappe.PermissionError):
						stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances, {"A": 10, "B": 10})
		self.assertEqual(self.save_counts, {})

	def test_stock_service_rejects_cross_garage_parts_before_any_save(self):
		self.part_garages["B"] = "GARAGE-B"
		doc = FakeDocument(parts=[{"part": "A", "qty": 1}, {"part": "B", "qty": 1}])

		with self.assertRaises(frappe.PermissionError):
			stock.update_stock_from_job_card(doc)

		self.assertEqual(self.balances, {"A": 10, "B": 10})
		self.assertEqual(self.save_counts, {})
		self.savepoint.assert_not_called()

	def test_job_card_repeat_edit_part_change_and_delete(self):
		doc = FakeDocument(parts=[{"part": "A", "qty": 2}])
		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 8)

		doc = FakeDocument(parts=[{"part": "A", "qty": 2}], before=doc.snapshot())
		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 8)

		doc = FakeDocument(parts=[{"part": "A", "qty": 4}], before=doc.snapshot())
		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 6)

		doc = FakeDocument(parts=[{"part": "B", "qty": 3}], before=doc.snapshot())
		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances, {"A": 10, "B": 7})
		stock.restore_stock_from_job_card(doc)
		self.assertEqual(self.balances, {"A": 10, "B": 10})

	def test_job_card_cancellation_and_reactivation(self):
		active = FakeDocument(parts=[{"part": "A", "qty": 2}], status="In Progress")
		stock.update_stock_from_job_card(active)
		self.assertEqual(self.balances["A"], 8)

		cancelled = FakeDocument(
			parts=deepcopy(active.parts), status="Cancelled", before=active.snapshot()
		)
		stock.update_stock_from_job_card(cancelled)
		self.assertEqual(self.balances["A"], 10)

		cancelled_again = FakeDocument(
			parts=deepcopy(cancelled.parts), status="Cancelled", before=cancelled.snapshot()
		)
		stock.update_stock_from_job_card(cancelled_again)
		self.assertEqual(self.balances["A"], 10)

		reactivated = FakeDocument(
			parts=deepcopy(cancelled.parts), status="In Progress", before=cancelled_again.snapshot()
		)
		stock.update_stock_from_job_card(reactivated)
		self.assertEqual(self.balances["A"], 8)

	def test_deleting_cancelled_job_card_does_not_restore_stock_again(self):
		active = FakeDocument(parts=[{"part": "A", "qty": 2}], status="In Progress")
		stock.update_stock_from_job_card(active)

		cancelled = FakeDocument(
			parts=deepcopy(active.parts), status="Cancelled", before=active.snapshot()
		)
		stock.update_stock_from_job_card(cancelled)
		self.assertEqual(self.balances["A"], 10)

		stock.restore_stock_from_job_card(cancelled)
		stock.restore_stock_from_job_card(cancelled)
		self.assertEqual(self.balances["A"], 10)

	def test_cancelled_job_card_edits_wait_until_reactivation(self):
		active = FakeDocument(parts=[{"part": "A", "qty": 2}], status="In Progress")
		stock.update_stock_from_job_card(active)
		cancelled = FakeDocument(
			parts=deepcopy(active.parts), status="Cancelled", before=active.snapshot()
		)
		stock.update_stock_from_job_card(cancelled)
		self.assertEqual(self.balances, {"A": 10, "B": 10})

		edited_cancelled = FakeDocument(
			parts=[{"part": "A", "qty": 4}, {"part": "B", "qty": 3}],
			status="Cancelled",
			before=cancelled.snapshot(),
		)
		stock.update_stock_from_job_card(edited_cancelled)
		self.assertEqual(self.balances, {"A": 10, "B": 10})

		reactivated = FakeDocument(
			parts=deepcopy(edited_cancelled.parts),
			status="In Progress",
			before=edited_cancelled.snapshot(),
		)
		stock.update_stock_from_job_card(reactivated)
		self.assertEqual(self.balances, {"A": 6, "B": 7})

	def test_sale_repeat_edit_part_change_and_delete(self):
		doc = FakeDocument(doctype="BG Sale", items=[{"part": "A", "qty": 2}])
		stock.update_stock_from_sale(doc)
		self.assertEqual(self.balances["A"], 8)

		doc = FakeDocument(doctype="BG Sale", items=[{"part": "A", "qty": 2}], before=doc.snapshot())
		stock.update_stock_from_sale(doc)
		self.assertEqual(self.balances["A"], 8)

		doc = FakeDocument(doctype="BG Sale", items=[{"part": "A", "qty": 4}], before=doc.snapshot())
		stock.update_stock_from_sale(doc)
		self.assertEqual(self.balances["A"], 6)

		doc = FakeDocument(doctype="BG Sale", items=[{"part": "B", "qty": 3}], before=doc.snapshot())
		stock.update_stock_from_sale(doc)
		self.assertEqual(self.balances, {"A": 10, "B": 7})
		stock.restore_stock_from_sale(doc)
		self.assertEqual(self.balances, {"A": 10, "B": 10})

	def test_insufficient_stock_on_later_part_writes_nothing(self):
		self.balances = {"A": 5, "B": 1}
		doc = FakeDocument(parts=[{"part": "A", "qty": 2}, {"part": "B", "qty": 2}])

		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				stock.update_stock_from_job_card(doc)

		self.assertEqual(self.balances, {"A": 5, "B": 1})
		self.assertEqual(self.save_counts, {})

	def test_second_stock_save_failure_is_distinct_from_validation_failure(self):
		"""Mocks verify the service requests rollback; they do not emulate SQL rollback."""
		original_save = FakeStockPart.save
		save_count = 0
		starting_balances = deepcopy(self.balances)
		starting_save_counts = deepcopy(self.save_counts)

		def fail_on_second_save(stock_doc, ignore_permissions=False):
			nonlocal save_count
			save_count += 1
			if save_count == 2:
				raise RuntimeError("Simulated second stock save failure")
			original_save(stock_doc, ignore_permissions=ignore_permissions)

		savepoint_names = []
		def record_savepoint(name):
			savepoint_names.append(name)

		def emulate_rollback(save_point=None):
			self.assertEqual(save_point, savepoint_names[0])
			self.balances.clear()
			self.balances.update(starting_balances)
			self.save_counts.clear()
			self.save_counts.update(starting_save_counts)

		with (
			patch.object(frappe.db, "savepoint", side_effect=record_savepoint) as savepoint,
			patch.object(frappe.db, "rollback", side_effect=emulate_rollback) as rollback,
			patch.object(FakeStockPart, "save", fail_on_second_save),
		):
			# Simulate an upstream caller catching the original service exception.
			try:
				stock._apply_stock_changes({"A": -2, "B": -2}, garage="GARAGE-A")
			except RuntimeError as error:
				self.assertRegex(str(error), "second stock save")
			else:
				self.fail("Expected the second stock save to fail")

		self.assertEqual(savepoint.call_count, 1)
		self.assertRegex(savepoint_names[0], r"^bg_stock_[0-9a-f]{32}$")
		rollback.assert_called_once_with(save_point=savepoint_names[0])
		self.release_savepoint.assert_not_called()
		self.assertEqual(self.balances, starting_balances)
		self.assertEqual(self.save_counts, starting_save_counts)
		self.assertFalse(stock._is_stock_qty_update_authorized("A"))
		self.assertFalse(stock._is_stock_qty_update_authorized("B"))

	def test_consumed_map_aggregates_multiple_rows_for_one_part(self):
		doc = FakeDocument(parts=[{"part": "A", "qty": 2}, {"part": "A", "qty": 3}])

		self.assertEqual(stock._consumed_map(doc, "parts"), {"A": 5})
		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 5)

		split_rows = FakeDocument(
			parts=[{"part": "A", "qty": 3}, {"part": "A", "qty": 2}],
			before=doc.snapshot(),
		)
		stock.update_stock_from_job_card(split_rows)
		self.assertEqual(self.balances["A"], 5)

	def test_consumed_map_supports_dict_and_attribute_rows(self):
		doc = FakeDocument(
			parts=[
				{"part": "A", "qty": 2},
				SimpleNamespace(part="A", qty=3),
				SimpleNamespace(part="B", qty=1),
			]
		)

		self.assertEqual(stock._consumed_map(doc, "parts"), {"A": 5, "B": 1})

	def test_child_quantities_must_be_strictly_positive(self):
		for controller in (BGJobCardPart, BGSaleItem):
			for qty in (None, 0, -1):
				with self.subTest(controller=controller.__name__, qty=qty):
					with patch.object(frappe, "throw", side_effect=ValueError):
						with self.assertRaises(ValueError):
							controller.validate(SimpleNamespace(qty=qty, rate=0, amount=0, gst_rate=0))

			controller.validate(SimpleNamespace(qty=0.5, rate=0, amount=0, gst_rate=0))

	def test_billing_calculations_remain_unchanged(self):
		job_card = SimpleNamespace(
			parts=[SimpleNamespace(qty=2, rate=12.5, amount=0)],
			labour_charges=7.5,
			amount_paid=10,
			parts_total=0,
			grand_total=0,
			payment_status="Unpaid",
		)
		BGJobCard.calculate_totals(job_card)
		BGJobCard.set_payment_status(job_card)
		self.assertEqual(job_card.parts_total, 25)
		self.assertEqual(job_card.grand_total, 32.5)
		self.assertEqual(job_card.payment_status, "Partially Paid")

		sale = SimpleNamespace(
			items=[SimpleNamespace(qty=2, rate=100, gst_rate=18, amount=0)],
			labour_charges=10,
			subtotal=0,
			gst_amount=0,
			grand_total=0,
		)
		BGSale.calculate_totals(sale)
		self.assertEqual(sale.subtotal, 200)
		self.assertEqual(sale.gst_amount, 36)
		self.assertEqual(sale.grand_total, 246)

	def test_job_card_payment_status_boundaries(self):
		job_card = SimpleNamespace(grand_total=32.5, amount_paid=0, payment_status="Paid")

		BGJobCard.set_payment_status(job_card)
		self.assertEqual(job_card.payment_status, "Unpaid")

		job_card.amount_paid = job_card.grand_total
		BGJobCard.set_payment_status(job_card)
		self.assertEqual(job_card.payment_status, "Paid")

		job_card.amount_paid = job_card.grand_total + 1
		BGJobCard.set_payment_status(job_card)
		self.assertEqual(job_card.payment_status, "Paid")

	def test_historical_import_scope_skips_only_imported_stock_deltas(self):
		doc = FakeDocument(parts=[{"part": "A", "qty": 2}])

		with stock._historical_import_scope(stock._HISTORICAL_IMPORT_CAPABILITY):
			stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 10)
		self.get_doc_mock.assert_not_called()

		stock.update_stock_from_job_card(doc)
		self.assertEqual(self.balances["A"], 8)

	def test_historical_import_scope_allows_snapshot_stock_on_new_parts_only(self):
		new_part = SimpleNamespace(
			stock_qty=7,
			purchase_price=0,
			selling_price=0,
			min_stock_qty=0,
			gst_rate="0",
			is_new=lambda: True,
		)
		with stock._historical_import_scope(stock._HISTORICAL_IMPORT_CAPABILITY):
			BGSparePart.validate(new_part)

		new_part.stock_qty = 7
		with patch.object(frappe, "throw", side_effect=ValueError):
			with self.assertRaises(ValueError):
				BGSparePart.validate(new_part)
