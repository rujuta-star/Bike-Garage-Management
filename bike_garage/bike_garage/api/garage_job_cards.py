"""Website-facing Job Card operations scoped to the session garage."""

import frappe
from frappe import _

from bike_garage import payments, permissions, tenancy


LIST_FIELDS = ["name", "customer", "bike", "registration_no", "status", "date"]
DETAIL_FIELDS = LIST_FIELDS + ["estimated_delivery", "problem_description"]


def _garage_job_cards(fields, filters=None, limit=200):
	garage = tenancy.get_current_garage()
	query_filters = {"garage": garage}
	if filters:
		query_filters.update(filters)
	# This API is the deliberately field-limited read path for staff roles. Direct
	# BG Job Card resource reads are blocked for members without payment access.
	return frappe.get_all(
		"BG Job Card",
		filters=query_filters,
		fields=fields,
		order_by="date desc, modified desc",
		limit_page_length=limit,
	)


@frappe.whitelist(methods=["GET"])
def get_job_cards():
	"""List Job Cards visible to the authenticated user's active garage."""
	garage = tenancy.get_current_garage()
	fields = LIST_FIELDS.copy()
	if payments.can_read_payment_data(garage):
		fields.extend(["grand_total", "payment_status"])
	return _garage_job_cards(fields)


@frappe.whitelist(methods=["GET"])
def get_job_card_form_options():
	"""Return only this garage's customer and bike choices."""
	garage = tenancy.get_current_garage()
	return {
		"customers": frappe.get_list(
			"BG Customer",
			filters={"garage": garage},
			fields=["name", "customer_name"],
			order_by="customer_name asc",
			limit_page_length=500,
		),
		"bikes": frappe.get_list(
			"BG Bike",
			filters={"garage": garage},
			fields=["name", "customer", "registration_no", "bike_brand", "bike_model"],
			order_by="registration_no asc",
			limit_page_length=500,
		),
	}


def _get_job_card_for_current_garage(name):
	if not isinstance(name, str) or not name.strip():
		frappe.throw(_("Job Card was not found."), frappe.DoesNotExistError)
	rows = _garage_job_cards(DETAIL_FIELDS, {"name": name.strip()}, limit=1)
	if not rows:
		# Same response for absent and cross-garage names to avoid disclosing existence.
		frappe.throw(_("Job Card was not found."), frappe.DoesNotExistError)
	return rows[0]


@frappe.whitelist(methods=["GET"])
def get_job_card(name):
	"""Read a single Job Card only through the session garage's scoped query."""
	return _get_job_card_for_current_garage(name)


@frappe.whitelist(methods=["POST"])
def create_job_card(customer, problem_description, bike=None):
	"""Create a no-parts Job Card using existing DocType validations.

	Garage ownership is derived from the session membership. Parts are deliberately
	not accepted here because the app has no verified stock-in workflow.
	"""
	garage = tenancy.get_current_garage()
	if not isinstance(customer, str) or not customer.strip():
		frappe.throw(_("Choose a customer."), frappe.ValidationError)
	if bike is not None and (not isinstance(bike, str) or not bike.strip()):
		frappe.throw(_("Choose a valid bike or leave it blank."), frappe.ValidationError)
	if not isinstance(problem_description, str):
		frappe.throw(_("Describe the reported problem."), frappe.ValidationError)
	problem_description = problem_description.strip()
	if not problem_description or len(problem_description) > 2000:
		frappe.throw(_("Problem description is required and must be at most 2000 characters."), frappe.ValidationError)
	doc = frappe.get_doc(
		{
			"doctype": "BG Job Card",
			"customer": customer.strip(),
			"bike": bike.strip() if bike else None,
			"date": frappe.utils.today(),
			"problem_description": problem_description,
			"parts": [],
		}
	)
	doc.garage = garage
	# Reuse the same server-side link checks as the DocType validation hook before
	# insert, then let normal insert/DocType hooks perform the full validation.
	permissions._validate_linked_garage_references(doc)
	doc.insert()
	return {"name": doc.name}
