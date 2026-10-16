import csv
from pathlib import Path

import frappe
from frappe.sessions import get_csrf_token

from bike_garage import payments, tenancy


def _get_dashboard_translation_maps():
    translations_dir = Path(__file__).resolve().parents[1] / "translations"
    maps = {}
    for language in ("hi", "mr"):
        with (translations_dir / f"{language}.csv").open(encoding="utf-8-sig", newline="") as file:
            maps[language] = {row[0]: row[1] for row in csv.reader(file) if len(row) >= 2 and row[0]}
    return maps


def get_context(context):
    context.no_cache = 1
    if frappe.session.user == "Guest":
        frappe.throw("Please login to access this page", frappe.PermissionError)
    context.user = frappe.session.user
    context.user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
    context.translation_maps_json = frappe.as_json(_get_dashboard_translation_maps()).replace("</", "<\\/")
    context.csrf_token = get_csrf_token()
    context.language = frappe.local.lang or "en"
    context.today = frappe.utils.today()

    garage_id = tenancy.get_current_garage()
    context.can_view_financials = payments.can_read_payment_data(garage_id)
    garage_doc = frappe.get_doc("BG Garage", garage_id)
    if garage_doc.status != "Active":
        frappe.throw("The assigned garage is not active.", frappe.PermissionError)

    name = garage_doc.garage_name
    owner = garage_doc.owner_name or ""
    phone = garage_doc.phone or ""
    addr = ", ".join(
        part for part in (garage_doc.address, garage_doc.city, garage_doc.state) if part
    )
    if garage_doc.pin_code:
        addr = (addr + " – " + str(garage_doc.pin_code)) if addr else str(garage_doc.pin_code)

    garage = {
        "name": name,
        "tagline": "Bike Service & Spare Parts",
        "owner": owner,
        "phone": phone,
        "addr": addr,
        "gstin": garage_doc.gstin or "",
        "footer": garage_doc.invoice_footer_note or "",
    }
    context.garage = garage
    # A closing script tag inside a user-entered garage name must not escape the
    # JSON script context in the template.
    context.garage_json = frappe.as_json(garage).replace("</", "<\\/")

    words = name.split()
    context.initials = ("".join(w[0] for w in words[:2]).upper()) or "BG"
