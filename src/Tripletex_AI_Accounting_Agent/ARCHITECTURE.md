# NM i AI 2026 - Tripletex Agent Architecture

> FastAPI service on Google Cloud Run (europe-north1, 2Gi/2CPU)
> Models: `gemini-3-flash-preview` (text) / `gemini-3.1-pro-preview` (vision)

---

## High-Level Flow

```
Competition Platform
        │
        │  POST /solve
        │  {prompt, files[], tripletex_credentials}
        ▼
┌───────────────────┐
│   1. Setup        │──► TripletexClient (httpx, Basic Auth)
│                   │──► API call tracker (monkey-patched GET/POST/PUT/DELETE)
└────────┬──────────┘
         ▼
┌───────────────────┐
│  2. File Process  │──► PDF → pdfplumber text+tables (or vision Part if image-based)
│                   │──► Images → google.genai.types.Part
│                   │──► Other → UTF-8 decode
└────────┬──────────┘
         ▼
┌───────────────────┐
│  3. LLM Classify  │──► Stage 1: Task type classification (gemini-3-flash)
│     (two-stage)   │──► Stage 2: Entity extraction (task-specific prompt)
└────────┬──────────┘
         ▼
┌───────────────────┐
│  4. Enrich        │──► Inject _original_prompt, _has_files
│                   │──► Lightweight account scan (task-specific GETs)
│                   │──► Routing decision: smart planner vs handler
└────────┬──────────┘
         ▼
┌───────────────────┐     ┌──────────────────┐
│ 5. Execute        │────►│ Deterministic    │ (33 registered handlers)
│                   │  or │ Smart Planner    │ (Gemini-planned writes)
│                   │  or │ Agentic          │ (multi-turn Gemini loop)
└────────┬──────────┘     └──────────────────┘
         │
         ▼  (on handler exception)
┌───────────────────┐
│  6. Recovery      │──► AgenticHandler with error context injected
└────────┬──────────┘
         ▼
┌───────────────────┐
│  7. Response      │──► SUBMISSION_SUMMARY log
│                   │──► Return {"status": "completed"}
└───────────────────┘
```

---

## 1. Request Handling (`main.py`)

The `/solve` endpoint receives:
- `prompt` — the accounting task in one of 7 languages (nb, nn, en, de, es, pt, fr)
- `files[]` — optional base64-encoded PDFs/images
- `tripletex_credentials` — `{base_url, session_token}`

A `TripletexClient` is created and monkey-patched to track all API calls for logging.

## 2. File Processing (`file_processing/processor.py`)

```
files[] ──► For each file:
            ├── PDF? ──► pdfplumber (text + tables) ──► pdf_texts[]
            │            └── Empty text? ──► Send as image Part to Gemini Vision
            ├── Image? ──► google.genai.types.Part ──► image_parts[]
            └── Other? ──► UTF-8 decode ──► pdf_texts[]

Output: context = prompt + "\n--- Extracted file content ---\n" + pdf_texts
```

## 3. Two-Stage LLM Classification (`llm/classifier.py`)

### Stage 1: Classification

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` |
| Temperature | 0.0 |
| Output | JSON `{"task_type": "..."}` |
| System prompt | `CLASSIFY_PROMPT` — task type definitions + disambiguation rules |

33 task types across 3 tiers (see [Task Types](#task-types) below).

### Stage 2: Entity Extraction

| Property | Value |
|----------|-------|
| Model | `gemini-3-flash-preview` (text) or `gemini-3.1-pro-preview` (with files) |
| Temperature | 0.0 |
| Output | JSON with extracted entities |
| System prompt | Task-specific `EXTRACT_PROMPTS[task_type]` |

Post-processing:
- Unwrap single-item arrays for non-multi types
- Unwrap nested `"entities"` keys (LLM double-wrapping)
- Sanitize dates (validate `YYYY-MM-DD`, null if invalid)

Output: `TaskPlan(task_type, entities)`

## 4. Context Enrichment (`main.py:87-97`)

Before dispatching to a handler:

1. **Inject metadata** — `_original_prompt`, `_has_files` into entities
2. **Lightweight account scan** (`handlers/account_scanner.py`) — task-specific GETs:
   - `create_employee` → departments, employees
   - `create_invoice` → customers, products, payment types
   - `create_project` → customers, employees
   - `run_payroll` → employees, salary types
   - etc.
3. **Routing decision**:
   - `use_smart = true` if task_type in `{ledger_correction, bank_reconciliation, unknown}` OR (has files AND task_type not in `{create_employee, create_supplier_invoice, create_voucher, create_invoice, year_end_closing}`)

## 5. Handler Dispatch

Three execution paths based on the routing decision:

### Path A: Deterministic Handlers (33 types)

Looked up from `REGISTRY[task_type]`. Each handler extends `BaseHandler` and implements `execute(plan)`.

### Path B: Smart Planner (`handlers/smart_planner.py`)

Used for complex/file-based tasks where hardcoded logic fails:

```
1. ensure_bank_account (PUT account 1920)
2. Gather full context via free GETs:
   ├── GET /department
   ├── GET /employee
   ├── GET /customer
   ├── GET /invoice (+ highlight overdue)
   ├── GET /ledger/voucher (+ postings for corrections)
   ├── GET /invoice/paymentType
   ├── GET /ledger/account?number=1920
   └── GET /ledger/posting (for cost_analysis/ledger_correction)
