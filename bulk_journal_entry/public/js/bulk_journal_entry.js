frappe.ui.form.on("Bulk Journal Entry", {
	onload(frm) {
		if (!frm.doc.company) {
			frappe.db.get_single_value("Global Defaults", "default_company").then((company) => {
				if (company) {
					frm.set_value("company", company);
				}
			});
		}
	},

	setup(frm) {
		frm.set_query("collection_account", () => account_query(frm));
		frm.set_query("receivable_account", () => account_query(frm, "Receivable"));
		frm.set_query("payment_entry", () => ({
			filters: {
				company: frm.doc.company,
				docstatus: 1,
			},
		}));
		frm.set_query("sales_invoice", "items", () => ({
			filters: {
				company: frm.doc.company,
				docstatus: 1,
				outstanding_amount: [">", 0],
			},
		}));
	},

	refresh(frm) {
		if (frm.doc.generated_journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.generated_journal_entry);
			}, __("View"));
		}

		if (frm.doc.docstatus === 1 && frm.doc.failed_count > 0 && !frm.doc.generated_journal_entry) {
			frm.add_custom_button(__("Retry Failed Rows"), () => {
				frappe.call({
					method: "bulk_journal_entry.api.bulk_journal_entry.retry_failed_rows",
					args: {
						docname: frm.doc.name,
					},
					callback() {
						frm.reload_doc();
					},
				});
			});
		}
	},

	scan_sales_invoice(frm) {
		const invoice = frm.doc.scan_sales_invoice;
		if (!invoice) return;

		if ((frm.doc.items || []).some((row) => row.sales_invoice === invoice)) {
			frappe.msgprint(__("Sales Invoice already added."));
			frm.set_value("scan_sales_invoice", "");
			return;
		}

		add_invoice_row(frm, invoice, true);
	},

	items_add(frm) {
		update_totals(frm);
	},

	items_remove(frm) {
		update_totals(frm);
	},
});

frappe.ui.form.on("Bulk Journal Entry Item", {
	sales_invoice(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.sales_invoice) return;

		add_invoice_row(frm, row.sales_invoice, false, cdt, cdn);
	},

	amount(frm) {
		update_totals(frm);
	},
});

function account_query(frm, account_type) {
	const filters = {
		company: frm.doc.company,
		is_group: 0,
	};

	if (account_type) {
		filters.account_type = account_type;
	}

	return { filters };
}

function add_invoice_row(frm, invoice, from_scan, cdt, cdn) {
	frappe.call({
		method: "bulk_journal_entry.api.bulk_journal_entry.get_sales_invoice_data",
		args: {
			invoice_no: invoice,
		},
		callback(r) {
			if (!r.message) return;

			if (frm.doc.company && r.message.company !== frm.doc.company) {
				frappe.msgprint(__("Sales Invoice belongs to another company."));
				frm.set_value("scan_sales_invoice", "");
				return;
			}

			let row;
			if (from_scan) {
				row = frm.add_child("items");
				row.sales_invoice = invoice;
				row.status = "Pending";
			} else {
				row = locals[cdt][cdn];
			}

			frappe.model.set_value(row.doctype, row.name, "customer", r.message.customer);
			frappe.model.set_value(row.doctype, row.name, "posting_date", r.message.posting_date);
			frappe.model.set_value(row.doctype, row.name, "grand_total", r.message.grand_total);
			frappe.model.set_value(row.doctype, row.name, "outstanding_amount", r.message.outstanding_amount);

			if (!row.amount) {
				frappe.model.set_value(row.doctype, row.name, "amount", r.message.outstanding_amount);
			}

			if (!frm.doc.posting_date && r.message.posting_date) {
				frm.set_value("posting_date", r.message.posting_date);
			}

			frm.refresh_field("items");
			update_totals(frm);

			if (from_scan) {
				frm.set_value("scan_sales_invoice", "");
				frm.fields_dict.scan_sales_invoice.$input.focus();
			}
		},
	});
}

function update_totals(frm) {
	const rows = frm.doc.items || [];
	const total = rows.reduce((sum, row) => sum + flt(row.amount), 0);

	frm.set_value("total_rows", rows.length);
	frm.set_value("total_amount", total);
}
