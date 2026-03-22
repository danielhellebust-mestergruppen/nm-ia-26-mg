"""Pre-scan the competition account to understand what already exists.
All GETs are FREE — use this liberally before any writes."""
import logging

logger = logging.getLogger("handler.scanner")


async def scan_account_light(client, task_type: str) -> dict:
    """Lightweight scan based on task type — avoid overwhelming proxy with GETs."""
    ctx = {}

    # Always scan departments (needed for employees)
    try:
        r = await client.get("/department", params={"fields": "id,name", "count": 5})
        ctx["departments"] = r.get("values", [])
        ctx["default_dept_id"] = ctx["departments"][0]["id"] if ctx["departments"] else None
    except Exception:
        ctx["departments"] = []

    # Only scan what the task type needs
    invoice_types = {"create_invoice", "register_payment", "reverse_payment", "create_credit_note",
                     "project_invoice", "currency_payment", "full_project_cycle", "overdue_invoice"}
    if task_type in invoice_types:
        # Bank account check
        try:
            r = await client.get("/ledger/account", params={
                "number": "1920", "fields": "id,number,bankAccountNumber", "count": 1,
            })
            accs = r.get("values", [])
            ctx["bank_account"] = accs[0] if accs else None
            ctx["bank_needs_setup"] = bool(accs and not accs[0].get("bankAccountNumber"))
        except Exception:
            ctx["bank_needs_setup"] = True

    if task_type in {"register_payment", "reverse_payment", "currency_payment", "create_credit_note"}:
        # Need payment types
        try:
            r = await client.get("/invoice/paymentType", params={"fields": "id,description", "count": 10})
            ctx["payment_types"] = r.get("values", [])
            for pt in ctx["payment_types"]:
                if "bank" in (pt.get("description") or "").lower():
                    ctx["bank_payment_type_id"] = pt["id"]
        except Exception:
            ctx["payment_types"] = []

    return ctx


async def scan_account(client) -> dict:
    """Scan the account for existing data. Returns a context dict."""
    ctx = {}

    # Departments (needed for employee creation)
    try:
        r = await client.get("/department", params={"fields": "id,name", "count": 5})
        ctx["departments"] = r.get("values", [])
        ctx["default_dept_id"] = ctx["departments"][0]["id"] if ctx["departments"] else None
    except Exception:
        ctx["departments"] = []

    # Employees (needed for projects, timesheets)
    try:
        r = await client.get("/employee", params={"fields": "id,firstName,lastName,email", "count": 10})
        ctx["employees"] = r.get("values", [])
    except Exception:
        ctx["employees"] = []

    # Customers (needed for invoices, projects)
    try:
        r = await client.get("/customer", params={
            "fields": "id,name,organizationNumber",
            "count": 20,
        })
        ctx["customers"] = r.get("values", [])
    except Exception:
        ctx["customers"] = []

    # Products (needed for invoices)
    try:
        r = await client.get("/product", params={
            "fields": "id,name,number,priceExcludingVatCurrency",
            "count": 50,
        })
        ctx["products"] = r.get("values", [])
    except Exception:
        ctx["products"] = []

    # Bank account status
    try:
        r = await client.get("/ledger/account", params={
            "number": "1920",
            "fields": "id,number,bankAccountNumber",
            "count": 1,
        })
        accs = r.get("values", [])
        ctx["bank_account"] = accs[0] if accs else None
        ctx["bank_needs_setup"] = bool(accs and not accs[0].get("bankAccountNumber"))
    except Exception:
        ctx["bank_needs_setup"] = True

    # Invoices (for payment/credit tasks)
    try:
        r = await client.get("/invoice", params={
            "invoiceDateFrom": "2026-01-01",
            "invoiceDateTo": "2026-12-31",
            "fields": "id,invoiceNumber,amount,amountOutstanding,customer",
            "count": 20,
        })
        ctx["invoices"] = r.get("values", [])
    except Exception:
        ctx["invoices"] = []

    # Projects
    try:
        r = await client.get("/project", params={
            "fields": "id,name,number,customer,projectManager",
            "count": 20,
        })
        ctx["projects"] = r.get("values", [])
    except Exception:
        ctx["projects"] = []

    # Payment types
    try:
        r = await client.get("/invoice/paymentType", params={
            "fields": "id,description", "count": 10,
        })
        ctx["payment_types"] = r.get("values", [])
        ctx["bank_payment_type_id"] = None
        for pt in ctx["payment_types"]:
            if "bank" in (pt.get("description") or "").lower():
                ctx["bank_payment_type_id"] = pt["id"]
    except Exception:
        ctx["payment_types"] = []

    # Divisions (for payroll)
    try:
        r = await client.get("/division", params={"fields": "id,name", "count": 1})
        ctx["divisions"] = r.get("values", [])
    except Exception:
        ctx["divisions"] = []

    logger.info(f"Account scan: {len(ctx.get('customers',[]))} customers, "
                f"{len(ctx.get('products',[]))} products, "
                f"{len(ctx.get('invoices',[]))} invoices, "
                f"{len(ctx.get('projects',[]))} projects, "
                f"bank_needs_setup={ctx.get('bank_needs_setup')}")

    return ctx