3. Ask Gemini to plan minimum write operations
   (uses ACCOUNTING_EXPERT_PROMPT, ~5K tokens, not full 70K spec)
4. Execute planned operations sequentially:
   ├── Auto-fix common path errors (/voucher → /ledger/voucher)
   ├── Fix field name errors ("vendor" → "supplier")
   ├── Resolve account numbers → IDs via cached GETs
   ├── Replace placeholder IDs from previous operation results
   └── 240s time limit
```

### Path C: Agentic Handler (`handlers/agentic.py`)

Fallback for `unknown` task types or handler recovery:

```
Multi-turn conversation with Gemini:
├── System prompt: API_REFERENCE + ACCOUNTING_KNOWLEDGE
├── Up to 15 steps, 240s time limit
├── Each step: Gemini returns JSON action:
│   ├── {"action": "api_call", "method": "POST", "path": "...", "body": {...}}
│   └── {"action": "done"}
├── Results (success or error) fed back for next decision
└── Self-correcting: errors shown to Gemini to parse and retry
```

## 6. Error Recovery (`main.py:116-132`)

If a deterministic handler throws an exception:

1. Error is logged
2. `AgenticHandler` is invoked in **recovery mode** with:
   - `_handler_error` — the original exception message
   - `_partial_context` — note that some API calls may already have been made
3. Gemini tries to complete remaining steps

## 7. Response & Logging

Every request logs a `SUBMISSION_SUMMARY` JSON:

```json
{
  "prompt": "...",
  "files": 0,
  "task_type": "create_invoice",
  "entities": {...},
  "api_calls": 5,
  "api_detail": ["POST /customer", "POST /order", ...],
  "elapsed_s": 3.2,
  "status": "ok",
  "error": null
}
```

Always returns `{"status": "completed"}` (HTTP 200).

---

## Task Types

### Tier 1 — Basic CRUD

| Task Type | Handler | Description |
|-----------|---------|-------------|
| `create_employee` | `CreateEmployeeHandler` | Employee + department + employment + optional admin entitlements |
| `update_employee` | `UpdateEmployeeHandler` | Search by name, update fields |
| `create_customer` | `CreateCustomerHandler` | Also handles suppliers via `/customer` endpoint |
| `update_customer` | `UpdateCustomerHandler` | Search by name, update fields |
| `create_product` | `CreateProductHandler` | Single or batch, with pricing and VAT |
| `update_product` | `UpdateProductHandler` | Search by name, update fields |
| `create_department` | `CreateDepartmentHandler` | Single or batch |
| `update_department` | `UpdateDepartmentHandler` | Search by name, update fields |
| `enable_module` | `EnableModuleHandler` | Enable Tripletex modules |
| `create_invoice` | `CreateInvoiceHandler` | Customer -> order -> invoice -> optional payment + email |
| `create_order` | `CreateInvoiceHandler` | Same handler as invoice |
| `create_project` | `CreateProjectHandler` | Project with customer + project manager |
| `update_project` | `UpdateProjectHandler` | Search by name, update fields |

### Tier 2 — Business Operations

| Task Type | Handler | Description |
|-----------|---------|-------------|
| `register_payment` | `RegisterPaymentHandler` | Find unpaid invoice, register payment |
| `create_credit_note` | `CreateCreditNoteHandler` | Find/create invoice, issue credit note |
| `project_invoice` | `ProjectInvoiceHandler` | Project + timesheet + invoice + payment |
| `create_travel_expense` | `CreateTravelExpenseHandler` | Travel details + costs + mileage + per diem |
| `update_travel_expense` | `UpdateTravelExpenseHandler` | Find and update travel expense |
| `delete_travel_expense` | `DeleteTravelExpenseHandler` | Find and delete travel expense |
| `register_timesheet` | `RegisterTimesheetHandler` | Employee + project + activity + hours |
| `run_payroll` | `RunPayrollHandler` | Division + employment + salary transaction |
| `reverse_payment` | `ReversePaymentHandler` | Find invoice, reverse with negative amount |
| `create_supplier_invoice` | `CreateSupplierInvoiceHandler` | Manual voucher with VAT splits (6590/1610/2400) |
| `create_contact` | `CreateContactHandler` | Contact person linked to customer |

### Tier 3 — Complex Operations

| Task Type | Handler | Description |
|-----------|---------|-------------|
| `delete_voucher` | `DeleteVoucherHandler` | Delete or reverse voucher (prefers reverse) |
| `create_voucher` | `CreateVoucherHandler` | Manual journal entry with balanced postings |
| `overdue_invoice` | `OverdueInvoiceHandler` | Find overdue, post reminder fee, partial payment |
| `ledger_correction` | `SmartPlannerHandler` | Gemini-planned ledger error corrections |
| `currency_payment` | `CurrencyPaymentHandler` | Foreign currency with agio/disagio (8060/8160) |
| `year_end_closing` | `YearEndHandler` | Depreciation + closing entries |
| `create_accounting_dimension` | `CreateAccountingDimensionHandler` | Dimension + values + linked voucher |
| `bank_reconciliation` | `BankReconciliationHandler` | Account + period selection |
| `full_project_cycle` | `FullProjectCycleHandler` | Customer -> project -> timesheet -> supplier costs -> invoice |
| `cost_analysis` | `CostAnalysisHandler` | Analyze ledger, create projects for top expense accounts |
| `unknown` | `AgenticHandler` | Gemini multi-turn fallback |

---

## BaseHandler Auto-Fix Layer (`handlers/base.py`)

Both `TripletexClient` and `BaseHandler` attempt to self-heal failed requests:

| Norwegian Error Message | Fix Type | Action |
|------------------------|----------|--------|
| "Feltet ma fylles ut" | `required_field` | Set sensible default |
| "Kan ikke vaere null" | `required_field` | Set sensible default |
| "er i bruk" | `duplicate` | Append "-2" suffix |
| "Finnes fra for" | `duplicate` | Append "-2" suffix |
| "eksisterer ikke i objektet" | `remove_field` | Remove invalid field |
| "Ugyldig" | `invalid_value` | Remove invalid field |
| "Brukertype kan ikke" | `needs_usertype` | Set userType=EXTENDED |

`TripletexClient.post()` additionally strips `null` values from bodies before sending.

---

## LLM Knowledge Modules

| Module | Size | Used By | Purpose |
|--------|------|---------|---------|
| `prompts.py` | ~80 lines | (unused, original single-stage) | System prompt with all task types |
| `classifier.py` | ~320 lines | main.py | Two-stage classify + extract pipeline |
| `accounting_knowledge.py` | ~100 lines | AgenticHandler | Norwegian accounting rules, VAT rates, chart of accounts |
| `accounting_expert.py` | ~130 lines (~5K) | SmartPlannerHandler | Expert prompt for planning writes |
| `api_reference.py` | ~100 lines | AgenticHandler | Concise API reference |
| `full_api_spec.py` | ~600 lines (~70K) | (imported but too slow) | Complete Tripletex API specification |
| `examples.py` | ~50 lines | workflow.sh cycle | Few-shot examples loader |
| `schemas.py` | ~50 lines | everywhere | TaskType enum + TaskPlan model |

---

## Infrastructure

### Deployment

```
Dockerfile: python:3.11-slim + uvicorn on :8080
Deploy:     gcloud run deploy tripletex-agent --source . --region europe-north1
Config:     2Gi memory, 2 CPU, 300s timeout, min 1 instance, unauthenticated
Env vars:   GOOGLE_API_KEY
```

### Dependencies

```
fastapi, uvicorn, httpx, google-genai, pydantic, pdfplumber
```

### Operations (`workflow.sh`)

| Command | Action |
|---------|--------|
| `./workflow.sh pull` | Pull GCP logs, parse into `submissions.json`, show failure analysis |
| `./workflow.sh deploy` | Deploy to Cloud Run |
| `./workflow.sh cycle` | Pull + analyze success rates + deploy |
| `./workflow.sh status` | Per-task-type success rate table |
| `./workflow.sh tail` | Live log stream |
| `./workflow.sh test` | Run sandbox integration tests |

### Test Suites

| File | Purpose |
|------|---------|
| `tests/accounting_test_suite.py` | Direct Tripletex sandbox API integration tests |
| `tests/generate_test_prompts.py` | Gemini generates 20 multilingual prompts, tests classification |
| `tests/stress_test.py` | 50-200 generated prompts through full pipeline |
| `tests/test_prompts_1000.py` | 1000 template-based classification tests |

---

## Key Architecture Decisions

1. **Two-stage LLM pipeline** — cheap classification first, then task-specific extraction with a tailored prompt. Vision model only when files are present.

2. **Three execution paths** — deterministic handlers (fast, reliable), Smart Planner (Gemini-planned for complex tasks), Agentic fallback (multi-turn for unknowns).

3. **Defense in depth** — if a handler crashes, AgenticHandler takes over with partial context + error injected.

4. **API cost optimization** — GETs are free in competition scoring, so the system pre-fetches aggressively. Only writes count.

5. **Auto-fix layer** — both `TripletexClient` and `BaseHandler` parse Norwegian Tripletex error messages and self-heal 422s.

6. **7-language support** — classification and extraction prompts handle nb, nn, en, de, es, pt, fr with explicit multilingual examples in the system prompts.
