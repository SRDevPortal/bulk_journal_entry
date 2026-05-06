frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.is_new()) {
			return;
		}

		frm.add_custom_button(
			__("Settlement Journal Entries"),
			() => show_settlement_journal_entries(frm),
			__("View")
		);
	},
});

function show_settlement_journal_entries(frm) {
	frappe.call({
		method: "bulk_journal_entry.api.payment_entry.get_settlement_journal_entries",
		args: {
			payment_entry: frm.doc.name,
		},
		callback(r) {
			const data = r.message || {};
			const rows = data.rows || [];

			if (!rows.length) {
				frappe.msgprint({
					title: __("Settlement Journal Entries"),
					message: __("No submitted Journal Entry rows are linked to this Payment Entry."),
					indicator: "orange",
				});
				return;
			}

			const currency =
				rows[0].account_currency || frm.doc.paid_from_account_currency || frm.doc.paid_to_account_currency;
			const table_rows = rows.map((row) => [
				frappe.utils.get_form_link("Journal Entry", row.journal_entry, true),
				frappe.datetime.str_to_user(row.posting_date),
				row.party || "",
				row.reference_name
					? frappe.utils.get_form_link(row.reference_type, row.reference_name, true)
					: "",
				format_currency(row.settled_amount, row.account_currency || currency),
			]);

			frappe.msgprint({
				title: __("Settlement Journal Entries"),
				message: [
					`<p><b>${__("Total Settled")}:</b> ${format_currency(data.total_settled, currency)}</p>`,
					frappe.render_template("table", {
						data: {
							header: [
								__("Journal Entry"),
								__("Posting Date"),
								__("Party"),
								__("Against Voucher"),
								__("Settled Amount"),
							],
							rows: table_rows,
						},
					}),
				].join(""),
				wide: true,
			});
		},
	});
}
