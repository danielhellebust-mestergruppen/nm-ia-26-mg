from llm.schemas import TaskType
from handlers.employee import CreateEmployeeHandler, UpdateEmployeeHandler
from handlers.customer import CreateCustomerHandler, UpdateCustomerHandler
from handlers.product import CreateProductHandler
from handlers.department import CreateDepartmentHandler, EnableModuleHandler
from handlers.invoice import CreateInvoiceHandler
from handlers.payment import RegisterPaymentHandler
from handlers.credit_note import CreateCreditNoteHandler
from handlers.project_invoice import ProjectInvoiceHandler
from handlers.travel_expense import CreateTravelExpenseHandler, UpdateTravelExpenseHandler, DeleteTravelExpenseHandler
from handlers.project import CreateProjectHandler
from handlers.correction import DeleteVoucherHandler
from handlers.reverse_payment import ReversePaymentHandler
from handlers.timesheet import RegisterTimesheetHandler
from handlers.salary import RunPayrollHandler
from handlers.updates import UpdateProductHandler, UpdateDepartmentHandler, UpdateProjectHandler
from handlers.supplier_invoice import CreateSupplierInvoiceHandler
# Old bank handler replaced by deterministic bank_reconciliation handler
from handlers.contact import CreateContactHandler
from handlers.voucher import CreateVoucherHandler
from handlers.year_end import YearEndHandler
from handlers.currency import CurrencyPaymentHandler
from handlers.accounting_dimension import CreateAccountingDimensionHandler
from handlers.agentic import AgenticHandler
from handlers.smart_planner import SmartPlannerHandler
from handlers.ledger_correction import LedgerCorrectionHandler
from handlers.bank_reconciliation import BankReconciliationHandler
from handlers.full_project import FullProjectCycleHandler
from handlers.cost_analysis import CostAnalysisHandler
from handlers.overdue_invoice import OverdueInvoiceHandler

REGISTRY = {
    # Tier 1
    TaskType.CREATE_EMPLOYEE: CreateEmployeeHandler,
    TaskType.UPDATE_EMPLOYEE: UpdateEmployeeHandler,
    TaskType.CREATE_CUSTOMER: CreateCustomerHandler,
    TaskType.UPDATE_CUSTOMER: UpdateCustomerHandler,
    TaskType.CREATE_PRODUCT: CreateProductHandler,
    TaskType.UPDATE_PRODUCT: UpdateProductHandler,
    TaskType.CREATE_DEPARTMENT: CreateDepartmentHandler,
    TaskType.UPDATE_DEPARTMENT: UpdateDepartmentHandler,
    TaskType.CREATE_INVOICE: CreateInvoiceHandler,
    TaskType.CREATE_PROJECT: CreateProjectHandler,
    TaskType.UPDATE_PROJECT: UpdateProjectHandler,
    TaskType.CREATE_ORDER: CreateInvoiceHandler,
    # Tier 2
    TaskType.REGISTER_PAYMENT: RegisterPaymentHandler,
    TaskType.CREATE_CREDIT_NOTE: CreateCreditNoteHandler,
    TaskType.PROJECT_INVOICE: ProjectInvoiceHandler,
    TaskType.CREATE_TRAVEL_EXPENSE: CreateTravelExpenseHandler,
    TaskType.UPDATE_TRAVEL_EXPENSE: UpdateTravelExpenseHandler,
    TaskType.DELETE_TRAVEL_EXPENSE: DeleteTravelExpenseHandler,
    TaskType.REGISTER_TIMESHEET: RegisterTimesheetHandler,
    TaskType.RUN_PAYROLL: RunPayrollHandler,
    TaskType.REVERSE_PAYMENT: ReversePaymentHandler,
    TaskType.CREATE_SUPPLIER_INVOICE: CreateSupplierInvoiceHandler,
    TaskType.CREATE_CONTACT: CreateContactHandler,
    # Tier 3
    TaskType.DELETE_VOUCHER: DeleteVoucherHandler,
    TaskType.CREATE_VOUCHER: CreateVoucherHandler,
    TaskType.OVERDUE_INVOICE: OverdueInvoiceHandler,
    TaskType.LEDGER_CORRECTION: LedgerCorrectionHandler,
    TaskType.CURRENCY_PAYMENT: CurrencyPaymentHandler,
    TaskType.YEAR_END_CLOSING: YearEndHandler,
    TaskType.CREATE_ACCOUNTING_DIMENSION: CreateAccountingDimensionHandler,
    TaskType.BANK_RECONCILIATION: BankReconciliationHandler,
    TaskType.ENABLE_MODULE: EnableModuleHandler,
    TaskType.FULL_PROJECT_CYCLE: FullProjectCycleHandler,
    TaskType.COST_ANALYSIS: CostAnalysisHandler,
    TaskType.UNKNOWN: AgenticHandler,
}
