app_name = "bike_garage"
app_title = "Bike Garage"
app_publisher = "nandkishor48"
app_description = "Bike Garage and Spare Parts Management System"
app_email = "utkrishiagriflow@gmail.com"
app_license = "mit"
app_logo_url = "/assets/bike_garage/images/bike-garage-logo-transparent.png"


# Create the platform role definition during a future migration. This never
# assigns the role to a user; assignment remains an explicit administrator task.
after_migrate = "bike_garage.install.after_migrate"
after_install = "bike_garage.install.after_install"
get_website_user_home_page = "bike_garage.website.get_home_page"
website_path_resolver = "bike_garage.website.resolve_website_path"
app_include_css = ["/assets/bike_garage/css/garage_ui.css"]
web_include_css = "/assets/bike_garage/css/garage_ui.css?v=20261018-1900"
web_include_js = ["/assets/bike_garage/js/garage_login.js?v=20261018-1900"]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "bike_garage",
# 		"logo": "/assets/bike_garage/logo.png",
# 		"title": "Bike Garage",
# 		"route": "/bike_garage",
# 		"has_permission": "bike_garage.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/bike_garage/css/bike_garage.css"
# app_include_js = "/assets/bike_garage/js/bike_garage.js"

# include js, css files in header of web template
# web_include_css = "/assets/bike_garage/css/bike_garage.css"
# web_include_js = "/assets/bike_garage/js/bike_garage.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "bike_garage/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "bike_garage/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "bike_garage.utils.jinja_methods",
# 	"filters": "bike_garage.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "bike_garage.install.before_install"
# after_install = "bike_garage.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "bike_garage.uninstall.before_uninstall"
# after_uninstall = "bike_garage.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "bike_garage.utils.before_app_install"
# after_app_install = "bike_garage.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "bike_garage.utils.before_app_uninstall"
# after_app_uninstall = "bike_garage.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "bike_garage.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "bike_garage.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"BG Customer": "bike_garage.permissions.get_permission_query_conditions",
	"BG Bike": "bike_garage.permissions.get_permission_query_conditions",
	"BG Job Card": "bike_garage.permissions.get_permission_query_conditions",
	"BG Spare Part": "bike_garage.permissions.get_permission_query_conditions",
	"BG Sale": "bike_garage.permissions.get_permission_query_conditions",
	"BG Sale Payment": "bike_garage.permissions.get_permission_query_conditions",
	"BG Expense": "bike_garage.permissions.get_permission_query_conditions",
	"BG Stock Movement": "bike_garage.permissions.get_permission_query_conditions",
}

has_permission = {
	"BG Customer": "bike_garage.permissions.has_permission",
	"BG Bike": "bike_garage.permissions.has_permission",
	"BG Job Card": "bike_garage.permissions.has_permission",
	"BG Spare Part": "bike_garage.permissions.has_permission",
	"BG Sale": "bike_garage.permissions.has_permission",
	"BG Sale Payment": "bike_garage.permissions.has_permission",
	"BG Expense": "bike_garage.permissions.has_permission",
	"BG Stock Movement": "bike_garage.permissions.has_permission",
}

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
	"BG Customer": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": [
			"bike_garage.permissions.validate_garage_ownership",
			"bike_garage.erpnext_integration.validate_mapping_reference",
		],
	},
	"BG Bike": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": "bike_garage.permissions.validate_garage_ownership",
	},
	"BG Job Card": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": [
			"bike_garage.permissions.validate_garage_ownership",
			"bike_garage.erpnext_integration.validate_mapping_reference",
		],
		"on_update": "bike_garage.stock.update_stock_from_job_card",
		"on_trash": "bike_garage.stock.restore_stock_from_job_card",
	},
	"BG Spare Part": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": [
			"bike_garage.permissions.validate_garage_ownership",
			"bike_garage.erpnext_integration.validate_mapping_reference",
		],
	},
	"BG Sale": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": [
			"bike_garage.permissions.validate_garage_ownership",
			"bike_garage.erpnext_integration.validate_mapping_reference",
		],
		"on_update": "bike_garage.stock.update_stock_from_sale",
		"on_trash": [
			"bike_garage.payments.prevent_sale_with_payments_from_deletion",
			"bike_garage.stock.restore_stock_from_sale",
		],
	},
	"BG Sale Payment": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": "bike_garage.permissions.validate_garage_ownership",
	},
	"BG Expense": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": "bike_garage.permissions.validate_garage_ownership",
	},
	"BG Stock Movement": {
		"before_insert": "bike_garage.permissions.assign_garage_on_insert",
		"validate": "bike_garage.permissions.validate_garage_ownership",
		"on_submit": "bike_garage.stock.apply_stock_movement",
		"on_cancel": "bike_garage.stock.reverse_stock_movement",
	},
	"BG Garage": {
		"validate": "bike_garage.erpnext_integration.validate_mapping_reference",
	},
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"bike_garage.tasks.all"
# 	],
# 	"daily": [
# 		"bike_garage.tasks.daily"
# 	],
# 	"hourly": [
# 		"bike_garage.tasks.hourly"
# 	],
# 	"weekly": [
# 		"bike_garage.tasks.weekly"
# 	],
# 	"monthly": [
# 		"bike_garage.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "bike_garage.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "bike_garage.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "bike_garage.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "bike_garage.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["bike_garage.utils.before_request"]
# after_request = ["bike_garage.utils.after_request"]

# Job Events
# ----------
# before_job = ["bike_garage.utils.before_job"]
# after_job = ["bike_garage.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"bike_garage.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
