import frappe


@frappe.whitelist()
def get_settlement_journal_entries(payment_entry):
	if not payment_entry:
		return {"rows": [], "total_settled": 0}

	if not frappe.has_permission("Payment Entry", "read", payment_entry):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	je_account = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")

	rows = (
		frappe.qb.from_(je_account)
		.inner_join(je)
		.on(je.name == je_account.parent)
		.select(
			je.name.as_("journal_entry"),
			je.posting_date,
			je.voucher_type,
			je.company,
			je_account.party_type,
			je_account.party,
			je_account.reference_type,
			je_account.reference_name,
			je_account.debit_in_account_currency,
			je_account.credit_in_account_currency,
			je_account.account_currency,
		)
		.where(je.docstatus == 1)
		.where(je_account.docstatus == 1)
		.where(je_account.advance_voucher_type == "Payment Entry")
		.where(je_account.advance_voucher_no == payment_entry)
		.orderby(je.posting_date, je.name)
	).run(as_dict=True)

	total_settled = 0
	for row in rows:
		row.settled_amount = abs(row.debit_in_account_currency or row.credit_in_account_currency or 0)
		total_settled += row.settled_amount

	return {
		"rows": rows,
		"total_settled": total_settled,
	}
