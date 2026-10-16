"""Public garage onboarding and explicitly authorized platform administration."""

import hashlib
import hmac
import secrets
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, now_datetime, validate_email_address
from frappe.utils.data import escape_html
from frappe.utils.html_utils import sanitize_html

from bike_garage import tenancy


REGISTRATION_ACKNOWLEDGEMENT = _(
	"If this is a new request, it has been saved as Pending review. If an account or application already exists for this email, no duplicate was created. No email is sent at this stage; registration instructions are sent only after approval when outgoing email is configured."
)
REGISTRATION_TOKEN_HOURS = 48
MEMBERSHIP_STATUSES = ("Pending", "Active", "Suspended")
MEMBERSHIP_TYPES = (
	"Owner",
	"Manager",
	"Service Advisor",
	"Technician",
	"Inventory Manager",
	"Accountant",
)


def _clean_text(value, label, max_length, required=False, multiline=False):
	if value is None:
		value = ""
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)
	value = value.replace("\x00", "").strip()
	if not multiline:
		value = " ".join(value.split())
	if required and not value:
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	if len(value) > max_length:
		frappe.throw(_("{0} is too long.").format(label), frappe.ValidationError)
	value = sanitize_html(value, always_sanitize=True, disallowed_tags="*")
	if required and not value.strip():
		frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
	return value


def _normalize_registration(garage_name, owner_name, email, phone, address, city, state, pin_code):
	garage_name = _clean_text(garage_name, _("Garage name"), 140, required=True)
	owner_name = _clean_text(owner_name, _("Owner name"), 140, required=True)
	phone = _clean_text(phone, _("Phone"), 40, required=True)
	if not isinstance(email, str):
		frappe.throw(_("A valid email address is required."), frappe.ValidationError)
	email = email.strip().lower()
	if not email or len(email) > 254 or "," in email or ";" in email:
		frappe.throw(_("A valid email address is required."), frappe.ValidationError)
	validated_email = validate_email_address(email, throw=True)
	if validated_email.lower() != email:
		frappe.throw(_("Enter one email address only."), frappe.ValidationError)
	return {
		"garage_name": garage_name,
		"owner_name": owner_name,
		"email": email,
		"phone": phone,
		"address": _clean_text(address, _("Address"), 500, multiline=True),
		"city": _clean_text(city, _("City"), 100),
		"state": _clean_text(state, _("State"), 100),
		"pin_code": _clean_text(pin_code, _("PIN code"), 20),
	}


def _registration_already_exists(email):
	# Keep public acknowledgements generic for existing users/applications.
	return bool(
		frappe.db.exists("User", email)
		or frappe.db.exists("BG Garage", {"email": email})
	)


@contextmanager
def _registration_lock(email):
	"""Serialize requests for the same address across workers without storing it in Redis keys."""
	key = hashlib.sha256(email.encode("utf-8")).hexdigest()
	lock = frappe.cache.lock(f"bike_garage:registration:{key}", timeout=60, blocking_timeout=10)
	if not lock.acquire(blocking=True):
		frappe.throw(_("We could not submit this request. Please try again later."), frappe.ValidationError)
	try:
		yield
	finally:
		lock.release()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60, methods=["POST"], ip_based=True)
