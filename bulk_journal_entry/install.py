import logging

import frappe

from .setup.utils import APP_PY_MODULE, MODULE_DEF_NAME, ensure_module_def
from .setup.custom_fields import setup_custom_fields

logger = logging.getLogger(__name__)


def _ensure_module():
	ensure_module_def(MODULE_DEF_NAME, APP_PY_MODULE)


def before_install():
	logger.info("===== Bulk Journal Entry: Before Install =====")
	frappe.clear_cache()


def after_install():
	logger.info("===== Bulk Journal Entry: After Install Started =====")
	_ensure_module()
	setup_custom_fields()
	frappe.clear_cache()
	frappe.db.commit()
	logger.info("===== Bulk Journal Entry: After Install Completed =====")


def after_migrate():
	logger.info("===== Bulk Journal Entry: After Migrate Started =====")
	_ensure_module()
	setup_custom_fields()
	frappe.clear_cache()
	frappe.db.commit()
	logger.info("===== Bulk Journal Entry: After Migrate Completed =====")
