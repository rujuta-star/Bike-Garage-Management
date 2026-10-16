import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate
from bike_garage.numeric import validate_number


SUBSCRIPTION_TRANSITIONS = {
	"Pending": {"Pending", "Active", "Cancelled"},
	"Active": {"Active", "Suspended", "Cancelled", "Expired"},
	"Suspended": {"Suspended", "Active", "Cancelled", "Expired"},
	"Cancelled": {"Cancelled"},
	"Expired": {"Expired"},
}


class BGGarageSubscription(Document):
	def validate(self):
		if not isinstance(self.status, str) or self.status not in SUBSCRIPTION_TRANSITIONS:
			frappe.throw(_("Unsupported subscription status."), frappe.ValidationError)
		if not isinstance(self.billing_period, str) or self.billing_period not in {"Monthly", "Quarterly", "Yearly"}:
			frappe.throw(_("Unsupported billing period."), frappe.ValidationError)
		if not self.garage or not frappe.db.exists("BG Garage", self.garage):
			frappe.throw(_("Select an existing garage."), frappe.ValidationError)
		previous = self.get_doc_before_save()
		if self.is_new() and self.status != "Pending":
			frappe.throw(_("New subscriptions must begin in Pending status."), frappe.ValidationError)
		if previous and self.status not in SUBSCRIPTION_TRANSITIONS.get(previous.status, set()):
			frappe.throw(_("This subscription status transition is not allowed."), frappe.ValidationError)
		if previous and self.garage != previous.garage:
			frappe.throw(_("A subscription cannot be transferred to another garage."), frappe.ValidationError)

		plan_status = frappe.db.get_value("BG Subscription Plan", self.plan, "status") if self.plan else None
		if not plan_status:
			frappe.throw(_("Select an existing subscription plan."), frappe.ValidationError)
		if self.is_new() and plan_status != "Active":
			frappe.throw(_("New subscriptions require an active plan."), frappe.ValidationError)
		if self.status == "Active":
			# An active subscription keeps its agreed terms if the plan is later
			# retired. Require an active plan only when entering Active status.
			entering_active = not previous or previous.status != "Active"
			if entering_active and plan_status != "Active":
				frappe.throw(_("An active subscription requires an active plan."), frappe.ValidationError)
			if frappe.db.get_value("BG Garage", self.garage, "status") != "Active":
				frappe.throw(_("A subscription can be activated only for an active garage."), frappe.ValidationError)

		if not self.start_date or not self.end_date:
			frappe.throw(_("Valid subscription start and end dates are required."), frappe.ValidationError)
		try:
			start_date = getdate(self.start_date)
			end_date = getdate(self.end_date)
		except Exception:
			frappe.throw(_("Valid subscription start and end dates are required."), frappe.ValidationError)
		if end_date < start_date:
			frappe.throw(_("Subscription end date cannot precede its start date."), frappe.ValidationError)

		validate_number(self.agreed_amount, _("Agreed amount"), minimum=0)
		if not self.currency or not frappe.db.exists("Currency", self.currency):
			frappe.throw(_("Select an existing currency."), frappe.ValidationError)

		reference = (self.payment_reference or "").strip()
		if len(reference) > 140:
			frappe.throw(_("Payment reference must be 140 characters or fewer."), frappe.ValidationError)
		self.payment_reference = reference or None
		if self.payment_status not in {"Pending", "Unverified"}:
			frappe.throw(_("Payment cannot be marked confirmed without an independent payment verification integration."), frappe.ValidationError)
		self.payment_status = "Unverified" if reference else "Pending"

		# This hidden unique key makes the one-active-subscription-per-garage rule
		# race-safe at the database constraint level. It is derived server-side.
		self.active_garage = self.garage if self.status == "Active" else None
		if self.status == "Active" and frappe.db.exists(
			"BG Garage Subscription",
			{"active_garage": self.garage, "name": ["!=", self.name]},
		):
			frappe.throw(_("This garage already has an active subscription."), frappe.ValidationError)