def submit_garage_registration(
	garage_name=None,
	owner_name=None,
	email=None,
	phone=None,
	address=None,
	city=None,
	state=None,
	pin_code=None,
):
	"""Persist a Pending application without creating a user or membership."""
	if getattr(frappe.session, "user", None) != "Guest":
		frappe.throw(_("Submit a public registration request while signed out."), frappe.PermissionError)

	values = _normalize_registration(
		garage_name, owner_name, email, phone, address, city, state, pin_code
	)
	with _registration_lock(values["email"]):
		try:
			if _registration_already_exists(values["email"]):
				return {"message": REGISTRATION_ACKNOWLEDGEMENT}
		except Exception:
			frappe.log_error(title="Garage registration duplicate check failed", message=frappe.get_traceback())
			frappe.throw(
				_("We could not submit this request. Please try again later."),
				frappe.ValidationError,
			)

		try:
			garage = frappe.get_doc(
				{
					"doctype": "BG Garage",
					"garage_id": "BG-" + frappe.generate_hash(length=16).upper(),
					"garage_name": values["garage_name"],
					"owner_name": values["owner_name"],
					"email": values["email"],
					"phone": values["phone"],
					"address": values["address"],
					"city": values["city"],
					"state": values["state"],
					"pin_code": values["pin_code"],
					"status": "Pending",
				}
			)
			garage.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			return {"message": REGISTRATION_ACKNOWLEDGEMENT}
		except Exception:
			frappe.log_error(title="Garage registration failed", message=frappe.get_traceback())
			frappe.throw(
				_("We could not submit this request. Please try again later."),
				frappe.ValidationError,
			)

	return {"message": REGISTRATION_ACKNOWLEDGEMENT}


def _registration_token_hash(token):
	return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_registration_token(garage):
	token = secrets.token_urlsafe(32)
	garage.application_token_hash = _registration_token_hash(token)
	garage.application_token_expires_on = add_to_date(now_datetime(), hours=REGISTRATION_TOKEN_HOURS)
	return token


def _queue_registration_email(garage, token):
	"""Queue an approval link without claiming SMTP delivery succeeded."""
	from frappe.email.doctype.email_account.email_account import EmailAccount

	if frappe.are_emails_muted():
		return "not_configured"
	try:
		account = EmailAccount.find_default_outgoing()
	except Exception:
		account = None
	if not account or getattr(account, "name", None) == "Notifications":
		return "not_configured"
	registration_url = frappe.utils.get_url(f"/register?token={token}")
	try:
		frappe.sendmail(
			recipients=[garage.email],
			subject=_("Your Bike Garage access request is approved"),
			message=_(
				"Your garage access request for {0} has been approved. Complete your owner registration within {1} hours: <a href=\"{2}\">Complete registration</a>."
			).format(escape_html(garage.garage_name), REGISTRATION_TOKEN_HOURS, registration_url),
			delayed=True,
		)
		return "queued_not_delivery_verified"
	except Exception:
		frappe.log_error(title="Garage registration email could not be queued", message=frappe.get_traceback())
		return "queue_failed"


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60, methods=["POST"], ip_based=True)
def complete_garage_registration(token=None, password=None, password_confirmation=None):
	"""Consume a single email-delivered approval token and create its owner."""
	if getattr(frappe.session, "user", None) != "Guest":
		frappe.throw(_("Complete this registration while signed out."), frappe.PermissionError)
	if not isinstance(token, str) or len(token) < 32 or len(token) > 200:
		frappe.throw(_("This registration link is invalid or expired."), frappe.ValidationError)
	if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
		frappe.throw(_("Choose a password with at least 8 characters."), frappe.ValidationError)
	if not isinstance(password_confirmation, str) or not hmac.compare_digest(password, password_confirmation):
		frappe.throw(_("The password confirmation does not match."), frappe.ValidationError)

	token_hash = _registration_token_hash(token)
	try:
		garage_name = frappe.db.get_value("BG Garage", {"application_token_hash": token_hash}, "name")
		if not garage_name:
			frappe.throw(_("This registration link is invalid or expired."), frappe.ValidationError)
		garage = frappe.get_doc("BG Garage", garage_name, for_update=True)
	except frappe.DoesNotExistError:
		frappe.throw(_("This registration link is invalid or expired."), frappe.ValidationError)
	if (
		garage.status != "Approved"
		or not garage.application_token_hash
		or not hmac.compare_digest(garage.application_token_hash, token_hash)
		or not garage.application_token_expires_on
		or garage.application_token_expires_on < now_datetime()
		or garage.registration_completed_on
	):
		frappe.throw(_("This registration link is invalid or expired."), frappe.ValidationError)
	user_name = frappe.db.get_value("User", garage.email, "name")
	pending_owners = frappe.get_all(
		"BG Garage Membership",
		filters={"garage": garage.name, "status": "Pending", "membership_type": "Owner"},
		fields=["name", "user"],
		limit_page_length=2,
	)
	if user_name:
		# Complete legacy pending requests created by older app versions only
		# when the disabled Website User and pending Owner membership match exactly.
		if len(pending_owners) != 1 or pending_owners[0].get("user") != user_name:
			frappe.throw(_("This registration cannot be completed. Contact Bike Garage support."), frappe.ValidationError)
		user = frappe.get_doc("User", user_name, for_update=True)
		if user.enabled or user.user_type != "Website User":
			frappe.throw(_("This registration cannot be completed. Contact Bike Garage support."), frappe.ValidationError)
		if garage.owner_user and garage.owner_user != user.name:
			frappe.throw(_("This registration cannot be completed. Contact Bike Garage support."), frappe.ValidationError)
		other_memberships = frappe.get_all(
			"BG Garage Membership", filters={"user": user.name}, fields=["name", "garage", "status"], limit_page_length=0
		)
		if any(row.garage != garage.name or row.status == "Active" for row in other_memberships):
			frappe.throw(_("This registration cannot be completed. Contact Bike Garage support."), frappe.ValidationError)
		membership = frappe.get_doc("BG Garage Membership", pending_owners[0]["name"], for_update=True)
		user.new_password = password
		user.enabled = 1
		user.save(ignore_permissions=True)
		membership.status = "Active"
		membership.save(ignore_permissions=True)
	else:
		if pending_owners or frappe.db.exists("BG Garage Membership", {"garage": garage.name}):
			frappe.throw(_("This registration cannot be completed. Contact Bike Garage support."), frappe.ValidationError)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": garage.email,
				"first_name": garage.owner_name,
				"user_type": "Website User",
				"enabled": 1,
				"send_welcome_email": 0,
				"new_password": password,
			}
		)
		user.insert(ignore_permissions=True)
		membership = frappe.get_doc(
			{
				"doctype": "BG Garage Membership",
				"user": user.name,
				"garage": garage.name,
				"status": "Active",
				"membership_type": "Owner",
			}
		)
		membership.insert(ignore_permissions=True)
	garage.owner_user = user.name
	garage.status = "Active"
	garage.application_token_hash = ""
	garage.application_token_expires_on = None
	garage.registration_completed_on = now_datetime()
	garage.save(ignore_permissions=True)
	return {"message": _("Registration is complete. You can now log in."), "login_url": "/login"}


