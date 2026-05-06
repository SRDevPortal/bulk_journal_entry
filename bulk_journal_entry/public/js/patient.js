frappe.ui.form.on("Patient", {
	refresh(frm) {
		if (!frm.doc.customer) return;

		frm.add_custom_button(
			__("Journal Entries"),
			() => {
				frappe.set_route("List", "Journal Entry", {
					"accounts.party_type": "Customer",
					"accounts.party": frm.doc.customer,
				});
			},
			__("Accounting")
		);
	},
});
