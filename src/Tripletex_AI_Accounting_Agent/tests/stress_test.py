"""
High-volume end-to-end stress test.
Generates realistic prompts via Gemini, runs them through the full pipeline
(LLM classification → handler → Tripletex sandbox), and reports results.

Usage:
    python3 tests/stress_test.py              # 50 tests
    python3 tests/stress_test.py --count 200  # 200 tests
"""
import asyncio
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from google.genai import types
from config import GOOGLE_API_KEY
from llm.client import classify_and_extract
from tripletex_client.client import TripletexClient
from handlers.registry import REGISTRY

logging.basicConfig(level="WARNING", format="%(name)s: %(message)s")
logger = logging.getLogger("stress")
logger.setLevel("INFO")

BASE_URL = "https://kkpqfuj-amager.tripletex.dev/v2"
TOKEN = "eyJ0b2tlbklkIjoyMTQ3NjQ1OTIyLCJ0b2tlbiI6Ijg4ZWZhMDhmLWE1YTQtNDQ1NS05ZTI0LTg0MGUwYjJjMmQ2OCJ9"

BATCH_PROMPT = """Generate {count} realistic Tripletex accounting task prompts for an AI agent competition.

## Available Tripletex API Endpoints
The agent can use these endpoints:
- POST /employee (firstName, lastName, email, userType, department.id) + PUT /employee/entitlement for admin role
- POST /customer (name, email, organizationNumber, isCustomer, postalAddress)
- POST /supplier (name, email, organizationNumber) — separate endpoint for pure suppliers
- POST /product (name, number, priceExcludingVatCurrency, vatType.id)
- POST /department (name, departmentNumber)
- POST /project (name, startDate, customer.id, projectManager.id)
- POST /order + POST /invoice (customer → order with orderLines → invoice)
- PUT /invoice/:payment (register payment with paymentDate, paymentTypeId, paidAmount)
- PUT /invoice/:createCreditNote (reverse an invoice)
- POST /travelExpense (employee.id, title, travelDetails.departureDate/returnDate) + POST /travelExpense/cost
- POST /timesheet/entry (employee.id, date, hours, activity.id, project.id)
- POST /salary/transaction OR manual voucher on 5000-series accounts for payroll
- POST /ledger/accountingDimensionName + POST /ledger/accountingDimensionValue + POST /ledger/voucher
- POST /ledger/voucher (date, description, postings with account.id, amount, row)
- POST /incomingInvoice (supplier invoice with vendorId, orderLines)
- POST /bank/reconciliation (account.id, accountingPeriod.id)
- PUT /ledger/voucher/:reverse (reverse a voucher)

## Task Types to Generate (mix evenly)
1. create_employee — with admin role, DOB, email. Sometimes multiple employees.
2. create_customer — with org number, address, email. Sometimes multiple customers.
3. create_product — with product number, price, VAT rate (25%/15%/12%/0%). Sometimes multiple.
4. create_department — single or multiple (2-3 departments).
5. create_invoice — single line or multi-line (2-4 products with product numbers like "4449"). Include "create and send". Some with payment registration.
6. register_payment — customer has pending invoice, register full payment.
7. reverse_payment — payment was returned by bank, reverse it. Invoice ALREADY EXISTS.
8. create_credit_note — customer complained, create credit note to reverse invoice.
9. create_project — linked to customer, with project manager, start/end dates.
10. project_invoice — register X hours for employee on activity in project, then invoice. Include hourly rate.
11. create_travel_expense — with departure/return dates, destination, per diem (4 dager, dagsats 800 kr), costs (flight, taxi, hotel).
12. delete_travel_expense — delete a specific travel expense.
13. register_timesheet — register X hours for employee on project/activity.
14. run_payroll — "Kjør lønn" with base salary + bonus. Mention fallback to manual voucher.
15. create_supplier_invoice — incoming invoice from supplier, with account number (6590, 6860 etc), including VAT.
16. create_accounting_dimension — create custom dimension (e.g. "Kostsenter", "Prosjekttype") with 2-3 values, then post a voucher linked to one value.
17. update_employee — change email, phone, address.
18. update_customer — change contact info.

## Rules
- Mix ALL 7 languages equally: nb, nn, en, de, es, pt, fr
- Use realistic Norwegian company names, person names, org numbers (9 digits), amounts in NOK
- Include special characters (æ, ø, å, ü, ñ, ã, é) where appropriate
- For invoices with products, include product numbers in parentheses like (4449)
- For VAT: mention "25% MVA", "15% MVA (næringsmiddel)", "0% MVA (avgiftsfri)", or "uten MVA"/"sem IVA"/"ohne MwSt"
- For payment reversals, say "returned by bank" / "returnert av banken" / "devolvido pelo banco"
- For credit notes, say "reklamert" / "complained" / "reklamiert" / "reclamado"
- For travel expenses, include duration in days, per diem rate, specific costs
- For accounting dimensions, name the dimension and 2-3 values, then a voucher with account + amount
- For payroll, include base salary + bonus amounts, mention using salary accounts (5000-series) as fallback
- Make prompts realistic — like what a Norwegian accountant would actually write

Return a JSON array of objects with: "prompt", "expected_task_type", "language"
"""