def _require_platform_super_admin():
	user = getattr(frappe.session, "user", None)
	if not user or user == "Guest":
		frappe.throw(_("Platform Super Admin access is required."), frappe.PermissionError)
	if not tenancy.is_platform_super_admin(user):
		frappe.throw(_("Platform Super Admin access is required."), frappe.PermissionError)
	return user


def _get_garage_or_fail(garage_name, for_update=False):
	if not isinstance(garage_name, str) or not garage_name.strip():
		frappe.throw(_("A garage is required."), frappe.ValidationError)
	try:
		return frappe.get_doc("BG Garage", garage_name.strip(), for_update=for_update)
	except frappe.DoesNotExistError:
		frappe.throw(_("Garage application was not found."), frappe.DoesNotExistError)


@frappe.whitelist()
def get_platform_dashboard():
	"""Return real platform counts without loading unbounded administration tables."""
	_require_platform_super_admin()
	return {
		"counts": {
			"garages": frappe.db.count("BG Garage"),
			"pending_garages": frappe.db.count("BG Garage", {"status": "Pending"}),
			"approved_garages": frappe.db.count("BG Garage", {"status": "Approved"}),
			"active_garages": frappe.db.count("BG Garage", {"status": "Active"}),
			"suspended_garages": frappe.db.count("BG Garage", {"status": "Suspended"}),
			"rejected_garages": frappe.db.count("BG Garage", {"status": "Rejected"}),
			"closed_garages": frappe.db.count("BG Garage", {"status": "Closed"}),
			"memberships": frappe.db.count("BG Garage Membership"),
			"pending_memberships": frappe.db.count("BG Garage Membership", {"status": "Pending"}),
		},
		"active_garages": frappe.get_all("BG Garage", filters={"status": "Active"},
			fields=["name", "garage_id", "garage_name"], order_by="garage_name asc", limit_page_length=0),
	}


