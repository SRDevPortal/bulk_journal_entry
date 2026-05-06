import frappe
from frappe.model.document import Document
from frappe.utils import flt


class BulkJournalEntry(Document):
	def validate(self):
		self.set_missing_item_values()
		self.validate_accounts()
		self.validate_payment_entry()
		self.validate_items()
		self.set_totals()

	def on_submit(self):
		if self.generated_journal_entry:
			frappe.throw(frappe._("Journal Entry is already created."))

		from bulk_journal_entry.api.bulk_journal_entry import create_journal_entry_on_submit

		create_journal_entry_on_submit(self)

	def on_cancel(self):
		if not self.generated_journal_entry:
			return

		je = frappe.get_doc("Journal Entry", self.generated_journal_entry)
		if je.docstatus == 1:
			je.cancel()

	def set_missing_item_values(self):
		for row in self.items:
			if not row.sales_invoice:
				continue

			si = frappe.get_cached_doc("Sales Invoice", row.sales_invoice)
			row.customer = si.customer
			row.posting_date = si.posting_date
			row.grand_total = si.grand_total
			row.outstanding_amount = si.outstanding_amount
			if not row.amount:
				row.amount = si.outstanding_amount

	def validate_accounts(self):
		for fieldname in ("collection_account", "receivable_account"):
			account = self.get(fieldname)
			if not account:
				continue

			account_doc = frappe.get_cached_doc("Account", account)
			if account_doc.company != self.company:
				frappe.throw(
					frappe._("{0} belongs to {1}, but Bulk Journal Entry company is {2}.").format(
						frappe.bold(account), frappe.bold(account_doc.company), frappe.bold(self.company)
					)
				)

			if account_doc.is_group:
				frappe.throw(frappe._("{0} must be a ledger account, not a group account.").format(frappe.bold(account)))

	def validate_payment_entry(self):
		if not self.payment_entry:
			return

		payment_entry = frappe.get_doc("Payment Entry", self.payment_entry)
		if payment_entry.docstatus != 1:
			frappe.throw(frappe._("Payment Entry {0} must be submitted.").format(frappe.bold(self.payment_entry)))

		if payment_entry.company != self.company:
			frappe.throw(
				frappe._("Payment Entry {0} belongs to {1}, but Bulk Journal Entry company is {2}.").format(
					frappe.bold(self.payment_entry), frappe.bold(payment_entry.company), frappe.bold(self.company)
				)
			)

	def validate_items(self):
		if not self.items:
			frappe.throw(frappe._("Add at least one settlement row."))

		for row in self.items:
			if not row.sales_invoice:
				frappe.throw(frappe._("Row {0}: Sales Invoice is required.").format(row.idx))

			if flt(row.amount) <= 0:
				frappe.throw(frappe._("Row {0}: Settle Amount must be greater than zero.").format(row.idx))

	def set_totals(self):
		self.total_rows = len(self.items or [])
		self.total_amount = sum(flt(row.amount) for row in self.items)

	def create_journal_entry(self, row_names=None, status=None):
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.company
		je.posting_date = self.posting_date
		je.user_remark = f"Created from Bulk Journal Entry {self.name}"

		if self.payment_entry:
			reference_no, reference_date = frappe.db.get_value(
				"Payment Entry", self.payment_entry, ["reference_no", "reference_date"]
			)
			je.cheque_no = reference_no
			je.cheque_date = reference_date

		settlement_items = self.get_settlement_items(row_names=row_names, status=status)
		total_amount = sum(flt(row["amount"]) for row in settlement_items)
		if not settlement_items:
			frappe.throw(frappe._("No settlement rows found to create Journal Entry."))

		je.append(
			"accounts",
			self.get_journal_account_row(
				account=self.collection_account,
				debit_in_account_currency=total_amount,
				user_remark=f"Collection settlement from {self.name}",
			),
		)

		for row in settlement_items:
			account_row = self.get_journal_account_row(
				account=self.receivable_account,
				party_type="Customer",
				party=row["customer"],
				credit_in_account_currency=row["amount"],
				is_advance="No",
				reference_type="Sales Invoice",
				reference_name=row["sales_invoice"],
				user_remark=row.get("remarks") or f"Settlement from {self.name}",
			)

			if self.payment_entry:
				account_row.update(
					{
						"advance_voucher_type": "Payment Entry",
						"advance_voucher_no": self.payment_entry,
					}
				)

			je.append("accounts", account_row)

		je.set_amounts_in_company_currency()
		je.set_total_debit_credit()
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		return je

	def get_journal_account_row(self, **values):
		row = {
			"party_type": None,
			"party": None,
			"reference_type": None,
			"reference_name": None,
			"reference_detail_no": None,
			"cost_center": None,
			"project": None,
			"is_advance": "No",
			"advance_voucher_type": None,
			"advance_voucher_no": None,
		}
		row.update(values)
		return row

	def get_settlement_items(self, row_names=None, status=None):
		filters = {"parent": self.name, "parenttype": self.doctype, "parentfield": "items"}
		if row_names:
			filters["name"] = ["in", row_names]
		if status:
			filters["status"] = status

		return frappe.db.get_all(
			"Bulk Journal Entry Item",
			filters=filters,
			fields=["name", "idx", "sales_invoice", "customer", "amount", "remarks"],
			order_by="idx",
		)
