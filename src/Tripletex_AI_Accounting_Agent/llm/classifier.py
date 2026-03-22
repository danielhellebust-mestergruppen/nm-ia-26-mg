"""Two-stage LLM pipeline: quick classify → task-specific extract → validate."""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_MODEL_VISION
from llm.schemas import TaskPlan, TaskType

logger = logging.getLogger("llm.classifier")

_client = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GOOGLE_API_KEY)
    return _client


# Stage 1: Lightweight classification prompt
CLASSIFY_PROMPT = """Classify this accounting task. Return JSON: {"task_type": "..."}

Task types:
- create_employee, update_employee
- create_customer (also for suppliers/leverandør/Lieferant/fournisseur) — ONLY for NEW customers/suppliers
- update_customer (oppdater/endre/aktualisieren/actualizar/atualizar/mettre à jour — change email, phone, address of EXISTING customer. Keywords: "oppdater"/"endre"/"update"/"ändern"/"actualizar"/"atualizar"/"mettre à jour")
- create_product, update_product
- create_department, update_department
- enable_module (aktivere modul/enable module/Modul aktivieren/activar módulo/ativar módulo/activer module — enable a Tripletex module like project, payroll, travel expense)
- create_invoice (also "create order + invoice + payment" if registerPayment mentioned)
- reverse_payment (ONLY if payment was "returned by bank"/"returnert"/"devolvido"/"retourné"/"zurückgebucht" — NOT for registering new payments)
- register_payment (register NEW payment on invoice — NOT reversals)
- create_credit_note (kreditnota/Gutschrift/nota de crédito/avoir)
- project_invoice (invoice linked to project, often with hours)
- create_project, update_project
- create_travel_expense, update_travel_expense, delete_travel_expense
- register_timesheet (register hours/timer)
- run_payroll (kjør lønn/salary)
- create_supplier_invoice (incoming invoice FROM A NAMED SUPPLIER with invoice number — NOT for receipts/expenses)
- create_voucher (register expense from RECEIPT/kvittering/Quittung/recibo, business meals, office supplies — use when prompt mentions "recibo"/"receipt"/"Quittung"/"kvittering")
- create_accounting_dimension (custom dimension + values + voucher)
- create_voucher (manual journal entry/bilag)
- delete_voucher (delete/reverse voucher)
- bank_reconciliation
- overdue_invoice (find overdue/past-due invoice, post reminder fee, register partial payment — forfalt/uberfallige/überfällige/vencida/impayée/overdue. Keywords: Mahngebühr/purregebyr/cargo por recordatorio/reminder fee. ALWAYS classify as overdue_invoice if the task mentions finding an existing overdue invoice, NOT create_invoice)
- ledger_correction (find and fix errors in ledger/vouchers — feil i hovudboka/error correction/Korrekturbuchung)
- currency_payment (payment with exchange rate difference — disagio/agio/valutadifferanse/diferença cambial/Wechselkursdifferenz. Involves foreign currency invoice paid at different rate)
- year_end_closing (årsoppgjør/year-end closing/Jahresabschluss/cierre anual — depreciation, closing entries)
- full_project_cycle (complete project lifecycle: create project, register hours, register supplier costs, create invoice — prosjektsyklus/ciclo completo/cycle complet)
- cost_analysis (analyze ledger to find expense accounts, then create projects/reports — kostnadsanalyse/análise de custos/Kostenanalyse/analyse des coûts)
- unknown (ONLY if no other type fits)

IMPORTANT classification rules:
- "oppdater"/"endre"/"update"/"ändern" + customer/supplier = update_customer, NOT create_customer
- "aktivere"/"enable"/"aktivieren"/"activar"/"activer" + module = enable_module, NOT unknown
"""