GARAGE_STATUSES = {"Pending", "Approved", "Active", "Suspended", "Rejected", "Closed"}
ADMIN_MEMBERSHIP_STATUSES = {"Pending", "Active", "Suspended"}
ADMIN_MEMBERSHIP_TYPES = {"Owner", "Manager", "Service Advisor", "Technician", "Inventory Manager", "Accountant"}


def _admin_page_args(query, status, allowed_statuses, start, page_length):
	query = " ".join(query.strip().split()) if isinstance(query, str) else ""
	if len(query) > 100:
		frappe.throw(_("Search text is too long."), frappe.ValidationError)
	if not isinstance(status, str) or (status != "All" and status not in allowed_statuses):
		frappe.throw(_("Unsupported filter."), frappe.ValidationError)
	try:
		start = int(start)
		page_length = int(page_length)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid page selection."), frappe.ValidationError)
	if start < 0 or page_length < 1:
		frappe.throw(_("Invalid page selection."), frappe.ValidationError)
	return query, status, start, min(page_length, 100)


@frappe.whitelist()
def get_platform_garages(query="", status="All", start=0, page_length=20):
	"""Search the authorized platform garage list with bounded pagination."""
	_require_platform_super_admin()
	query, status, start, page_length = _admin_page_args(query, status, GARAGE_STATUSES, start, page_length)
	filters = {"status": status} if status != "All" else {}
	or_filters = []
	if query:
		like = f"%{query}%"
		or_filters = [{field: ["like", like]} for field in ("garage_name", "garage_id", "owner_name", "owner_user", "email", "phone", "city")]
	fields = [
		"name", "garage_id", "garage_name", "status", "owner_name", "owner_user", "email", "phone",
		"address", "city", "state", "pin_code", "creation", "application_decision_by",
		"application_decision_on", "registration_completed_on", "registration_email_status",
	]
	rows = frappe.get_all("BG Garage", filters=filters, or_filters=or_filters, fields=fields,
		order_by="creation desc", start=start, page_length=page_length)
	if query:
		total = len(frappe.get_all("BG Garage", filters=filters, or_filters=or_filters,
			fields=["name"], limit_page_length=0))
	else:
		total = frappe.db.count("BG Garage", filters)
	return {"rows": rows, "total": total, "start": start, "page_length": page_length}


@frappe.whitelist()
def get_platform_memberships(query="", status="All", membership_type="All", start=0, page_length=20):
	"""Search and page membership rows without exposing system-user credentials."""
	_require_platform_super_admin()
	query, status, start, page_length = _admin_page_args(query, status, ADMIN_MEMBERSHIP_STATUSES, start, page_length)
	if not isinstance(membership_type, str) or (membership_type != "All" and membership_type not in ADMIN_MEMBERSHIP_TYPES):
		frappe.throw(_("Unsupported membership type."), frappe.ValidationError)
	filters = {}
	if status != "All":
		filters["status"] = status
	if membership_type != "All":
		filters["membership_type"] = membership_type
	or_filters = []
	if query:
		like = f"%{query}%"
		or_filters = [{field: ["like", like]} for field in ("user", "garage", "membership_type", "status")]
	rows = frappe.get_all("BG Garage Membership", filters=filters, or_filters=or_filters,
		fields=["name", "user", "garage", "status", "membership_type", "creation"],
		order_by="creation desc", start=start, page_length=page_length)
	if query:
		total = len(frappe.get_all("BG Garage Membership", filters=filters, or_filters=or_filters,
			fields=["name"], limit_page_length=0))
	else:
		total = frappe.db.count("BG Garage Membership", filters)
	return {"rows": rows, "total": total, "start": start, "page_length": page_length}


