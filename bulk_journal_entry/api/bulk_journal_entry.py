import logging
import math

import frappe
from frappe.utils import flt, now_datetime


logger = logging.getLogger(__name__)

BATCH_SIZE = 10
BATCH_QUEUE = "long"
BATCH_TIMEOUT = 1200


@frappe.whitelist()
def get_sales_invoice_data(invoice_no):
	if not invoice_no:
		return None

	if not frappe.db.exists("Sales Invoice", invoice_no):
		frappe.throw(frappe._("Sales Invoice not found"))

	si = frappe.get_doc("Sales Invoice", invoice_no)
	return {
		"name": si.name,
		"company": si.company,
		"customer": si.customer,
		"posting_date": si.posting_date,
		"grand_total": si.grand_total,
		"outstanding_amount": si.outstanding_amount,
	}


def create_journal_entry_on_submit(doc, method=None):
	_prepare_rows_for_processing(doc)
	enqueue_journal_entry_batches(doc.name, notify_user=frappe.session.user)
	logger.info(
		"Bulk Journal Entry %s submitted by %s; dispatching batches of %s rows",
		doc.name,
		frappe.session.user,
		BATCH_SIZE,
	)
	frappe.msgprint(f"Bulk Journal Entry processing started in batches of {BATCH_SIZE} rows.")


def enqueue_journal_entry_batches(docname, row_names=None, notify_user=None):
	doc = frappe.get_doc("Bulk Journal Entry", docname)
	rows = _get_rows_for_batches(doc, row_names=row_names)

	if not rows:
		logger.info("Bulk Journal Entry %s has no rows to enqueue", docname)
		_update_summary_counts(docname)
		_finalize_journal_entry_if_ready(docname)
		return

	total_batches = math.ceil(len(rows) / BATCH_SIZE)
	logger.info(
		"Bulk Journal Entry %s dispatching %s rows into %s batches",
		docname,
		len(rows),
		total_batches,
	)

	for batch_no, start in enumerate(range(0, len(rows), BATCH_SIZE), start=1):
		batch_rows = rows[start : start + BATCH_SIZE]
		logger.info(
			"Bulk Journal Entry %s enqueue batch %s/%s rows %s-%s",
			docname,
			batch_no,
			total_batches,
			batch_rows[0].idx,
			batch_rows[-1].idx,
		)
		frappe.enqueue(
			"bulk_journal_entry.api.bulk_journal_entry.process_bulk_journal_entry_batch",
			docname=docname,
			row_names=[row.name for row in batch_rows],
			start_idx=batch_rows[0].idx,
			end_idx=batch_rows[-1].idx,
			batch_no=batch_no,
			total_batches=total_batches,
			notify_user=notify_user,
			queue=BATCH_QUEUE,
			timeout=BATCH_TIMEOUT,
			enqueue_after_commit=True,
		)

	_update_summary_counts(docname)


def process_bulk_journal_entry_batch(
	docname,
	row_names=None,
	start_idx=None,
	end_idx=None,
	batch_no=None,
	total_batches=None,
	notify_user=None,
):
	doc = frappe.get_doc("Bulk Journal Entry", docname)
	rows = _get_batch_rows(doc, row_names=row_names, start_idx=start_idx, end_idx=end_idx)

	logger.info(
		"Bulk Journal Entry %s batch %s/%s started with %s rows",
		docname,
		batch_no or "-",
		total_batches or "-",
		len(rows),
	)

	for row in rows:
		if row.status in {"Created", "Settled"}:
			logger.info(
				"Bulk Journal Entry %s row %s invoice %s already %s; skipping",
				docname,
				row.idx,
				row.sales_invoice,
				row.status,
			)
			continue

		logger.info(
			"Bulk Journal Entry %s row %s invoice %s processing started",
			docname,
			row.idx,
			row.sales_invoice,
		)
		_set_row_state(row, "Processing")
		frappe.db.commit()

		try:
			status = _validate_settlement_row(doc, row)
			_set_row_state(row, status)
			logger.info(
				"Bulk Journal Entry %s row %s invoice %s finished with status %s",
				docname,
				row.idx,
				row.sales_invoice,
				status,
			)
			frappe.db.commit()
		except Exception as exc:
			error_message = _format_error_message(exc)
			_set_row_state(row, "Failed", error_message=error_message)
			logger.exception(
				"Bulk Journal Entry %s row %s invoice %s failed",
				docname,
				row.idx,
				row.sales_invoice,
			)
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Bulk Journal Entry Error | Invoice: {row.sales_invoice} | Row: {row.idx}",
			)
			frappe.db.commit()

	_update_summary_counts(docname)
	_finalize_journal_entry_if_ready(docname)
	logger.info(
		"Bulk Journal Entry %s batch %s/%s completed",
		docname,
		batch_no or "-",
		total_batches or "-",
	)
	_publish_batch_progress(docname, batch_no, total_batches, notify_user=notify_user)