# Stage 2: Task-specific extraction prompts
EXTRACT_PROMPTS = {
    "create_employee": """Extract employee data from the prompt AND any attached PDF/contract. Return JSON with "entities" object.
Fields: firstName, lastName, email, dateOfBirth (YYYY-MM-DD), phoneNumber, startDate (YYYY-MM-DD), isAdministrator (true if admin role mentioned),
employeeNumber (personnummer/personnelnummer), bankAccountNumber, departmentName (avdeling e.g. "Utvikling", "Drift"),
annualSalary (årslønn in NOK), employmentPercentage (stillingsprosent e.g. 100.0), jobCode (stillingskode/STYRK code),
employmentType (ansettelsesform e.g. "Fast stilling"), salaryType (lønnstype e.g. "Fastlønn")
IMPORTANT: If a PDF contract is attached, extract ALL fields from it. Preserve names EXACTLY including accents.""",

    "create_customer": """Extract customer/supplier data. Return JSON with "entities" object.
Fields: name, email, organizationNumber, phoneNumber, postalAddress, postalCode, city, isSupplier (true if leverandør/supplier/Lieferant/fournisseur/proveedor/fornecedor), isCustomer (default true, false only if PURE supplier)
For multiple items: {"entities": {"items": [{"name": "X"}, {"name": "Y"}]}}""",

    "create_invoice": """Extract invoice data. Return JSON with "entities" object.
Fields: customerName, customerOrganizationNumber, customerEmail, invoiceDate, dueDate, registerPayment (true if prompt also asks to register/record payment)
orderLines: list of {product (name), number (product number like "4449"), quantity, unitPrice (the price EXCLUDING VAT), vatTypeId}
VAT rules for vatTypeId:
- 25% standard → 3 (DEFAULT if not specified — most services and products in Norway)
- 15% food → 31
- 12% transport/hotel → 32
- 0% exempt → 5 (ONLY when explicitly stated as "0% MVA", "avgiftsfri", "exento de IVA", "tax exempt")
CRITICAL: "X NOK ekskl. MVA"/"ohne MwSt"/"hors TVA"/"sem IVA"/"excl. VAT"/"eksklusiv MVA" means the PRICE is quoted BEFORE standard 25% VAT — use vatTypeId=3, NOT 5.
Only use vatTypeId=5 when the prompt explicitly says the rate IS 0% or the item is tax exempt.
CRITICAL: Extract ALL order lines. Count products in prompt and verify your output matches.""",

    "reverse_payment": """Extract payment reversal data. Return JSON with "entities" object.
The invoice ALREADY EXISTS — do NOT create a new one.
Fields: customerName, customerOrganizationNumber, amount (the amount excl. VAT mentioned), description (what the invoice was for)""",

    "register_payment": """Extract payment registration data. Return JSON with "entities" object.
Fields: customerName, customerOrganizationNumber, amount, description, paymentDate
orderLines: list of {product, number, quantity, unitPrice} if multiple products""",

    "create_credit_note": """Extract credit note data. Return JSON with "entities" object.
Fields: customerName, customerOrganizationNumber, amount, description (the product/service being credited — NOT the reason), invoiceNumber, creditNoteDate, comment (reason for credit)
IMPORTANT: description = product/service name, comment = reason for crediting.""",

    "project_invoice": """Extract project invoice data. Return JSON with "entities" object.
Fields: customerName, customerOrganizationNumber, projectName, projectManagerName, projectManagerEmail, amount (the amount to INVOICE, not the fixed price), totalFixedPrice (the full fixed price if mentioned), invoiceDate, registerPayment
orderLines: list of {description, quantity, unitPrice}
IMPORTANT — If hours are mentioned, ALWAYS extract these as TOP-LEVEL fields:
- hours: the NUMBER of hours (e.g. 13)
- employeeName: who worked the hours
- employeeEmail: their email address
- activityName: the activity (e.g. "Design", "Analyse", "Utvikling")
If a fixed price and percentage are mentioned (e.g. "362300 NOK, invoice 33%"), set totalFixedPrice=362300 and amount=calculated value.""",

    "create_travel_expense": """Extract travel expense data. Return JSON with "entities" object.
Fields: employeeName, title, departureDate (YYYY-MM-DD, use today if not specified), returnDate (YYYY-MM-DD, calculate from duration), destination, purpose
costs: list of {description, amount}
perDiem: true if per diem/diett mentioned. perDiemDays: number of days. perDiemRate: daily rate.
IMPORTANT: If duration given (e.g. "4 dager"), set returnDate = departureDate + (days-1).""",

    "create_department": """Extract department data. Return JSON with "entities" object.
For single: {name, departmentNumber}
For multiple: {"items": [{"name": "HR"}, {"name": "Sales"}]}""",

    "create_product": """Extract product data. Return JSON with "entities" object.
Fields: name, number, unitPriceExcludingVat, vatTypeId (25%→3, 15%→31, 12%→32, 0%→omit), description
For multiple: {"items": [{"name": "X", "number": "1234", "unitPriceExcludingVat": 1000}]}""",

    "create_project": """Extract project data. Return JSON with "entities" object.
Fields: name, number, projectManagerName, projectManagerEmail, customerName, customerOrganizationNumber, startDate (YYYY-MM-DD), endDate, description""",

    "create_accounting_dimension": """Extract accounting dimension data. Return JSON with "entities" object.
CRITICAL: Extract ALL fields — the prompt ALWAYS contains a voucher to post after creating the dimension.
Fields: dimensionName (string), dimensionValues (list of value name strings), accountNumber (the account NUMBER for the voucher e.g. "6300" or "7300" — MUST be extracted), amount (the NOK amount for the voucher — MUST be extracted as a number), linkedDimensionValue (which dimension value to link the voucher to — MUST be extracted), description (optional)
Example: "dimension X with values A and B, post voucher on account 6300 for 25000 NOK linked to A" → accountNumber="6300", amount=25000, linkedDimensionValue="A" """,

    "run_payroll": """Extract payroll data. Return JSON with "entities" object.
Fields: employeeName, employeeEmail, baseSalary (number), bonus (number), month (integer 1-12), year (integer)
If month/year not specified, use current month/year.""",

    "create_supplier_invoice": """Extract supplier invoice data from prompt AND any attached PDF. Return JSON with "entities" object.
Fields: supplierName, organizationNumber, amount (TOTAL including VAT/TTC), description, invoiceDate (YYYY-MM-DD from fakturadato), dueDate (YYYY-MM-DD from forfallsdato), invoiceNumber, accountNumber (ledger account e.g. 6300, 6340, 6590), vatRate (the VAT% e.g. 25, 15, 12), supplierBankAccount (bank account number from PDF), address (street address from PDF), postalCode, city.
IMPORTANT: If a PDF invoice is attached, extract ALL fields from it including dates, amounts, VAT, account numbers.""",

    "register_timesheet": """Extract timesheet data. Return JSON with "entities" object.
Fields: employeeName, hours (number), date (YYYY-MM-DD), projectName, activityName, comment""",

    "update_employee": """Extract employee update data. Return JSON with "entities" object.
Fields: searchName (current name to find the employee), firstName, lastName, email, phoneNumber, address, postalCode, city, dateOfBirth, isAdministrator""",

    "update_customer": """Extract customer update data. Return JSON with "entities" object.
Fields: searchName (current name to find), name, email, phoneNumber, organizationNumber""",

    "create_voucher": """Extract voucher/journal entry data. Return JSON with "entities" object.
CRITICAL: The task prompt specifies WHICH item(s) to book. Only extract those specific items from the receipt — NOT all items.
For example, if receipt has 3 items but prompt says "book the Oppbevaringsboks", only book that ONE item.
If a receipt/image is attached, read date, vendor, and the SPECIFIC items mentioned in the prompt.
Fields: date (YYYY-MM-DD), description, departmentName (if mentioned), postings (list of {accountNumber, amount, description}).
Amount rules — Norwegian VAT rates:
- Standard 25%: most goods/services. VAT account 1610. Net = gross/1.25.
- Reduced 15%: food/beverages (restaurant, catering). VAT account 1611. Net = gross/1.15.
- Low 12%: transport, cinema, hotel/overnatting, camping. VAT account 1612. Net = gross/1.12.
- Representation/business meals (kundelunsj, forretningslunsj, kunderelasjon): MVA NOT deductible — book GROSS on 7350, no separate VAT. Credit 1920.
- Use correct expense account: 6500 (kontorutstyr), 6590 (driftsmateriale), 6860 (kontorkostnader), 7140 (reisekostnad/overnatting), 7350 (representasjon).
The postings MUST balance (sum to zero). Credit 1920 (bank) for the total paid.""",

    "delete_voucher": """Extract voucher deletion data. Return JSON with "entities" object.
Fields: voucherNumber, date, description""",

    "delete_travel_expense": """Extract travel expense deletion data. Return JSON with "entities" object.
Fields: title, description, employeeName""",

    "update_product": """Extract product update data. Return JSON with "entities" object.
Fields: searchName (current name), name, number, priceExcludingVatCurrency, description""",

    "update_department": """Extract department update data. Return JSON with "entities" object.
Fields: searchName (current name), name, departmentNumber""",

    "update_project": """Extract project update data. Return JSON with "entities" object.
Fields: searchName (current name), name, description, startDate, endDate, isClosed""",

    "bank_reconciliation": """Extract bank reconciliation data. Return JSON with "entities" object.
Fields: date, transactions (list), fileData""",

    "overdue_invoice": """Extract overdue invoice task data. Return JSON with "entities" object.
The task involves finding an EXISTING overdue invoice (no customer name given — search all invoices).
Fields: reminderFee (amount for reminder e.g. 50), debitAccount (e.g. "1500"), creditAccount (e.g. "3400"),
partialPaymentAmount (if partial payment requested), sendReminder (true if send invoice requested).
The agent will need to: GET invoices to find the overdue one, then plan writes.""",

    "ledger_correction": """Extract ledger correction data. Return JSON with "entities" object.
The task describes specific errors to find and fix in the ledger. Extract:
errors: list of {type (wrong_account/duplicate/wrong_amount/missing), description, accountNumber, correctAccount, amount, voucherDescription}
Read the full prompt carefully — it describes each error in detail.""",

    "currency_payment": """Extract currency payment with exchange rate difference. Return JSON with "entities" object.
Fields: customerName, customerOrganizationNumber, foreignAmount (amount in foreign currency e.g. 4885), currency (e.g. "EUR", "USD"), originalRate (exchange rate when invoice was sent), paymentRate (exchange rate when payment received), paymentDate.
The exchange difference (disagio/agio) = foreignAmount × (originalRate - paymentRate).""",

    "full_project_cycle": """Extract full project cycle data. Return JSON with "entities" object.
This is a multi-step task involving project creation, timesheet registration, supplier costs, and invoicing.
Fields: projectName, customerName, customerOrganizationNumber, budget (total budget in NOK),
projectManagerName, projectManagerEmail,
timesheetEntries: list of {employeeName, employeeEmail, hours, activityName},
supplierCosts: list of {supplierName, organizationNumber (org.nr/org no.), amount, description, accountNumber (expense account like 4300)},
invoiceAmount (amount to invoice), invoiceDate, sendInvoice (boolean)
Extract ALL steps mentioned in the prompt.""",

    "cost_analysis": """Extract cost analysis task data. Return JSON with "entities" object.
The task involves analyzing ledger data and creating projects or reports based on findings.
Fields: analysisType (e.g. "expense_increase", "top_expenses"), period (e.g. "jan-feb 2026"),
createProjects (boolean — true if task asks to create projects), numberOfAccounts (e.g. 3),
additionalActions: list of {action, description}
The agent will need to: GET ledger data to analyze, then execute the required actions.""",

    "year_end_closing": """Extract year-end or month-end closing / depreciation data. Return JSON with "entities" object.
Fields: year (the fiscal year, e.g. 2026), isMonthEnd (true if this is a MONTH-END closing, not year-end),
closingMonth (integer 1-12 if month-end, e.g. 3 for March),
depreciationAccount (account number for depreciation EXPENSE, e.g. "6010" or "6030"),
accumulatedDepreciationAccount (account for accumulated depreciation CREDIT, e.g. "1209" — if specified in prompt, otherwise null),
assets: list of {name, cost (original cost in NOK), years (useful life in years), account (asset account number e.g. "1250", "1200", "1210")},
closingEntries: list of {debitAccount, creditAccount, amount, description} for any additional closing entries (accruals, salary accruals, etc.).
IMPORTANT: For month-end, depreciation = (cost / years) / 12. Extract ALL entries from the prompt including salary accruals.
If amount is not specified for a closing entry, extract it from attached files (PDF/CSV) if available. Otherwise estimate (e.g. for salary accrual, use a reasonable amount like 50000).
If an attached file contains transaction data, trial balance, or specific amounts — USE those exact amounts instead of estimating.
CRITICAL: debitAccount and creditAccount must be NUMERIC account numbers (like "6000", "1700", "5000"), NOT words like "Aufwand"/"expense"/"kostnad". If the prompt says "to expense", use a reasonable expense account number (e.g. 6000 for general, 7700 for other).""",
}