def _lock_user_then_membership(membership_name, expected_user):
	"""Serialize membership changes on the stable User row, then lock the membership.

	The user name is read from the membership before taking locks. After locking
	the User row, reload and lock the membership and verify that its user did not
	change while we were acquiring the serialization lock.
	"""
	try:
		user = frappe.get_doc("User", expected_user, for_update=True)
	except frappe.DoesNotExistError:
		frappe.throw(_("The membership user account was not found."), frappe.DoesNotExistError)
	try:
		membership = frappe.get_doc("BG Garage Membership", membership_name, for_update=True)
	except frappe.DoesNotExistError:
		frappe.throw(_("Garage membership was not found."), frappe.DoesNotExistError)
	if membership.user != user.name:
		frappe.throw(
			_("The membership user changed while it was being updated. Reload and try again."),
			frappe.ValidationError,
		)
	return user, membership


def _ensure_no_other_active_membership(user_name, membership_name):
	"""Check active memberships with a locking read after locking the User row."""
	other_active = frappe.db.get_value(
		"BG Garage Membership",
		{
			"user": user_name,
			"status": "Active",
			"name": ["!=", membership_name],
		},
		"name",
		for_update=True,
	)
	if other_active:
		frappe.throw(
			_("This user already has an active garage membership."),
			frappe.ValidationError,
		)


@frappe.whitelist(methods=["POST"])
def approve_garage_application(garage_name):
	approver = _require_platform_super_admin()
	garage = _get_garage_or_fail(garage_name, for_update=True)
	if garage.status != "Pending":
		frappe.throw(_("Only pending garage applications can be approved."), frappe.ValidationError)
	token = _new_registration_token(garage)
	garage.status = "Approved"
	garage.application_decision_by = approver
	garage.application_decision_on = now_datetime()
	garage.registration_email_status = _queue_registration_email(garage, token)
	garage.save(ignore_permissions=True)
	return {
		"status": garage.status,
		"registration_email_status": garage.registration_email_status,
	}


@frappe.whitelist(methods=["POST"])
def resend_garage_registration_link(garage_name):
	_require_platform_super_admin()
	garage = _get_garage_or_fail(garage_name, for_update=True)
	if garage.status != "Approved" or garage.registration_completed_on:
		frappe.throw(_("A registration link can be sent only for an approved, incomplete application."), frappe.ValidationError)
	token = _new_registration_token(garage)
	garage.registration_email_status = _queue_registration_email(garage, token)
	garage.save(ignore_permissions=True)
	return {"status": garage.status, "registration_email_status": garage.registration_email_status}


@frappe.whitelist(methods=["POST"])
def reject_garage_application(garage_name):
	decision_by = _require_platform_super_admin()
	garage = _get_garage_or_fail(garage_name, for_update=True)
	if garage.status != "Pending":
		frappe.throw(_("Only pending garage applications can be rejected."), frappe.ValidationError)
	garage.status = "Rejected"
	garage.application_decision_by = decision_by
	garage.application_decision_on = now_datetime()
	garage.application_token_hash = ""
	garage.application_token_expires_on = None
	garage.save(ignore_permissions=True)
	for row in frappe.get_all(
		"BG Garage Membership",
		filters={"garage": garage.name, "status": "Pending"},
		fields=["name", "user"],
		limit_page_length=0,
	):
		if not row.get("user"):
			continue
		_user, membership = _lock_user_then_membership(row["name"], row["user"])
		if membership.garage != garage.name or membership.status != "Pending":
			continue
		# A rejected application must not delete or disable an existing account or
		# membership. Preserve the record for audit and explicitly suspend only
		# its pending membership.
		membership.status = "Suspended"
		membership.save(ignore_permissions=True)
	return {"status": garage.status}


