"""
Comprehensive Tripletex API accounting test suite.
Simulates a full accounting workflow against the sandbox to discover
required fields, response formats, and validation rules.

Usage:
    python3 tests/accounting_test_suite.py

Results saved to logs/sandbox-test-results.json
"""
import asyncio
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tripletex_client.client import TripletexClient, ValidationError

logging.basicConfig(level="INFO", format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("test_suite")

BASE_URL = "https://kkpqfuj-amager.tripletex.dev/v2"
TOKEN = "eyJ0b2tlbklkIjoyMTQ3NjQ1OTIyLCJ0b2tlbiI6Ijg4ZWZhMDhmLWE1YTQtNDQ1NS05ZTI0LTg0MGUwYjJjMmQ2OCJ9"

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_MONTH = (date.today() + timedelta(days=30)).isoformat()
# Unique suffix to avoid duplicate errors on persistent sandbox
RUN_ID = str(int(time.time()))[-6:]

results = []


def record(test_name: str, endpoint: str, method: str, status: str,
           request_body=None, response_body=None, error=None, notes=""):
    entry = {
        "test": test_name,
        "endpoint": endpoint,
        "method": method,
        "status": status,
        "request": request_body,
        "response_snippet": str(response_body)[:500] if response_body else None,
        "error": str(error)[:300] if error else None,
        "notes": notes,
    }
    results.append(entry)
    icon = "✓" if status == "ok" else "✗"
    logger.info(f"{icon} {test_name}: {status} {notes}")


async def run_all():
    client = TripletexClient(BASE_URL, TOKEN)
    ctx = {}  # shared context for IDs

    # =========================================================================
    # 1. COMPANY SETUP
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 1: Company Setup")
    logger.info("=" * 60)

    # 1a. Query company info (use PUT endpoint to find company)
    try:
        r = await client.get("/company", params={"fields": "id,name"})
        ctx["company"] = r.get("value", r)
        record("company_get", "/company", "GET", "ok",
               response_body=r, notes=f"Company data retrieved")
    except Exception as e:
        # /company GET may not work, try alternative
        record("company_get", "/company", "GET", "error", error=e,
               notes="Company endpoint may require specific ID")

    # 1b. Query existing departments
    try:
        r = await client.get("/department", params={"fields": "id,name,departmentNumber", "count": 10})
        ctx["departments"] = r.get("values", [])
        ctx["default_dept_id"] = ctx["departments"][0]["id"] if ctx["departments"] else None
        record("department_list", "/department", "GET", "ok",
               notes=f"Found {len(ctx['departments'])} departments")
    except Exception as e:
        record("department_list", "/department", "GET", "error", error=e)

    # 1c. Query existing employees
    try:
        r = await client.get("/employee", params={"fields": "id,firstName,lastName,email,userType", "count": 10})
        ctx["employees"] = r.get("values", [])
        record("employee_list", "/employee", "GET", "ok",
               notes=f"Found {len(ctx['employees'])} employees")
    except Exception as e:
        record("employee_list", "/employee", "GET", "error", error=e)

    # 1d. Query bank accounts
    try:
        r = await client.get("/ledger/account", params={
            "isBankAccount": "true", "fields": "id,number,name,bankAccountNumber", "count": 10
        })
        ctx["bank_accounts"] = r.get("values", [])
        record("bank_accounts", "/ledger/account", "GET", "ok",
               notes=f"Bank accounts: {[(a['number'], a['bankAccountNumber']) for a in ctx['bank_accounts']]}")
    except Exception as e:
        record("bank_accounts", "/ledger/account", "GET", "error", error=e)

    # 1e. Set bank account number on 1920
    try:
        r = await client.get("/ledger/account", params={"number": "1920", "fields": "*", "count": 1})
        accs = r.get("values", [])
        if accs and not accs[0].get("bankAccountNumber"):
            acc = accs[0]
            acc["bankAccountNumber"] = "86011117947"
            await client.put(f"/ledger/account/{acc['id']}", acc)
            record("bank_setup", "/ledger/account/{id}", "PUT", "ok",
                   notes="Set bankAccountNumber on 1920")
        else:
            record("bank_setup", "/ledger/account", "GET", "ok",
                   notes="Bank account already set or not found")
    except Exception as e:
        record("bank_setup", "/ledger/account", "PUT", "error", error=e)

    # 1f. Query VAT types
    try:
        r = await client.get("/ledger/vatType", params={"fields": "id,number,name,percentage", "count": 50})
        ctx["vat_types"] = r.get("values", [])
        vat_summary = [(v.get("number"), v.get("name", "")[:30], v.get("percentage")) for v in ctx["vat_types"][:10]]
        record("vat_types", "/ledger/vatType", "GET", "ok",
               notes=f"Found {len(ctx['vat_types'])} VAT types. First 10: {vat_summary}")
    except Exception as e:
        record("vat_types", "/ledger/vatType", "GET", "error", error=e)

    # 1g. Query payment types
    try:
        r = await client.get("/invoice/paymentType", params={"fields": "id,description", "count": 20})
        ctx["payment_types"] = r.get("values", [])
        ctx["bank_payment_type_id"] = None
        for pt in ctx["payment_types"]:
            if "bank" in pt.get("description", "").lower():
                ctx["bank_payment_type_id"] = pt["id"]
        record("payment_types", "/invoice/paymentType", "GET", "ok",
               notes=f"Payment types: {ctx['payment_types']}")
    except Exception as e:
        record("payment_types", "/invoice/paymentType", "GET", "error", error=e)

    # =========================================================================
    # 2. EMPLOYEE MANAGEMENT
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 2: Employee Management")
    logger.info("=" * 60)

    # 2a. Create employee (minimal)
    try:
        r = await client.post("/employee", {
            "firstName": f"Anna{RUN_ID}",
            "lastName": "Berg",
            "email": f"anna.berg.{RUN_ID}@example.org",
            "userType": "EXTENDED",
            "department": {"id": ctx["default_dept_id"]},
        })
        ctx["employee_anna_id"] = r["value"]["id"]
        record("employee_create_minimal", "/employee", "POST", "ok",
               request_body={"firstName": f"Anna{RUN_ID}", "userType": "EXTENDED"},
               notes=f"id={ctx['employee_anna_id']}")
    except Exception as e:
        record("employee_create_minimal", "/employee", "POST", "error", error=e)

    # 2b. Create employee with all fields
    try:
        r = await client.post("/employee", {
            "firstName": f"Erik{RUN_ID}",
            "lastName": "Solvang",
            "email": f"erik.solvang.{RUN_ID}@example.org",
            "userType": "EXTENDED",
            "department": {"id": ctx["default_dept_id"]},
            "dateOfBirth": "1985-06-15",
            "phoneNumberMobile": "98765432",
            "employeeNumber": f"EMP{RUN_ID}",
        })
        ctx["employee_erik_id"] = r["value"]["id"]
        record("employee_create_full", "/employee", "POST", "ok",
               notes=f"id={ctx['employee_erik_id']} with DOB, phone, number")
    except Exception as e:
        record("employee_create_full", "/employee", "POST", "error", error=e)

    # 2c. Grant admin role
    try:
        eid = ctx.get("employee_anna_id")
        if eid:
            await client.put(
                f"/employee/entitlement/:grantEntitlementsByTemplate?employeeId={eid}&template=ALL_PRIVILEGES", {}
            )
            record("employee_grant_admin", "/employee/entitlement/:grantEntitlementsByTemplate", "PUT", "ok",
                   notes=f"ALL_PRIVILEGES granted to employee {eid}")
    except Exception as e:
        record("employee_grant_admin", "/employee/entitlement", "PUT", "error", error=e)

    # 2d. Update employee
    try:
        eid = ctx.get("employee_erik_id")
        if eid:
            emp = (await client.get(f"/employee/{eid}", params={"fields": "*"}))["value"]
            emp["phoneNumberMobile"] = "11223344"
            emp["comments"] = "Updated via test suite"
            await client.put(f"/employee/{eid}", emp)
            record("employee_update", f"/employee/{eid}", "PUT", "ok",
                   notes="Updated phone + comments")
    except Exception as e:
        record("employee_update", "/employee/{id}", "PUT", "error", error=e,
               notes="May require dateOfBirth for PUT")

    # 2e. Search employee by firstName
    try:
        r = await client.get("/employee", params={"firstName": "Anna", "fields": "id,firstName,lastName", "count": 5})
        found = r.get("values", [])
        record("employee_search", "/employee", "GET", "ok",
               notes=f"Search 'Anna': found {len(found)} results")
    except Exception as e:
        record("employee_search", "/employee", "GET", "error", error=e)

    # =========================================================================
    # 3. CUSTOMER & SUPPLIER MANAGEMENT
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 3: Customer & Supplier Management")
    logger.info("=" * 60)

    # 3a. Create customer
    try:
        r = await client.post("/customer", {
            "name": "Nordvik Consulting AS",
            "email": "post@nordvik.no",
            "organizationNumber": "912345678",
            "isCustomer": True,
            "phoneNumber": "22334455",
        })
        ctx["customer_id"] = r["value"]["id"]
        record("customer_create", "/customer", "POST", "ok",
               notes=f"id={ctx['customer_id']} with org number + email + phone")
    except Exception as e:
        record("customer_create", "/customer", "POST", "error", error=e)

    # 3b. Create supplier (not customer)
    try:
        r = await client.post("/customer", {
            "name": "Leverandør Oslo AS",
            "email": "faktura@leverandor.no",
            "organizationNumber": "987654321",
            "isCustomer": False,
            "isSupplier": True,
        })
        ctx["supplier_id"] = r["value"]["id"]
        record("supplier_create", "/customer", "POST", "ok",
               notes=f"id={ctx['supplier_id']} isCustomer=false, isSupplier=true")
    except Exception as e:
        record("supplier_create", "/customer", "POST", "error", error=e)

    # 3c. Create customer+supplier combo
    try:
        r = await client.post("/customer", {
            "name": "Dual Role AS",
            "isCustomer": True,
            "isSupplier": True,
            "organizationNumber": "111222333",
        })
        ctx["dual_id"] = r["value"]["id"]
        record("customer_supplier_dual", "/customer", "POST", "ok",
               notes=f"id={ctx['dual_id']} both customer and supplier")
    except Exception as e:
        record("customer_supplier_dual", "/customer", "POST", "error", error=e)

    # 3d. Update customer
    try:
        cid = ctx.get("customer_id")
        if cid:
            cust = (await client.get(f"/customer/{cid}", params={"fields": "*"}))["value"]
            cust["phoneNumberMobile"] = "99887766"
            cust["description"] = "Key account"
            await client.put(f"/customer/{cid}", cust)
            record("customer_update", f"/customer/{cid}", "PUT", "ok",
                   notes="Updated mobile + description")
    except Exception as e:
        record("customer_update", "/customer/{id}", "PUT", "error", error=e)

    # =========================================================================
    # 4. PRODUCT MANAGEMENT
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 4: Product Management")
    logger.info("=" * 60)

    # 4a. Create product (minimal)
    try:
        r = await client.post("/product", {"name": f"Consulting Hours {RUN_ID}"})
        ctx["product_basic_id"] = r["value"]["id"]
        record("product_create_minimal", "/product", "POST", "ok",
               notes=f"id={ctx['product_basic_id']} name only")
    except Exception as e:
        record("product_create_minimal", "/product", "POST", "error", error=e)

    # 4b. Create product with price
    try:
        r = await client.post("/product", {
            "name": f"Software License {RUN_ID}",
            "number": f"PROD-{RUN_ID}",
            "priceExcludingVatCurrency": 5000,
            "description": "Annual software license",
        })
        ctx["product_full_id"] = r["value"]["id"]
        product_vat = r["value"].get("vatType", {}).get("id")
        record("product_create_full", "/product", "POST", "ok",
               notes=f"id={ctx['product_full_id']} price=5000, default vatType={product_vat}")
    except Exception as e:
        record("product_create_full", "/product", "POST", "error", error=e)

    # 4c. Create product with explicit VAT type
    try:
        r = await client.post("/product", {
            "name": f"Zero VAT Service {RUN_ID}",
            "priceExcludingVatCurrency": 2000,
            "vatType": {"id": 0},
        })
        record("product_create_no_vat", "/product", "POST", "ok",
               notes=f"vatType=0 (exempt)")
    except Exception as e:
        record("product_create_no_vat", "/product", "POST", "error", error=e)

    # =========================================================================
    # 5. DEPARTMENT MANAGEMENT
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 5: Department Management")
    logger.info("=" * 60)

    # 5a. Create department
    try:
        r = await client.post("/department", {
            "name": f"Engineering {RUN_ID}",
            "departmentNumber": RUN_ID[:3],
        })
        ctx["dept_eng_id"] = r["value"]["id"]
        record("department_create", "/department", "POST", "ok",
               notes=f"id={ctx['dept_eng_id']}")
    except Exception as e:
        record("department_create", "/department", "POST", "error", error=e)

    # 5b. Create department with manager
    try:
        r = await client.post("/department", {
            "name": f"Sales {RUN_ID}",
            "departmentNumber": str(int(RUN_ID[:3]) + 1),
            "departmentManager": {"id": ctx.get("employee_anna_id", ctx["employees"][0]["id"])},
        })
        ctx["dept_sales_id"] = r["value"]["id"]
        record("department_create_with_manager", "/department", "POST", "ok",
               notes=f"id={ctx['dept_sales_id']} with manager")
    except Exception as e:
        record("department_create_with_manager", "/department", "POST", "error", error=e)

    # =========================================================================
    # 6. PROJECT MANAGEMENT
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 6: Project Management")
    logger.info("=" * 60)

    # 6a. Create project (minimal)
    try:
        r = await client.post("/project", {
            "name": "Website Redesign",
            "startDate": TODAY,
            "projectManager": {"id": ctx.get("employee_anna_id", ctx["employees"][0]["id"])},
        })
        ctx["project_basic_id"] = r["value"]["id"]
        record("project_create_minimal", "/project", "POST", "ok",
               notes=f"id={ctx['project_basic_id']} with startDate + manager")
    except Exception as e:
        record("project_create_minimal", "/project", "POST", "error", error=e)

    # 6b. Create project linked to customer
    try:
        r = await client.post("/project", {
            "name": "ERP Implementation",
            "startDate": TODAY,
            "endDate": NEXT_MONTH,
            "customer": {"id": ctx.get("customer_id")},
            "projectManager": {"id": ctx.get("employee_erik_id", ctx["employees"][0]["id"])},
            "description": "Full ERP rollout",
        })
        ctx["project_full_id"] = r["value"]["id"]
        record("project_create_full", "/project", "POST", "ok",
               notes=f"id={ctx['project_full_id']} with customer + endDate + description")
    except Exception as e:
        record("project_create_full", "/project", "POST", "error", error=e)

    # =========================================================================
    # 7. INVOICING WORKFLOW
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 7: Invoicing Workflow")
    logger.info("=" * 60)

    # 7a. Create order with order lines
    try:
        r = await client.post("/order", {
            "customer": {"id": ctx["customer_id"]},
            "orderDate": TODAY,
            "deliveryDate": TODAY,
            "orderLines": [
                {"description": "Consulting Q1", "count": 10, "unitPriceExcludingVatCurrency": 1500},
                {"description": "Travel expenses", "count": 1, "unitPriceExcludingVatCurrency": 3000},
            ],
        })
        ctx["order_id"] = r["value"]["id"]
        record("order_create", "/order", "POST", "ok",
               notes=f"id={ctx['order_id']} with 2 order lines")
    except Exception as e:
        record("order_create", "/order", "POST", "error", error=e)

    # 7b. Create order linked to project
    try:
        r = await client.post("/order", {
            "customer": {"id": ctx["customer_id"]},
            "project": {"id": ctx.get("project_full_id")},
            "orderDate": TODAY,
            "deliveryDate": TODAY,
            "orderLines": [
                {"description": "Project milestone 1", "count": 1, "unitPriceExcludingVatCurrency": 50000},
            ],
        })
        ctx["order_project_id"] = r["value"]["id"]
        record("order_create_with_project", "/order", "POST", "ok",
               notes=f"id={ctx['order_project_id']} linked to project")
    except Exception as e:
        record("order_create_with_project", "/order", "POST", "error", error=e)

    # 7c. Create invoice from order
    try:
        r = await client.post("/invoice", {
            "invoiceDate": TODAY,
            "invoiceDueDate": NEXT_MONTH,
            "customer": {"id": ctx["customer_id"]},
            "orders": [{"id": ctx["order_id"]}],
        })
        ctx["invoice_id"] = r["value"]["id"]
        ctx["invoice_number"] = r["value"].get("invoiceNumber")
        record("invoice_create", "/invoice", "POST", "ok",
               notes=f"id={ctx['invoice_id']} number={ctx['invoice_number']} dueDate={NEXT_MONTH}")
    except Exception as e:
        record("invoice_create", "/invoice", "POST", "error", error=e)

    # 7d. Create project invoice
    try:
        r = await client.post("/invoice", {
            "invoiceDate": TODAY,
            "invoiceDueDate": NEXT_MONTH,
            "customer": {"id": ctx["customer_id"]},
            "orders": [{"id": ctx.get("order_project_id")}],
        })
        ctx["project_invoice_id"] = r["value"]["id"]
        record("invoice_create_project", "/invoice", "POST", "ok",
               notes=f"id={ctx['project_invoice_id']} project-linked invoice")
    except Exception as e:
        record("invoice_create_project", "/invoice", "POST", "error", error=e)

    # 7e. Register payment on invoice
    try:
        inv_id = ctx.get("invoice_id")
        pt_id = ctx.get("bank_payment_type_id", ctx["payment_types"][0]["id"])
        if inv_id:
            await client.put(f"/invoice/{inv_id}/:payment", {}, params={
                "paymentDate": TODAY,
                "paymentTypeId": pt_id,
                "paidAmount": 18000,  # 10*1500 + 3000
            })
            record("invoice_payment", f"/invoice/{inv_id}/:payment", "PUT", "ok",
                   notes=f"Paid 18000 via paymentTypeId={pt_id}")
    except Exception as e:
        record("invoice_payment", "/invoice/{id}/:payment", "PUT", "error", error=e)

    # 7f. Create credit note
    try:
        inv_id = ctx.get("project_invoice_id")
        if inv_id:
            r = await client.put(f"/invoice/{inv_id}/:createCreditNote", {}, params={
                "date": TODAY,
                "comment": "Test credit note",
                "sendToCustomer": False,
            })
            ctx["credit_note_id"] = r.get("value", {}).get("id")
            record("credit_note_create", f"/invoice/{inv_id}/:createCreditNote", "PUT", "ok",
                   notes=f"Credit note id={ctx.get('credit_note_id')}")
    except Exception as e:
        record("credit_note_create", "/invoice/{id}/:createCreditNote", "PUT", "error", error=e)

    # 7g. Query invoices (requires date range)
    try:
        r = await client.get("/invoice", params={
            "invoiceDateFrom": "2026-01-01",
            "invoiceDateTo": "2026-12-31",
            "fields": "id,invoiceNumber,invoiceDate",
            "count": 10,
        })
        invoices = r.get("values", [])
        record("invoice_list", "/invoice", "GET", "ok",
               notes=f"Found {len(invoices)} invoices")
    except Exception as e:
        record("invoice_list", "/invoice", "GET", "error", error=e)

    # =========================================================================
    # 8. TRAVEL EXPENSES
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 8: Travel Expenses")
    logger.info("=" * 60)

    # 8a. Create travel expense
    try:
        eid = ctx.get("employee_anna_id", ctx["employees"][0]["id"])
        r = await client.post("/travelExpense", {
            "employee": {"id": eid},
            "title": f"Client visit Oslo {RUN_ID}",
            "travelDetails": {
                "departureDate": TODAY,
                "returnDate": TOMORROW,
                "destination": "Oslo",
                "purpose": "Client meeting",
            },
        })
        ctx["travel_expense_id"] = r["value"]["id"]
        record("travel_expense_create", "/travelExpense", "POST", "ok",
               notes=f"id={ctx['travel_expense_id']} with travelDetails")
    except Exception as e:
        record("travel_expense_create", "/travelExpense", "POST", "error", error=e)

    # 8b. List travel expenses
    try:
        r = await client.get("/travelExpense", params={
            "fields": "id,title",
            "count": 10,
        })
        expenses = r.get("values", [])
        record("travel_expense_list", "/travelExpense", "GET", "ok",
               notes=f"Found {len(expenses)} travel expenses")
    except Exception as e:
        record("travel_expense_list", "/travelExpense", "GET", "error", error=e)

    # 8c. Delete travel expense
    try:
        te_id = ctx.get("travel_expense_id")
        if te_id:
            await client.delete(f"/travelExpense/{te_id}")
            record("travel_expense_delete", f"/travelExpense/{te_id}", "DELETE", "ok",
                   notes=f"Deleted travel expense {te_id}")
    except Exception as e:
        record("travel_expense_delete", "/travelExpense/{id}", "DELETE", "error", error=e)

    # =========================================================================
    # 9. LEDGER & VOUCHERS
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 9: Ledger & Vouchers")
    logger.info("=" * 60)

    # 9a. Query chart of accounts
    try:
        r = await client.get("/ledger/account", params={
            "fields": "id,number,name,vatType",
            "from": 0, "count": 20,
        })
        accounts = r.get("values", [])
        record("ledger_accounts", "/ledger/account", "GET", "ok",
               notes=f"Found {r.get('fullResultSize', '?')} accounts (showing 20)")
    except Exception as e:
        record("ledger_accounts", "/ledger/account", "GET", "error", error=e)

    # 9b. Query ledger postings
    try:
        r = await client.get("/ledger/posting", params={
            "dateFrom": TODAY, "dateTo": TODAY,
            "fields": "id,date,description,account,amount",
            "count": 20,
        })
        postings = r.get("values", [])
        record("ledger_postings", "/ledger/posting", "GET", "ok",
               notes=f"Found {len(postings)} postings for today")
    except Exception as e:
        record("ledger_postings", "/ledger/posting", "GET", "error", error=e)

    # 9c. Query vouchers (requires date range)
    try:
        r = await client.get("/ledger/voucher", params={
            "dateFrom": "2026-01-01",
            "dateTo": "2026-12-31",
            "fields": "id,number,date",
            "count": 20,
        })
        vouchers = r.get("values", [])
        record("ledger_vouchers", "/ledger/voucher", "GET", "ok",
               notes=f"Found {len(vouchers)} vouchers")
    except Exception as e:
        record("ledger_vouchers", "/ledger/voucher", "GET", "error", error=e)

    # 9d. Create a manual voucher (journal entry)
    try:
        r = await client.post("/ledger/voucher", {
            "date": TODAY,
            "description": "Test journal entry",
            "postings": [
                {"date": TODAY, "account": {"id": 433432494}, "amount": 1000, "description": "Debit bank"},
                {"date": TODAY, "account": {"id": 433432517}, "amount": -1000, "description": "Credit sales"},
            ],
        })
        ctx["voucher_id"] = r["value"]["id"]
        record("voucher_create", "/ledger/voucher", "POST", "ok",
               notes=f"id={ctx['voucher_id']} manual journal entry")
    except Exception as e:
        record("voucher_create", "/ledger/voucher", "POST", "error", error=e,
               notes="May need valid account IDs from this sandbox")

    # 9e. Delete voucher
    try:
        vid = ctx.get("voucher_id")
        if vid:
            await client.delete(f"/ledger/voucher/{vid}")
            record("voucher_delete", f"/ledger/voucher/{vid}", "DELETE", "ok",
                   notes=f"Deleted voucher {vid}")
    except Exception as e:
        record("voucher_delete", "/ledger/voucher/{id}", "DELETE", "error", error=e)

    # =========================================================================
    # 10. UPDATE OPERATIONS
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 10: Update Operations")
    logger.info("=" * 60)

    # 10a. Update product
    try:
        pid = ctx.get("product_full_id")
        if pid:
            prod = (await client.get(f"/product/{pid}", params={"fields": "*"}))["value"]
            prod["description"] = f"Updated description {RUN_ID}"
            await client.put(f"/product/{pid}", prod)
            record("product_update", f"/product/{pid}", "PUT", "ok",
                   notes="Updated description")
    except Exception as e:
        record("product_update", "/product/{id}", "PUT", "error", error=e)

    # 10b. Update department
    try:
        did = ctx.get("dept_eng_id")
        if did:
            dept = (await client.get(f"/department/{did}", params={"fields": "*"}))["value"]
            dept["name"] = f"Engineering Updated {RUN_ID}"
            await client.put(f"/department/{did}", dept)
            record("department_update", f"/department/{did}", "PUT", "ok",
                   notes="Updated name")
    except Exception as e:
        record("department_update", "/department/{id}", "PUT", "error", error=e)

    # 10c. Update project (use limited fields to avoid non-updatable nested objects)
    try:
        pid = ctx.get("project_basic_id")
        if pid:
            proj_fields = "id,version,name,number,description,startDate,endDate,customer,projectManager,department,isClosed"
            proj = (await client.get(f"/project/{pid}", params={"fields": proj_fields}))["value"]
            proj["description"] = f"Updated project {RUN_ID}"
            await client.put(f"/project/{pid}", proj)
            record("project_update", f"/project/{pid}", "PUT", "ok",
                   notes="Updated description (limited fields)")
    except Exception as e:
        record("project_update", "/project/{id}", "PUT", "error", error=e)

    # =========================================================================
    # 11. TIMESHEET & PAYROLL
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 11: Timesheet & Payroll")
    logger.info("=" * 60)

    # 11a. Get activities
    try:
        r = await client.get("/activity", params={"fields": "id,name", "count": 10})
        ctx["activities"] = r.get("values", [])
        record("activity_list", "/activity", "GET", "ok",
               notes=f"Found {len(ctx['activities'])} activities: {[a['name'] for a in ctx['activities']]}")
    except Exception as e:
        record("activity_list", "/activity", "GET", "error", error=e)

    # 11b. Register timesheet entry (use unique date to avoid 409 Conflict)
    try:
        eid = ctx.get("employee_anna_id", ctx["employees"][0]["id"])
        act_id = ctx["activities"][0]["id"] if ctx.get("activities") else None
        # Use a future date unlikely to conflict
        ts_date = (date.today() + timedelta(days=10 + int(RUN_ID[-1]))).isoformat()
        if act_id:
            r = await client.post("/timesheet/entry", {
                "employee": {"id": eid},
                "date": ts_date,
                "hours": 7.5,
                "activity": {"id": act_id},
            })
            ctx["timesheet_id"] = r["value"]["id"]
            record("timesheet_create", "/timesheet/entry", "POST", "ok",
                   notes=f"id={ctx['timesheet_id']} 7.5h on {ts_date}")
    except Exception as e:
        record("timesheet_create", "/timesheet/entry", "POST", "error", error=e)

    # 11c. Timesheet with project (use chargeable activity)
    try:
        eid = ctx.get("employee_anna_id", ctx["employees"][0]["id"])
        # Find chargeable activity for project work
        chargeable_id = None
        for act in ctx.get("activities", []):
            if act.get("isChargeable") or "faktur" in act.get("name", "").lower():
                chargeable_id = act["id"]
                break
        if not chargeable_id:
            chargeable_id = ctx["activities"][-1]["id"] if ctx.get("activities") else None
        proj_id = ctx.get("project_basic_id")
        ts_date2 = (date.today() + timedelta(days=11 + int(RUN_ID[-1]))).isoformat()
        if chargeable_id and proj_id:
            r = await client.post("/timesheet/entry", {
                "employee": {"id": eid},
                "date": ts_date2,
                "hours": 3,
                "activity": {"id": chargeable_id},
                "project": {"id": proj_id},
                "comment": "Project work",
            })
            record("timesheet_with_project", "/timesheet/entry", "POST", "ok",
                   notes=f"3h on project with chargeable activity")
    except Exception as e:
        record("timesheet_with_project", "/timesheet/entry", "POST", "error", error=e)

    # 11d. Salary types lookup
    try:
        r = await client.get("/salary/type", params={"fields": "id,number,name", "count": 30})
        ctx["salary_types"] = r.get("values", [])
        record("salary_types", "/salary/type", "GET", "ok",
               notes=f"Found {len(ctx['salary_types'])} salary types")
    except Exception as e:
        record("salary_types", "/salary/type", "GET", "error", error=e)

    # 11e. Salary transaction (best effort — may fail without employment/division)
    try:
        eid = ctx["employees"][0]["id"]
        fastlonn_id = None
        for st in ctx.get("salary_types", []):
            if "fastlønn" in st.get("name", "").lower() or st.get("number") == "2000":
                fastlonn_id = st["id"]
                break
        if fastlonn_id:
            r = await client.post("/salary/transaction", {
                "date": TODAY,
                "month": 3,
                "year": 2026,
                "payslips": [{
                    "employee": {"id": eid},
                    "date": TODAY,
                    "month": 3,
                    "year": 2026,
                    "specifications": [{
                        "salaryType": {"id": fastlonn_id},
                        "amount": 50000,
                        "count": 1,
                        "rate": 50000,
                        "month": 3,
                        "year": 2026,
                    }],
                }],
            })
            record("salary_transaction", "/salary/transaction", "POST", "ok",
                   notes="Payroll transaction created")
    except Exception as e:
        record("salary_transaction", "/salary/transaction", "POST", "error",
               error=e, notes="May need employment linked to division")

    # =========================================================================
    # 12. SUPPLIER INVOICE & CONTACTS
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 12: Supplier Invoice & Contacts")
    logger.info("=" * 60)

    # 12a. Create contact for customer
    try:
        cid = ctx.get("customer_id")
        if cid:
            r = await client.post("/contact", {
                "firstName": f"Kontakt{RUN_ID}",
                "lastName": "Person",
                "email": f"kontakt.{RUN_ID}@example.org",
                "customer": {"id": cid},
            })
            ctx["contact_id"] = r["value"]["id"]
            record("contact_create", "/contact", "POST", "ok",
                   notes=f"id={ctx['contact_id']} linked to customer {cid}")
    except Exception as e:
        record("contact_create", "/contact", "POST", "error", error=e)

    # 12b. Incoming/supplier invoice (IncomingInvoiceAggregateExternalWrite schema)
    try:
        r = await client.post("/incomingInvoice", {
            "invoiceHeader": {
                "vendorId": ctx.get("supplier_id"),
                "invoiceDate": TODAY,
                "dueDate": NEXT_MONTH,
                "invoiceAmount": 25000,
                "description": "Test supplier invoice",
            },
            "orderLines": [{
                "description": "Office supplies",
                "amountInclVat": 25000,
            }],
        })
        ctx["supplier_invoice_id"] = r.get("value", {}).get("id", "?")
        record("supplier_invoice_create", "/incomingInvoice", "POST", "ok",
               notes=f"id={ctx['supplier_invoice_id']}")
    except Exception as e:
        record("supplier_invoice_create", "/incomingInvoice", "POST", "error",
               error=e, notes="Incoming invoice may need specific module")

    # =========================================================================
    # 13. BANK RECONCILIATION
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 13: Bank Reconciliation")
    logger.info("=" * 60)

    # 13a. Create bank reconciliation (needs account + accountingPeriod + type)
    try:
        r = await client.get("/ledger/account", params={
            "number": "1920", "fields": "id", "count": 1,
        })
        accs = r.get("values", [])
        # Find current accounting period
        periods = await client.get("/ledger/accountingPeriod", params={
            "fields": "id,start,end", "count": 12,
        })
        period_id = None
        for p in periods.get("values", []):
            if p.get("start", "") <= TODAY < p.get("end", "9999"):
                period_id = p["id"]
                break
        if accs and period_id:
            r = await client.post("/bank/reconciliation", {
                "account": {"id": accs[0]["id"]},
                "accountingPeriod": {"id": period_id},
                "type": "MANUAL",
            })
            ctx["bank_recon_id"] = r["value"]["id"]
            record("bank_reconciliation_create", "/bank/reconciliation", "POST", "ok",
                   notes=f"id={ctx['bank_recon_id']} with period {period_id}")
    except Exception as e:
        record("bank_reconciliation_create", "/bank/reconciliation", "POST", "error",
               error=e, notes="Bank reconciliation requires account + accounting period")

    # 13b. Update travel expense
    try:
        # Create one first, then update
        eid = ctx.get("employee_anna_id", ctx["employees"][0]["id"])
        r = await client.post("/travelExpense", {
            "employee": {"id": eid},
            "title": f"Update test {RUN_ID}",
        })
        te_id = r["value"]["id"]
        te = (await client.get(f"/travelExpense/{te_id}", params={"fields": "*"}))["value"]
        te["title"] = f"Updated title {RUN_ID}"
        await client.put(f"/travelExpense/{te_id}", te)
        record("travel_expense_update", f"/travelExpense/{te_id}", "PUT", "ok",
               notes="Updated title")
        # Clean up
        await client.delete(f"/travelExpense/{te_id}")
    except Exception as e:
        record("travel_expense_update", "/travelExpense/{id}", "PUT", "error", error=e)

    # 13c. Add cost to travel expense
    try:
        eid = ctx.get("employee_anna_id", ctx["employees"][0]["id"])
        r = await client.post("/travelExpense", {
            "employee": {"id": eid},
            "title": f"Cost test {RUN_ID}",
        })
        te_id = r["value"]["id"]
        # Get cost categories
        cats = (await client.get("/travelExpense/costCategory", params={"fields": "id,description", "count": 5}))
        cat_id = cats["values"][0]["id"] if cats.get("values") else None
        if cat_id:
            await client.post("/travelExpense/cost", {
                "travelExpense": {"id": te_id},
                "date": TODAY,
                "amountCurrencyIncVat": 500,
                "currency": {"id": 1},
                "costCategory": {"id": cat_id},
                "paymentType": {"id": 0},
            })
            record("travel_expense_add_cost", "/travelExpense/cost", "POST", "ok",
                   notes=f"Added 500 NOK cost to expense {te_id}")
        await client.delete(f"/travelExpense/{te_id}")
    except Exception as e:
        record("travel_expense_add_cost", "/travelExpense/cost", "POST", "error", error=e)

    # 13d. Send invoice
    try:
        inv_id = ctx.get("invoice_id")
        if inv_id:
            await client.put(f"/invoice/{inv_id}/:send", {}, params={
                "sendType": "EMAIL",
                "overrideEmailAddress": "",
            })
            record("invoice_send", f"/invoice/{inv_id}/:send", "PUT", "ok",
                   notes="Invoice sent")
    except Exception as e:
        record("invoice_send", "/invoice/{id}/:send", "PUT", "error",
               error=e, notes="May need customer email set")

    # 13e. Reverse voucher
    try:
        # Find a voucher to reverse
        r = await client.get("/ledger/voucher", params={
            "dateFrom": "2026-01-01", "dateTo": "2026-12-31",
            "fields": "id,number", "count": 1,
        })
        vouchers = r.get("values", [])
        if vouchers:
            vid = vouchers[0]["id"]
            await client.put(f"/ledger/voucher/{vid}/:reverse", {}, params={"date": TODAY})
            record("voucher_reverse", f"/ledger/voucher/{vid}/:reverse", "PUT", "ok",
                   notes=f"Reversed voucher {vid}")
    except Exception as e:
        record("voucher_reverse", "/ledger/voucher/{id}/:reverse", "PUT", "error",
               error=e, notes="Some vouchers may not be reversible")

    # =========================================================================
    # 14. EDGE CASES & VALIDATION
    # =========================================================================
    logger.info("=" * 60)
    logger.info("PHASE 10: Edge Cases & Validation")
    logger.info("=" * 60)

    # 10a. Employee without userType
    try:
        r = await client.post("/employee", {"firstName": "NoType", "lastName": "Test"})
        record("edge_employee_no_usertype", "/employee", "POST", "ok",
               notes="Unexpected success without userType")
    except Exception as e:
        record("edge_employee_no_usertype", "/employee", "POST", "expected_error",
               error=e, notes="Confirms userType is required")

    # 10b. Employee without department
    try:
        r = await client.post("/employee", {"firstName": "NoDept", "lastName": "Test", "userType": "STANDARD"})
        record("edge_employee_no_dept", "/employee", "POST", "ok",
               notes="Unexpected success without department")
    except Exception as e:
        record("edge_employee_no_dept", "/employee", "POST", "expected_error",
               error=e, notes="Confirms department is required")

    # 10c. Project without startDate
    try:
        r = await client.post("/project", {"name": "No Start Date"})
        record("edge_project_no_startdate", "/project", "POST", "ok",
               notes="Unexpected success without startDate")
    except Exception as e:
        record("edge_project_no_startdate", "/project", "POST", "expected_error",
               error=e, notes="Confirms startDate is required")

    # 10d. Invoice without bank account (would fail on fresh account)
    # Already tested via bank setup

    # 10e. Customer with all optional fields
    try:
        r = await client.post("/customer", {
            "name": "Full Customer AS",
            "email": "full@customer.no",
            "organizationNumber": "444555666",
            "phoneNumber": "11112222",
            "phoneNumberMobile": "33334444",
            "isCustomer": True,
            "isSupplier": False,
            "invoiceEmail": "invoice@customer.no",
            "language": "EN",
            "description": "Full test customer",
            "postalAddress": {
                "addressLine1": "Testveien 1",
                "postalCode": "0150",
                "city": "Oslo",
            },
        })
        record("edge_customer_all_fields", "/customer", "POST", "ok",
               notes=f"Created with all optional fields, id={r['value']['id']}")
    except Exception as e:
        record("edge_customer_all_fields", "/customer", "POST", "error", error=e)

    return ctx


async def main():
    start = time.time()
    logger.info("Starting comprehensive accounting test suite")
    ctx = await run_all()
    elapsed = round(time.time() - start, 1)

    # Save results
    out_dir = Path(__file__).parent.parent / "logs"
    out_dir.mkdir(exist_ok=True)

    results_file = out_dir / "sandbox-test-results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Print summary
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    expected = sum(1 for r in results if r["status"] == "expected_error")

    logger.info("=" * 60)
    logger.info(f"DONE in {elapsed}s — {ok} passed, {err} failed, {expected} expected errors")
    logger.info(f"Results saved to {results_file}")
    logger.info("=" * 60)

    # Print failures
    if err > 0:
        logger.info("FAILURES:")
        for r in results:
            if r["status"] == "error":
                logger.info(f"  ✗ {r['test']}: {r['error']}")

    # Print discovered requirements
    logger.info("")
    logger.info("KEY FINDINGS:")
    for r in results:
        if r["notes"] and ("required" in r["notes"].lower() or "confirms" in r["notes"].lower()):
            logger.info(f"  • {r['notes']}")


if __name__ == "__main__":
    asyncio.run(main())