async def classify_and_extract_two_stage(
    context: str, image_parts: list[types.Part] | None = None
) -> TaskPlan:
    """Two-stage pipeline: classify task type, then extract with task-specific prompt."""
    client = get_client()

    contents: list = [context]
    if image_parts:
        contents.extend(image_parts)

    # Stage 1: Quick classification
    logger.info("Stage 1: Classifying task type")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=CLASSIFY_PROMPT,
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    classify_result = json.loads(response.text)
    if isinstance(classify_result, list):
        classify_result = classify_result[0] if classify_result else {}
    if not isinstance(classify_result, dict):
        classify_result = {"task_type": "unknown"}
    task_type_str = classify_result.get("task_type", "unknown")
    logger.info(f"Stage 1 result: {task_type_str}")

    try:
        task_type = TaskType(task_type_str)
    except ValueError:
        task_type = TaskType.UNKNOWN

    # Stage 2: Task-specific extraction (use vision model if files present)
    extract_prompt = EXTRACT_PROMPTS.get(task_type_str)
    if extract_prompt:
        model = GEMINI_MODEL_VISION if image_parts else GEMINI_MODEL
        logger.info(f"Stage 2: Extracting with {task_type_str}-specific prompt (model={model})")
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=extract_prompt,
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )

        extract_result = json.loads(response.text)
        if isinstance(extract_result, list):
            entities = {"items": extract_result}
        else:
            entities = extract_result.get("entities", extract_result)
        logger.info(f"Stage 2 result: {json.dumps(entities, ensure_ascii=False)[:200]}")
    else:
        # Fallback: use the classification result or empty
        entities = classify_result.get("entities", {}) if isinstance(classify_result, dict) else {"items": classify_result}

    # Unwrap: if entities is a list, wrap in items
    if isinstance(entities, list):
        entities = {"items": entities}

    # Unwrap: if entities has "items" with exactly 1 entry AND the task isn't a multi-item type,
    # unwrap to flat fields
    if "items" in entities and isinstance(entities["items"], list):
        multi_item_types = {"create_department", "create_product", "create_customer", "create_employee"}
        if len(entities["items"]) == 1 or task_type_str not in multi_item_types:
            # Single item or non-multi type — unwrap
            if len(entities["items"]) >= 1:
                unwrapped = entities["items"][0]
                if isinstance(unwrapped, dict):
                    entities = unwrapped
                    logger.info(f"Unwrapped single item from items[]")

    # Unwrap: if entities has a nested "entities" key (LLM double-wrapped), unwrap it
    if isinstance(entities, dict) and "entities" in entities and isinstance(entities["entities"], dict):
        inner = entities.pop("entities")
        # Preserve any top-level keys that aren't in inner (like _original_prompt)
        inner.update({k: v for k, v in entities.items() if k not in inner})
        entities = inner
        logger.info("Unwrapped nested 'entities' key")

    # Sanitize: clean all date fields and remove nulls that cause API errors
    today = date.today().isoformat()
    date_fields = {"date", "invoiceDate", "dueDate", "invoiceDueDate", "startDate", "endDate",
                   "departureDate", "returnDate", "paymentDate", "creditNoteDate", "orderDate",
                   "deliveryDate", "dateOfBirth"}
    for key in list(entities.keys()):
        val = entities[key]
        if key in date_fields:
            if val is None or val == "" or val == "null":
                entities[key] = None  # Will be caught by `or today` in handlers
            elif isinstance(val, str) and not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                # Invalid format — try to parse or default to today
                logger.warning(f"Invalid date format for {key}: {val}, using today")
                entities[key] = None

    return TaskPlan(task_type=task_type, entities=entities)