async def generate_batch(count: int) -> list[dict]:
    """Generate test prompts in batches of 30 to avoid output limits."""
    client = genai.Client(api_key=GOOGLE_API_KEY)
    all_prompts = []
    batch_size = 30

    for i in range(0, count, batch_size):
        n = min(batch_size, count - i)
        logger.info(f"Generating batch {i//batch_size + 1} ({n} prompts, {len(all_prompts)} total so far)...")
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=BATCH_PROMPT.format(count=n),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.9,
                ),
            )
            prompts = json.loads(response.text)
            all_prompts.extend(prompts)
        except Exception as e:
            logger.warning(f"Batch generation failed: {e}")

    logger.info(f"Generated {len(all_prompts)} prompts total")
    return all_prompts


async def run_single(prompt_data: dict, client: TripletexClient, index: int) -> dict:
    """Run a single test through the full pipeline."""
    prompt = prompt_data["prompt"]
    expected = prompt_data.get("expected_task_type", "?")
    lang = prompt_data.get("language", "?")

    result = {
        "index": index,
        "prompt": prompt[:200],
        "language": lang,
        "expected_type": expected,
        "actual_type": None,
        "status": "error",
        "error": None,
        "api_calls": 0,
    }

    try:
        # Step 1: Classify
        plan = await classify_and_extract(prompt)
        result["actual_type"] = plan.task_type.value
        plan.entities["_original_prompt"] = prompt

        # Step 2: Execute handler (if available)
        if plan.task_type in REGISTRY:
            handler = REGISTRY[plan.task_type](client)
            await handler.execute(plan)
            result["status"] = "ok"
        else:
            result["status"] = "no_handler"
            result["error"] = f"No handler for {plan.task_type.value}"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:100]}"

    return result


async def main():
    count = 50
    if "--count" in sys.argv:
        idx = sys.argv.index("--count")
        count = int(sys.argv[idx + 1])

    # Generate prompts
    prompts = await generate_batch(count)

    # Run tests
    client = TripletexClient(BASE_URL, TOKEN)
    results = []
    start = time.time()

    for i, p in enumerate(prompts):
        r = await run_single(p, client, i + 1)
        results.append(r)

        icon = "✓" if r["status"] == "ok" else "✗"
        type_match = "=" if r["actual_type"] == r["expected_type"] else "≠"
        err = f" | {r['error'][:50]}" if r.get("error") else ""
        logger.info(f"{icon} #{i+1:>3} [{r['language']}] {r['actual_type'] or '?':<25} {type_match} {r['expected_type']:<25}{err}")

    elapsed = round(time.time() - start, 1)

    # Save results
    out_dir = Path(__file__).parent.parent / "logs"
    out_file = out_dir / "stress-test-results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    no_handler = sum(1 for r in results if r["status"] == "no_handler")
    errors = sum(1 for r in results if r["status"] == "error")
    type_matches = sum(1 for r in results if r.get("actual_type") == r.get("expected_type"))

    logger.info(f"\n{'='*60}")
    logger.info(f"RESULTS: {ok} ok, {errors} errors, {no_handler} no handler | {elapsed}s")
    logger.info(f"Classification: {type_matches}/{len(results)} matched expected type")

    # Per-type breakdown
    from collections import Counter
    type_stats = Counter()
    type_errors = Counter()
    for r in results:
        t = r.get("actual_type", "unknown")
        type_stats[t] += 1
        if r["status"] == "error":
            type_errors[t] += 1

    logger.info(f"\nPer-type results:")
    for t_name, t_cnt in type_stats.most_common():
        t_errs = type_errors.get(t_name, 0)
        t_ok = t_cnt - t_errs
        pct = 100 * t_ok // t_cnt if t_cnt else 0
        logger.info(f"  {str(t_name):<30} {t_ok:>3}/{t_cnt} ok ({pct}%)")

    # Error details
    if errors:
        logger.info(f"\nError details:")
        for r in results:
            if r["status"] == "error":
                logger.info(f"  [{r['language']}] {r['actual_type']}: {r['error'][:80]}")

    logger.info(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
