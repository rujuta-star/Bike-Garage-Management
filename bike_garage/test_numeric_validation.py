import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage.bike_garage.doctype.bg_expense.bg_expense import BGExpense
from bike_garage.bike_garage.doctype.bg_garage_subscription.bg_garage_subscription import BGGarageSubscription
from bike_garage.bike_garage.doctype.bg_job_card.bg_job_card import BGJobCard
from bike_garage.bike_garage.doctype.bg_job_card_part.bg_job_card_part import BGJobCardPart
from bike_garage.bike_garage.doctype.bg_sale.bg_sale import BGSale
from bike_garage.bike_garage.doctype.bg_sale_item.bg_sale_item import BGSaleItem
from bike_garage.bike_garage.doctype.bg_spare_part.bg_spare_part import BGSparePart
from bike_garage.bike_garage.doctype.bg_subscription_plan.bg_subscription_plan import BGSubscriptionPlan
from bike_garage import payments, stock


class TestNumericValidation(unittest.TestCase):
	def test_job_card_payment_amount_changes_require_financial_role(self):
		previous = SimpleNamespace(amount_paid=10)
		doc = SimpleNamespace(
			labour_charges=0, amount_paid=10, garage="GARAGE-1",
			get_doc_before_save=lambda: previous,
		)

		with patch.object(payments, "require_payment_role") as require_payment_role:
			BGJobCard.validate(doc)
		require_payment_role.assert_not_called()

		doc.amount_paid = 11
		with patch.object(
			payments, "require_payment_role", side_effect=frappe.PermissionError
		) as require_payment_role:
			with self.assertRaises(frappe.PermissionError):
				BGJobCard.validate(doc)
		require_payment_role.assert_called_once_with("GARAGE-1")

		with patch.object(payments, "require_payment_role") as require_payment_role:
			BGJobCard.validate(
				SimpleNamespace(
					labour_charges=0, amount_paid=1, garage="GARAGE-1",
					get_doc_before_save=lambda: None,
				)
			)
		require_payment_role.assert_called_once_with("GARAGE-1")

	def test_job_card_part_quantity_rejects_non_finite_and_non_positive_values(self):
		for quantity in (float("nan"), float("inf"), float("-inf"), 0, -1):
			with self.subTest(quantity=quantity):
				row = SimpleNamespace(qty=quantity, rate=0, amount=0)
				with self.assertRaises(frappe.ValidationError):
					BGJobCardPart.validate(row)

	def test_sale_item_quantity_and_tax_percentage_boundaries(self):
		for quantity in (float("nan"), float("inf"), float("-inf"), 0, -0.1):
			with self.subTest(quantity=quantity):
				row = SimpleNamespace(qty=quantity, rate=0, gst_rate=0, amount=0)
				with self.assertRaises(frappe.ValidationError):
					BGSaleItem.validate(row)
		for gst_rate in (0, 100):
			BGSaleItem.validate(SimpleNamespace(qty=0.25, rate=0, gst_rate=gst_rate, amount=0))
		for gst_rate in (-1, 100.01, float("nan"), float("inf"), float("-inf")):
			with self.subTest(gst_rate=gst_rate):
				with self.assertRaises(frappe.ValidationError):
					BGSaleItem.validate(SimpleNamespace(qty=1, rate=0, gst_rate=gst_rate, amount=0))

	def test_nonnegative_job_card_sale_and_expense_amounts(self):
		for amount in (float("nan"), float("inf"), float("-inf"), -0.01):
			with self.subTest(amount=amount):
				with self.assertRaises(frappe.ValidationError):
					BGJobCard.validate(SimpleNamespace(labour_charges=amount, amount_paid=0))
				with self.assertRaises(frappe.ValidationError):
					BGJobCard.validate(SimpleNamespace(labour_charges=0, amount_paid=amount))
				with self.assertRaises(frappe.ValidationError):
					BGSale.validate(SimpleNamespace(labour_charges=amount, is_new=lambda: False, get_doc_before_save=lambda: None))
				with self.assertRaises(frappe.ValidationError):
					BGExpense.validate(SimpleNamespace(amount=amount))
		BGJobCard.validate(SimpleNamespace(labour_charges=0, amount_paid=0))
		BGSale.validate(SimpleNamespace(labour_charges=0, is_new=lambda: False, get_doc_before_save=lambda: None))
		BGExpense.validate(SimpleNamespace(amount=0))

	def test_negative_rates_and_computed_overflow_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			BGJobCardPart.validate(SimpleNamespace(qty=1, rate=-0.01, amount=0))
		with self.assertRaises(frappe.ValidationError):
			BGSaleItem.validate(SimpleNamespace(qty=1, rate=-0.01, gst_rate=0, amount=0))
		card = SimpleNamespace(parts=[SimpleNamespace(qty=1e308, rate=1e308, amount=0)], labour_charges=0)
		with self.assertRaises(frappe.ValidationError):
			BGJobCard.calculate_totals(card)
		sale = SimpleNamespace(items=[SimpleNamespace(qty=1e308, rate=1e308, gst_rate=0, amount=0)], labour_charges=0)
		with self.assertRaises(frappe.ValidationError):
			BGSale.calculate_totals(sale)

	def test_spare_part_money_and_stock_inputs_are_finite_and_nonnegative(self):
		def part(**overrides):
			values = {
				"purchase_price": 0, "selling_price": 0, "min_stock_qty": 0,
				"stock_qty": 0, "gst_rate": "0", "is_new": lambda: True,
			}
			values.update(overrides)
			return SimpleNamespace(**values)
		for field in ("purchase_price", "selling_price", "min_stock_qty", "stock_qty"):
			for amount in (float("nan"), float("inf"), float("-inf"), -0.01):
				with self.subTest(field=field, amount=amount):
					with self.assertRaises(frappe.ValidationError):
						BGSparePart.validate(part(**{field: amount}))
		BGSparePart.validate(part())
		for gst_rate in ("0", "5", "12", "18", "28", 18.0):
			BGSparePart.validate(part(gst_rate=gst_rate))
		for gst_rate in ("-1", "NaN", "Infinity", "4"):
			with self.subTest(gst_rate=gst_rate):
				with self.assertRaises(frappe.ValidationError):
					BGSparePart.validate(part(gst_rate=gst_rate))

	def test_subscription_plan_amount_validation(self):
		def plan(amount):
			return SimpleNamespace(
				plan_name="Plan A", status="Active", billing_period="Monthly",
				amount=amount, currency="INR",
			)
		with patch.object(frappe.db, "exists", return_value=True):
			for amount in (float("nan"), float("inf"), float("-inf"), -1):
				with self.subTest(amount=amount):
					with self.assertRaises(frappe.ValidationError):
						BGSubscriptionPlan.validate(plan(amount))
				BGSubscriptionPlan.validate(plan(0))

	def test_garage_subscription_agreed_amount_validation(self):
		def subscription(amount):
			return SimpleNamespace(
				status="Pending", billing_period="Monthly", garage="G-1", plan="P-1",
				is_new=lambda: True, get_doc_before_save=lambda: None,
				start_date="2026-01-01", end_date="2026-01-31", agreed_amount=amount,
				currency="INR", payment_reference="", payment_status="Pending",
			)
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value="Active"),
		):
			for amount in (float("nan"), float("inf"), float("-inf"), -1):
				with self.subTest(amount=amount):
					with self.assertRaises(frappe.ValidationError):
						BGGarageSubscription.validate(subscription(amount))
			BGGarageSubscription.validate(subscription(0))

	def test_stock_service_rejects_non_finite_quantities_before_loading_parts(self):
		with patch.object(frappe, "get_doc") as get_doc:
			with self.assertRaises(frappe.ValidationError):
				stock._apply_stock_changes({"PART-1": float("nan")}, garage="GARAGE-A")
		get_doc.assert_not_called()
		for quantity in (0, -1, float("inf"), float("-inf"), float("nan")):
			with self.subTest(quantity=quantity):
				with self.assertRaises(frappe.ValidationError):
					stock._consumed_map(
						SimpleNamespace(get=lambda field: [{"part": "PART-1", "qty": quantity}]),
						"parts",
					)


if __name__ == "__main__":
	unittest.main()
