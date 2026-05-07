import logging

import frappe

logger = logging.getLogger(__name__)

MODULE_DEF_NAME = "Bulk Journal Entry"
APP_PY_MODULE = "bulk_journal_entry"


def ensure_module_def(module_name: str, app_name: str):
	if not frappe.db.exists("Module Def", module_name):
		logger.info(f"Creating Module Def: {module_name}")
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": module_name,
				"app_name": app_name,
			}
		).insert(ignore_permissions=True)


def has_doctype(doctype_name: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype_name))
