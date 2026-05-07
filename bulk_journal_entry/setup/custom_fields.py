from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from .utils import has_doctype


def setup_custom_fields():
	create_custom_fields(get_custom_fields(), update=True)


def get_custom_fields():
	if not has_doctype("Patient"):
		return {}

	return {
		"Journal Entry": [
			{
				"fieldname": "patient",
				"label": "Patient",
				"fieldtype": "Link",
				"options": "Patient",
				"insert_after": "company",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"module": "Bulk Journal Entry",
			},
		],
		"Journal Entry Account": [
			{
				"fieldname": "patient",
				"label": "Patient",
				"fieldtype": "Link",
				"options": "Patient",
				"insert_after": "party",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"module": "Bulk Journal Entry",
			},
		],
	}