@frappe.whitelist()
def retry_failed_rows(docname):
	doc = frappe.get_doc("Bulk Journal Entry", docname)
	doc.check_permission("submit")

	if doc.generated_journal_entry:
		frappe.throw("Cannot retry failed rows after Journal Entry is generated. Please amend or create a new Bulk Journal Entry.")

	failed_rows = [row.name for row in doc.items if row.status == "Failed"]
	if not failed_rows:
		logger.info("Bulk Journal Entry %s retry requested but no failed rows found", docname)
		frappe.msgprint("No failed rows found to retry.")
		return

	for row_name in failed_rows:
		frappe.db.set_value(
			"Bulk Journal Entry Item",
			row_name,
			{"status": "Pending", "journal_entry": None, "error_message": None, "processed_at": None},
			update_modified=False,
		)

	enqueue_journal_entry_batches(docname, row_names=failed_rows, notify_user=frappe.session.user)
	logger.info("Bulk Journal Entry %s retry started for %s failed rows", docname, len(failed_rows))
	frappe.msgprint(f"Retry started for {len(failed_rows)} failed rows.")


def _prepare_rows_for_processing(doc):
	for row in doc.items:
		logger.info("Bulk Journal Entry %s preparing row %s invoice %s", doc.name, row.idx, row.sales_invoice)
		frappe.db.set_value(
			"Bulk Journal Entry Item",
			row.name,
			{
				"status": "Pending",
				"journal_entry": None,
				"error_message": None,
				"processed_at": None,
			},
			update_modified=False,
		)

	_update_summary_counts(doc.name)


def _get_rows_for_batches(doc, row_names=None):
	if row_names:
		row_names = set(row_names)
		rows = [row for row in doc.items if row.name in row_names]
	else:
		rows = [row for row in doc.items if row.status not in {"Created", "Settled"}]

	return sorted(rows, key=lambda row: row.idx)


def _get_batch_rows(doc, row_names=None, start_idx=None, end_idx=None):
	if row_names:
		row_names = set(row_names)
		return [row for row in doc.items if row.name in row_names]

	return [
		row
		for row in doc.items
		if (start_idx is None or row.idx >= int(start_idx))
		and (end_idx is None or row.idx <= int(end_idx))
	]


def _validate_settlement_row(doc, row):
	if not row.sales_invoice:
		frappe.throw("Sales Invoice is required.")

	si = frappe.get_doc("Sales Invoice", row.sales_invoice)
	if si.docstatus != 1:
		frappe.throw(f"Sales Invoice {si.name} is not submitted.")

	if si.company != doc.company:
		frappe.throw(f"Sales Invoice {si.name} belongs to {si.company}, but Bulk Journal Entry company is {doc.company}.")

	if si.customer != row.customer:
		frappe.throw(f"Sales Invoice {si.name} customer does not match row customer {row.customer}.")

	if si.debit_to != doc.receivable_account:
		frappe.throw(f"Sales Invoice {si.name} receivable account is {si.debit_to}, not {doc.receivable_account}.")

	duplicates = frappe.db.get_all(
		"Bulk Journal Entry Item",
		filters={
			"parent": doc.name,
			"parenttype": "Bulk Journal Entry",
			"sales_invoice": row.sales_invoice,
			"name": ["!=", row.name],
		},
		pluck="name",
	)
	if duplicates:
		frappe.throw(f"Sales Invoice {si.name} is added more than once.")

	if flt(row.amount) <= 0:
		frappe.throw("Settle Amount must be greater than zero.")

	if flt(row.amount, row.precision("amount")) > flt(si.outstanding_amount, row.precision("amount")):
		frappe.throw(f"Settle Amount cannot be greater than outstanding amount for {si.name}.")

	return "Created"


