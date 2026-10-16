import unittest
from unittest.mock import patch

import frappe

from bike_garage import permissions, tenancy
from bike_garage.bike_garage.api import reports


class TestJobCardPartReport(unittest.TestCase):
	def setUp(self):
		self.garage = "GARAGE-A"
		self.jobs_by_garage = {
			"GARAGE-A": [["JOB-A"]],
			"GARAGE-B": [["JOB-B"]],
		}
		self.parts_by_parent = {
			"JOB-A": [{"part": "Part A", "qty": 2, "amount": 20}],
			"JOB-B": [{"part": "Part B", "qty": 3, "amount": 30}],
		}
		self.garage_patch = patch.object(tenancy, "get_current_garage", side_effect=self.resolve_garage)
		self.get_current_garage = self.garage_patch.start()
		self.addCleanup(self.garage_patch.stop)
		self.ownership_patch = patch.object(permissions, "_ownership_field_available", return_value=True)
		self.ownership_available = self.ownership_patch.start()
		self.addCleanup(self.ownership_patch.stop)
		self.payment_access_patch = patch(
			"bike_garage.bike_garage.api.reports.payments.require_payment_read_access",
			return_value="GARAGE-A",
		)
		self.payment_access_patch.start()
		self.addCleanup(self.payment_access_patch.stop)
		self.parents_patch = patch.object(frappe, "get_list", side_effect=self.get_job_cards)
		self.get_list = self.parents_patch.start()
		self.addCleanup(self.parents_patch.stop)
		self.parts_patch = patch.object(frappe, "get_all", side_effect=self.get_part_rows)
		self.get_all = self.parts_patch.start()
		self.addCleanup(self.parts_patch.stop)

	def resolve_garage(self):
		return self.garage

	def get_job_cards(self, doctype, **kwargs):
		self.assertEqual(doctype, "BG Job Card")
		self.assertEqual(kwargs["filters"], {"garage": self.garage})
		self.assertEqual(kwargs["fields"], ["name"])
		self.assertTrue(kwargs["as_list"])
		self.assertEqual(kwargs["limit_page_length"], 0)
		return self.jobs_by_garage[self.garage]

	def get_part_rows(self, doctype, **kwargs):
		self.assertEqual(doctype, "BG Job Card Part")
		filters = kwargs["filters"]
		parent_names = filters["parent"][1]
		self.assertEqual(filters["parenttype"], "BG Job Card")
		self.assertEqual(filters["parentfield"], "parts")
		self.assertEqual(kwargs["fields"], ["part", "qty", "amount"])
		self.assertEqual(kwargs["limit_page_length"], 500)
		return [row for name in parent_names for row in self.parts_by_parent.get(name, [])]

	def test_two_garages_only_receive_child_rows_from_their_authorized_parents(self):
		for garage, expected_part in (("GARAGE-A", "Part A"), ("GARAGE-B", "Part B")):
			with self.subTest(garage=garage):
				self.garage = garage
				result = reports.get_job_card_part_report()
				self.assertEqual([row["part"] for row in result], [expected_part])
				self.assertEqual(self.get_list.call_args.kwargs["filters"], {"garage": garage})
				self.assertEqual(
					self.get_all.call_args.kwargs["filters"]["parent"][1],
					[self.jobs_by_garage[garage][0][0]],
				)
				self.get_list.reset_mock()
				self.get_all.reset_mock()

	def test_missing_membership_propagates_without_querying(self):
		self.get_current_garage.side_effect = frappe.PermissionError("No active garage")
		with self.assertRaises(frappe.PermissionError):
			reports.get_job_card_part_report()
		self.get_list.assert_not_called()
		self.get_all.assert_not_called()

	def test_empty_parent_results_return_an_empty_report(self):
		self.jobs_by_garage[self.garage] = []
		self.assertEqual(reports.get_job_card_part_report(), [])
		self.get_list.assert_called_once()
		self.get_all.assert_not_called()

	def test_missing_ownership_schema_fails_instead_of_appearing_empty(self):
		self.ownership_available.return_value = False
		with self.assertRaises(frappe.PermissionError):
			reports.get_job_card_part_report()
		self.get_list.assert_not_called()
		self.assertFalse(any(call.args and call.args[0] == "BG Job Card Part" for call in self.get_all.call_args_list))
