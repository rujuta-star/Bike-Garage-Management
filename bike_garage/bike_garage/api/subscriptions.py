"""Platform-admin-only subscription records; this module does not collect money."""

import frappe
from frappe import _

from bike_garage.bike_garage.api.onboarding import _require_platform_super_admin


PLAN_FIELDS = ["name", "status", "billing_period", "amount", "currency", "description"]
SUBSCRIPTION_FIELDS = [
	"name",
	"garage",
	"plan",
	"status",
	"start_date",
	"end_date",
	"billing_period",
	"agreed_amount",
	"currency",
	"payment_status",
	"payment_reference",
]
SUBSCRIPTION_STATUSES = {"Pending", "Active", "Suspended", "Cancelled", "Expired"}
PLAN_STATUSES = {"Active", "Inactive"}
BILLING_PERIODS = {"Monthly", "Quarterly", "Yearly"}


def _text(value, label, max_length, required=False):
	if value is None:
		value = ""
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)
	value = " ".join(value.strip().split())
	if required and not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > max_length:
		frappe.throw(_("{0} is too long.").format(label), frappe.ValidationError)
	return value


@frappe.whitelist()
def get_platform_subscription_data(query="", status="All", start=0, page_length=20):
	"""Return plans and subscription terms, never a platform revenue estimate."""
	_require_platform_super_admin()
	query = " ".join(query.strip().split()) if isinstance(query, str) else ""
	if len(query) > 100:
		frappe.throw(_("Search text is too long."), frappe.ValidationError)
	if not isinstance(status, str) or (status != "All" and status not in SUBSCRIPTION_STATUSES):
		frappe.throw(_("Unsupported subscription filter."), frappe.ValidationError)
	try:
		start = int(start)
		page_length = int(page_length)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid page selection."), frappe.ValidationError)
	if start < 0 or page_length < 1:
		frappe.throw(_("Invalid page selection."), frappe.ValidationError)
	page_length = min(page_length, 100)
	plans = frappe.get_all(
		"BG Subscription Plan", fields=PLAN_FIELDS, order_by="plan_name asc", limit_page_length=500
	)
	filters = {"status": status} if status != "All" else {}
	or_filters = [{field: ["like", f"%{query}%"]} for field in ("garage", "plan")] if query else []
	subscriptions = frappe.get_all(
		"BG Garage Subscription", filters=filters, or_filters=or_filters, fields=SUBSCRIPTION_FIELDS,
		order_by="modified desc", start=start, page_length=page_length,
	)
	if query:
		total = len(frappe.get_all("BG Garage Subscription", filters=filters, or_filters=or_filters,
			fields=["name"], limit_page_length=0))
	else:
		total = frappe.db.count("BG Garage Subscription", filters)
	return {
		"plans": plans,
		"subscriptions": subscriptions,
		"subscription_total": total,
		"subscription_start": start,
		"subscription_page_length": page_length,
		"payment_notice": _(
			"Payment confirmation is not integrated. References are Pending or Unverified; no collected revenue is reported."
		),
	}


@frappe.whitelist(methods=["POST"])
def save_subscription_plan(plan_name, billing_period, amount, currency, status="Active", description=None):
	"""Create or update a plan. Existing subscriptions retain agreed-term snapshots."""
	_require_platform_super_admin()
	plan_name = _text(plan_name, _("Plan name"), 140, required=True)
	if not isinstance(billing_period, str) or billing_period not in BILLING_PERIODS:
		frappe.throw(_("Unsupported billing period."), frappe.ValidationError)
	if not isinstance(status, str) or status not in PLAN_STATUSES:
		frappe.throw(_("Unsupported plan status."), frappe.ValidationError)
	currency = _text(currency, _("Currency"), 3, required=True).upper()
	description = _text(description, _("Description"), 2000)

	if frappe.db.exists("BG Subscription Plan", plan_name):
		plan = frappe.get_doc("BG Subscription Plan", plan_name)
	else:
		plan = frappe.get_doc({"doctype": "BG Subscription Plan", "plan_name": plan_name})
	plan.billing_period = billing_period
	plan.amount = amount
	plan.currency = currency
	plan.status = status
	plan.description = description
	if plan.is_new():
		plan.insert(ignore_permissions=True)
	else:
		plan.save(ignore_permissions=True)
	return {"name": plan.name, "status": plan.status}


@frappe.whitelist(methods=["POST"])
def create_garage_subscription(
	garage,
	plan,
	start_date,
	end_date,
	agreed_amount=None,
	currency=None,
	billing_period=None,
	payment_reference=None,
):
	"""Create a Pending subscription using a snapshot of the selected plan terms."""
	_require_platform_super_admin()
	garage = _text(garage, _("Garage"), 140, required=True)
	plan_name = _text(plan, _("Plan"), 140, required=True)
	if not frappe.db.exists("BG Garage", garage):
		frappe.throw(_("The selected garage does not exist."), frappe.DoesNotExistError)
	try:
		plan_doc = frappe.get_doc("BG Subscription Plan", plan_name)
	except frappe.DoesNotExistError:
		frappe.throw(_("The selected subscription plan does not exist."), frappe.DoesNotExistError)
	if plan_doc.status != "Active":
		frappe.throw(_("New subscriptions require an active plan."), frappe.ValidationError)

	subscription = frappe.get_doc(
		{
			"doctype": "BG Garage Subscription",
			"garage": garage,
			"plan": plan_doc.name,
			"status": "Pending",
			"start_date": start_date,
			"end_date": end_date,
			"billing_period": billing_period or plan_doc.billing_period,
			"agreed_amount": plan_doc.amount if agreed_amount is None else agreed_amount,
			"currency": _text(currency or plan_doc.currency or "", _("Currency"), 3, required=True).upper(),
			"payment_status": "Pending",
			"payment_reference": _text(payment_reference, _("Payment reference"), 140),
		}
	)
	subscription.insert(ignore_permissions=True)
	return {"name": subscription.name, "status": subscription.status, "payment_status": subscription.payment_status}


@frappe.whitelist(methods=["POST"])
def update_garage_subscription(subscription_name, status, payment_reference=None):
	"""Update administrative status/reference; payment confirmation is unavailable."""
	_require_platform_super_admin()
	subscription_name = _text(subscription_name, _("Subscription"), 140, required=True)
	if not isinstance(status, str) or status not in SUBSCRIPTION_STATUSES:
		frappe.throw(_("Unsupported subscription status."), frappe.ValidationError)
	try:
		subscription = frappe.get_doc("BG Garage Subscription", subscription_name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Subscription was not found."), frappe.DoesNotExistError)
	subscription.status = status
	if payment_reference is not None:
		subscription.payment_reference = _text(payment_reference, _("Payment reference"), 140)
	subscription.save(ignore_permissions=True)
	return {
		"name": subscription.name,
		"status": subscription.status,
		"payment_status": subscription.payment_status,
	}
