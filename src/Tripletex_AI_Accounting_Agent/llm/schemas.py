from enum import Enum
from pydantic import BaseModel
from typing import Any


class TaskType(str, Enum):
    # Tier 1
    CREATE_EMPLOYEE = "create_employee"
    UPDATE_EMPLOYEE = "update_employee"
    CREATE_CUSTOMER = "create_customer"
    UPDATE_CUSTOMER = "update_customer"
    CREATE_PRODUCT = "create_product"
    UPDATE_PRODUCT = "update_product"
    CREATE_DEPARTMENT = "create_department"
    UPDATE_DEPARTMENT = "update_department"
    CREATE_INVOICE = "create_invoice"
    CREATE_PROJECT = "create_project"
    UPDATE_PROJECT = "update_project"
    CREATE_ORDER = "create_order"
    # Tier 2
    REGISTER_PAYMENT = "register_payment"
    CREATE_CREDIT_NOTE = "create_credit_note"
    PROJECT_INVOICE = "project_invoice"
    CREATE_TRAVEL_EXPENSE = "create_travel_expense"
    UPDATE_TRAVEL_EXPENSE = "update_travel_expense"
    DELETE_TRAVEL_EXPENSE = "delete_travel_expense"
    REVERSE_PAYMENT = "reverse_payment"
    REGISTER_TIMESHEET = "register_timesheet"
    RUN_PAYROLL = "run_payroll"
    CREATE_SUPPLIER_INVOICE = "create_supplier_invoice"
    CREATE_CONTACT = "create_contact"
    # Tier 3
    DELETE_VOUCHER = "delete_voucher"
    CREATE_VOUCHER = "create_voucher"
    OVERDUE_INVOICE = "overdue_invoice"
    LEDGER_CORRECTION = "ledger_correction"
    CURRENCY_PAYMENT = "currency_payment"
    YEAR_END_CLOSING = "year_end_closing"
    CREATE_ACCOUNTING_DIMENSION = "create_accounting_dimension"
    BANK_RECONCILIATION = "bank_reconciliation"
    ENABLE_MODULE = "enable_module"
    FULL_PROJECT_CYCLE = "full_project_cycle"
    COST_ANALYSIS = "cost_analysis"
    UNKNOWN = "unknown"


class TaskPlan(BaseModel):
    task_type: TaskType
    entities: dict[str, Any]