def _finalize_journal_entry_if_ready(docname):
	doc = frappe.get_doc("Bulk Journal Entry", docname)
	if doc.generated_journal_entry:
		logger.info("Bulk Journal Entry %s already has Journal Entry %s", docname, doc.generated_journal_entry)
		return

	rows = frappe.db.get_all(
		"Bulk Journal Entry Item",
		filters={"parent": docname, "parenttype": "Bulk Journal Entry"},
		fields=["name", "status"],
	)

	if any(row.status in {"Pending", "Processing"} for row in rows):
		logger.info("Bulk Journal Entry %s finalization waiting for pending/processing rows", docname)
		return

	if any(row.status == "Failed" for row in rows):
		logger.info("Bulk Journal Entry %s finalization waiting; failed rows need retry", docname)
		_update_summary_counts(docname)
		return

	created_rows = [row.name for row in rows if row.status == "Created"]
	if not created_rows:
		logger.info("Bulk Journal Entry %s finalization skipped; no created rows", docname)
		_update_summary_counts(docname)
		return

	logger.info("Bulk Journal Entry %s creating Journal Entry from %s successful rows", docname, len(created_rows))
	je = doc.create_journal_entry(row_names=created_rows)
	frappe.db.set_value("Bulk Journal Entry", docname, "generated_journal_entry", je.name, update_modified=False)

	for row_name in created_rows:
		frappe.db.set_value(
			"Bulk Journal Entry Item",
			row_name,
			{"status": "Settled", "journal_entry": je.name, "error_message": None, "processed_at": now_datetime()},
			update_modified=False,
		)

	frappe.db.commit()
	logger.info("Bulk Journal Entry %s generated Journal Entry %s", docname, je.name)
	_update_summary_counts(docname)


def _set_row_state(row, status, journal_entry=None, error_message=None):
	values = {"status": status, "processed_at": now_datetime()}

	if journal_entry is not None:
		values["journal_entry"] = journal_entry

	if error_message is not None:
		values["error_message"] = error_message[:1000]
	elif status in {"Processing", "Created", "Settled", "Skipped"}:
		values["error_message"] = None

	frappe.db.set_value("Bulk Journal Entry Item", row.name, values, update_modified=False)


def _format_error_message(exc):
	summary = f"{type(exc).__name__}: {exc}"
	traceback = frappe.get_traceback()
	if summary in traceback:
		return traceback[-1000:]

	return f"{summary}\n\n{traceback}"[:1000]


def _update_summary_counts(docname):
	rows = frappe.db.get_all(
		"Bulk Journal Entry Item",
		filters={"parent": docname, "parenttype": "Bulk Journal Entry"},
		fields=["status", "amount"],
	)
	total = len(rows)
	settled = len([row for row in rows if row.status == "Settled"])
	failed = len([row for row in rows if row.status == "Failed"])
	skipped = len([row for row in rows if row.status == "Skipped"])
	pending = total - settled - failed - skipped
	total_amount = sum(flt(row.amount) for row in rows)

	frappe.db.set_value(
		"Bulk Journal Entry",
		docname,
		{
			"total_rows": total,
			"total_amount": total_amount,
			"settled_count": settled,
			"failed_count": failed,
			"skipped_count": skipped,
			"pending_count": pending,
		},
		update_modified=False,
	)
	logger.info(
		"Bulk Journal Entry %s summary total=%s settled=%s failed=%s skipped=%s pending=%s",
		docname,
		total,
		settled,
		failed,
		skipped,
		pending,
	)


def _publish_batch_progress(docname, batch_no=None, total_batches=None, notify_user=None):
	batch_label = ""
	if batch_no and total_batches:
		batch_label = f" Batch {batch_no} of {total_batches} completed."

	if notify_user:
		frappe.publish_realtime(
			"msgprint",
			{"message": f"Bulk Journal Entry {docname}:{batch_label} Progress updated."},
			user=notify_user,
		)
