from frappe import _


def get_dashboard_data(data=None):
	if data is None:
		data = {}

	data.setdefault("transactions", [])
	data.setdefault("internal_links", {})
	data.setdefault("non_standard_fieldnames", {})

	transactions = data["transactions"]
	accounting_group = next((group for group in transactions if group.get("label") == _("Accounting")), None)
	if not accounting_group:
		accounting_group = {"label": _("Accounting"), "items": []}
		transactions.append(accounting_group)

	if "Journal Entry" not in accounting_group["items"]:
		accounting_group["items"].append("Journal Entry")

	data["non_standard_fieldnames"]["Journal Entry"] = "patient"

	return data
