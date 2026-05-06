app_name = "bulk_journal_entry"
app_title = "Bulk Journal Entry"
app_publisher = "SRIAAS"
app_description = "Bulk settlement Journal Entries for collection payments in ERPNext"
app_email = "webdevelopersriaas@gmail.com"
app_license = "mit"

before_install = "bulk_journal_entry.install.before_install"
after_install = "bulk_journal_entry.install.after_install"
after_migrate = "bulk_journal_entry.install.after_migrate"

doctype_js = {
	"Bulk Journal Entry": "public/js/bulk_journal_entry.js",
	"Payment Entry": "public/js/payment_entry.js",
}

override_doctype_dashboards = {
	"Patient": ["bulk_journal_entry.patient_dashboard.get_dashboard_data"],
}

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "Bulk Journal Entry"]]},
	{"dt": "Property Setter", "filters": [["doc_type", "in", ["Bulk Journal Entry", "Bulk Journal Entry Item"]]]},
	{"dt": "Client Script", "filters": [["module", "=", "Bulk Journal Entry"]]},
	{"dt": "Server Script", "filters": [["module", "=", "Bulk Journal Entry"]]},
	{"dt": "Workspace", "filters": [["module", "=", "Bulk Journal Entry"]]},
	{"dt": "Report", "filters": [["module", "=", "Bulk Journal Entry"]]},
]
