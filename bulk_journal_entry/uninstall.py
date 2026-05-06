import frappe


def before_uninstall():
	frappe.clear_cache()
