import unittest
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from bike_garage.bike_garage.api import garage_job_cards as api


class FakeJobCard:
	def __init__(self, values):
		self.values = values
		self.doctype = values["doctype"]
		self.name = "JC-0001"
		self.garage = None
		self.inserted = False

	def get(self, fieldname):
		if fieldname == "garage":
			return self.garage
		return self.values.get(fieldname)

	def insert(self):
		self.inserted = True
		return self


class TestGarageWebsiteJobCards(unittest.TestCase):
	def setUp(self):
		self.garage = patch.object(api.tenancy, "get_current_garage", return_value="GARAGE-A")
		self.garage.start()
		self.addCleanup(self.garage.stop)
		self.get_list = patch.object(frappe, "get_list", return_value=[])
		self.get_list_mock = self.get_list.start()
		self.addCleanup(self.get_list.stop)

	def test_list_is_scoped_to_resolved_garage(self):
		api.get_job_cards()
		self.assertEqual(self.get_list_mock.call_args.kwargs["filters"], {"garage": "GARAGE-A"})
		self.assertIn("bike", self.get_list_mock.call_args.kwargs["fields"])

	def test_missing_membership_denies_list_before_query(self):
		api.tenancy.get_current_garage.side_effect = frappe.PermissionError("No active garage")
		with self.assertRaises(frappe.PermissionError):
			api.get_job_cards()
		self.get_list_mock.assert_not_called()

	def test_form_choices_are_scoped_to_resolved_garage(self):
		api.get_job_card_form_options()
		self.assertEqual(
			[self.get_list_mock.call_args_list[i].kwargs["filters"] for i in range(2)],
			[{"garage": "GARAGE-A"}, {"garage": "GARAGE-A"}],
		)

	def test_create_derives_garage_and_inserts_no_parts(self):
		job = FakeJobCard({"doctype": "BG Job Card", "customer": "CUSTOMER-A", "bike": "BIKE-A", "parts": []})
		with (
			patch.object(frappe, "get_doc", return_value=job),
			patch.object(frappe.db, "get_value", side_effect=["GARAGE-A", "GARAGE-A", "CUSTOMER-A"]),
			patch.object(frappe.utils, "today", return_value="2026-10-13"),
		):
			result = api.create_job_card("CUSTOMER-A", "Brake noise", "BIKE-A")
		self.assertEqual(result, {"name": "JC-0001"})
		self.assertEqual(job.garage, "GARAGE-A")
		self.assertEqual(job.values["parts"], [])
		self.assertTrue(job.inserted)
		self.assertNotIn("garage", inspect.signature(api.create_job_card).parameters)
		self.assertNotIn("parts", inspect.signature(api.create_job_card).parameters)

	def test_create_rejects_cross_garage_customer_before_insert(self):
		job = FakeJobCard({"doctype": "BG Job Card", "customer": "CUSTOMER-B", "bike": None, "parts": []})
		with (
			patch.object(frappe, "get_doc", return_value=job),
			patch.object(frappe.db, "get_value", return_value="GARAGE-B"),
			self.assertRaises(frappe.PermissionError),
		):
			api.create_job_card("CUSTOMER-B", "Brake noise")
		self.assertFalse(job.inserted)

	def test_create_rejects_bike_owned_by_another_customer(self):
		job = FakeJobCard({"doctype": "BG Job Card", "customer": "CUSTOMER-A", "bike": "BIKE-A", "parts": []})
		with (
			patch.object(frappe, "get_doc", return_value=job),
			patch.object(frappe.db, "get_value", side_effect=["GARAGE-A", "GARAGE-A", "CUSTOMER-B"]),
			self.assertRaises(frappe.PermissionError),
		):
			api.create_job_card("CUSTOMER-A", "Brake noise", "BIKE-A")
		self.assertFalse(job.inserted)

	def test_cross_garage_or_missing_job_card_has_same_not_found_response(self):
		with self.assertRaises(frappe.DoesNotExistError) as error:
			api.get_job_card("JC-OTHER-GARAGE")
		self.assertIn("Job Card was not found", str(error.exception))
		self.assertEqual(self.get_list_mock.call_args.kwargs["filters"], {"garage": "GARAGE-A", "name": "JC-OTHER-GARAGE"})

	def test_detail_query_returns_only_requested_garage_fields(self):
		self.get_list_mock.return_value = [{"name": "JC-0001", "customer": "CUSTOMER-A", "status": "Pending"}]
		result = api.get_job_card("JC-0001")
		self.assertEqual(result["name"], "JC-0001")
		self.assertEqual(self.get_list_mock.call_args.kwargs["filters"], {"garage": "GARAGE-A", "name": "JC-0001"})

	def test_guest_or_inactive_membership_cannot_render_create_page_context(self):
		from bike_garage.www import job_card_new
		context = SimpleNamespace()
		with (
			patch.object(api.tenancy, "get_current_garage", side_effect=frappe.PermissionError("No membership")),
			self.assertRaises(frappe.PermissionError),
		):
			job_card_new.get_context(context)
		self.get_list_mock.assert_not_called()