@frappe.whitelist(methods=["POST"])
def set_garage_status(garage_name, status):
	_require_platform_super_admin()
	if status not in ("Active", "Suspended"):
		frappe.throw(_("Garage status must be Active or Suspended."), frappe.ValidationError)
	garage = _get_garage_or_fail(garage_name, for_update=True)
	if garage.status not in ("Active", "Suspended"):
		frappe.throw(_("Only active garages can be suspended or reactivated."), frappe.ValidationError)
	garage.status = status
	garage.save(ignore_permissions=True)
	return {"status": garage.status}


@frappe.whitelist(methods=["POST"])
def update_garage_membership(membership_name, status=None, membership_type=None):
	_require_platform_super_admin()
	if status is not None and status not in MEMBERSHIP_STATUSES:
		frappe.throw(_("Unsupported membership status."), frappe.ValidationError)
	if membership_type is not None and membership_type not in MEMBERSHIP_TYPES:
		frappe.throw(_("Unsupported membership type."), frappe.ValidationError)
	if status is None and membership_type is None:
		frappe.throw(_("Choose a membership status or type to update."), frappe.ValidationError)
	if not isinstance(membership_name, str) or not membership_name.strip():
		frappe.throw(_("A membership is required."), frappe.ValidationError)
	try:
		membership_snapshot = frappe.get_doc("BG Garage Membership", membership_name.strip())
	except frappe.DoesNotExistError:
		frappe.throw(_("Garage membership was not found."), frappe.DoesNotExistError)
	# User is the per-account serialization lock. Lock it before the membership
	# so this path matches application approval and cannot invert their lock order.
	user, membership = _lock_user_then_membership(
		membership_snapshot.name, membership_snapshot.user
	)
	if status == "Active":
		if frappe.db.get_value("BG Garage", membership.garage, "status") != "Active":
			frappe.throw(_("Memberships can be activated only for an active garage."), frappe.ValidationError)
		_ensure_no_other_active_membership(user.name, membership.name)
	if status is not None:
		membership.status = status
	if membership_type is not None:
		membership.membership_type = membership_type
	membership.save(ignore_permissions=True)
	return {"name": membership.name, "status": membership.status, "membership_type": membership.membership_type}


@frappe.whitelist(methods=["POST"])
def add_garage_membership(user_email, garage_name, membership_type):
	"""Add an existing Frappe user as a Pending member of one active garage."""
	_require_platform_super_admin()
	if not isinstance(user_email, str):
		frappe.throw(_("A valid user email is required."), frappe.ValidationError)
	user_email = user_email.strip().lower()
	if not user_email or validate_email_address(user_email, throw=True).lower() != user_email:
		frappe.throw(_("A valid user email is required."), frappe.ValidationError)
	if membership_type not in MEMBERSHIP_TYPES:
		frappe.throw(_("Unsupported membership type."), frappe.ValidationError)
	garage = _get_garage_or_fail(garage_name, for_update=True)
	if garage.status != "Active":
		frappe.throw(_("Members can be added only to an active garage."), frappe.ValidationError)
	try:
		user = frappe.get_doc("User", user_email, for_update=True)
	except frappe.DoesNotExistError:
		frappe.throw(_("The user account was not found."), frappe.DoesNotExistError)
	if not user.enabled:
		frappe.throw(_("Enable the existing user account before assigning a membership."), frappe.ValidationError)
	if frappe.get_all(
		"BG Garage Membership",
		filters={"user": user.name},
		fields=["name"],
		limit_page_length=1,
	):
		frappe.throw(
			_("This user already has a garage membership. Review it before assigning another garage."),
			frappe.ValidationError,
		)
	membership = frappe.get_doc(
		{
			"doctype": "BG Garage Membership",
			"user": user.name,
			"garage": garage.name,
			"status": "Pending",
			"membership_type": membership_type,
		}
	)
	membership.insert(ignore_permissions=True)
	return {"name": membership.name, "status": membership.status}
