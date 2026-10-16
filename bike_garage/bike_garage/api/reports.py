"""Garage-scoped reporting endpoints for the Bike Garage UI."""

import frappe

from bike_garage import payments, permissions, tenancy


@frappe.whitelist()
def get_job_card_part_report():
	"""Return Job Card Part rows only through Job Cards in the session garage."""
	garage = tenancy.get_current_garage()
	payments.require_payment_read_access(garage)
	if not permissions._ownership_field_available("BG Job Card"):
		frappe.throw(
			"Garage ownership is not available for Job Card reporting.",
			frappe.PermissionError,
		)

	job_cards = frappe.get_list(
		"BG Job Card",
		filters={"garage": garage},
		fields=["name"],
		as_list=True,
		limit_page_length=0,
	)
	job_card_names = [row[0] for row in job_cards]
	if not job_card_names:
		return []

	return frappe.get_all(
		"BG Job Card Part",
		filters={
			"parent": ["in", job_card_names],
			"parenttype": "BG Job Card",
			"parentfield": "parts",
		},
		fields=["part", "qty", "amount"],
		limit_page_length=500,
	)
