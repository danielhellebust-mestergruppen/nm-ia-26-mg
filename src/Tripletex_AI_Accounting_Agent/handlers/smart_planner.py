"""Smart planner: Give Gemini full context and let IT plan the API writes.
For complex/PDF tasks where hardcoding fails. Uses free GETs liberally,
then asks Gemini to plan the minimum writes needed."""
import json
import logging
import time
from datetime import date

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_MODEL_VISION
from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan
from llm.full_api_spec import FULL_API_SPEC
from llm.accounting_expert import ACCOUNTING_EXPERT_PROMPT

logger = logging.getLogger("handler.smart_planner")

# Full API spec (70K) makes Gemini too slow (5 min+). Use accounting expert only (5K).
PLANNER_PROMPT = ACCOUNTING_EXPERT_PROMPT


class SmartPlannerHandler(BaseHandler):
    """Let Gemini plan the exact API writes based on full context."""

    async def execute(self, plan: TaskPlan) -> None:
        start = time.time()
        e = plan.entities if isinstance(plan.entities, dict) else {"data": plan.entities}

        # Ensure bank account is set up for invoice-related tasks
        try:
            await ensure_bank_account(self.client)
        except Exception:
            pass

        # Gather context (all GETs are free)
        context_parts = []

        # 1. Original prompt + file content
        original_prompt = e.get("_original_prompt", json.dumps(e, ensure_ascii=False, default=str))
        context_parts.append(f"## TASK:\n{original_prompt}")

        # 2. Extracted entities
        clean_ents = {k: v for k, v in e.items() if not str(k).startswith("_")}
        context_parts.append(f"## EXTRACTED DATA:\n{json.dumps(clean_ents, ensure_ascii=False, default=str)}")

        # 3. Account state from free GETs
        account_info = []
        logger.info("Smart planner: gathering account context (GETs are free)")
        try:
            # Departments
            r = await self.client.get("/department", params={"fields": "id,name", "count": 10})
            account_info.append(f"Departments: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        try:
            # Existing employees
            r = await self.client.get("/employee", params={"fields": "id,firstName,lastName,email", "count": 10})
            account_info.append(f"Employees: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        try:
            # Existing customers
            r = await self.client.get("/customer", params={"fields": "id,name,organizationNumber", "count": 10})
            account_info.append(f"Customers: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        try:
            # Existing invoices — get all with outstanding amounts for overdue detection
            r = await self.client.get("/invoice", params={
                "invoiceDateFrom": "2026-01-01", "invoiceDateTo": "2026-12-31",
                "fields": "id,invoiceNumber,invoiceDate,invoiceDueDate,amount,amountOutstanding,amountCurrency,customer",
                "count": 50,
            })
            invoices = r.get("values", [])
            account_info.append(f"Invoices: {json.dumps(invoices)}")
            # Highlight overdue invoices
            overdue = [inv for inv in invoices if inv.get("amountOutstanding", 0) > 0 and inv.get("invoiceDueDate", "9999") < date.today().isoformat()]
            if overdue:
                account_info.append(f"OVERDUE invoices (past due date with outstanding balance): {json.dumps(overdue)}")
        except Exception:
            pass

        try:
            # Existing vouchers — include postings for ledger correction
            vfields = "id,number,date,description"
            if plan.task_type.value in ("ledger_correction",):
                vfields = "id,number,date,description,postings(id,account,amountGross,description)"
            r = await self.client.get("/ledger/voucher", params={
                "dateFrom": "2026-01-01", "dateTo": "2026-12-31",
                "fields": vfields, "count": 50,
            })
            account_info.append(f"Vouchers: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        try:
            # Payment types (needed for overdue invoice, bank reconciliation)
            r = await self.client.get("/invoice/paymentType", params={
                "fields": "id,description", "count": 10,
            })
            account_info.append(f"Payment types: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        try:
            # Bank account
            r = await self.client.get("/ledger/account", params={
                "number": "1920", "fields": "id,number,bankAccountNumber", "count": 1,
            })
            account_info.append(f"Bank 1920: {json.dumps(r.get('values', []))}")
        except Exception:
            pass

        # For cost analysis / ledger tasks: gather ledger postings by account
        if plan.task_type.value in ("cost_analysis", "ledger_correction", "full_project_cycle"):
            try:
                r = await self.client.get("/ledger/posting", params={
                    "dateFrom": "2026-01-01", "dateTo": "2026-02-28",
                    "fields": "id,date,description,amount,account",
                    "count": 100,
                })
                postings = r.get("values", [])
                # Summarize by account for cost analysis
                from collections import defaultdict
                by_account = defaultdict(lambda: {"jan": 0, "feb": 0, "name": ""})
                for p in postings:
                    acc = p.get("account", {})
                    num = acc.get("number", 0)
                    name = acc.get("name", "")
                    amt = p.get("amount", 0)
                    d = p.get("date", "")
                    if 4000 <= num <= 7999:  # Expense accounts
                        if d and d[:7] == "2026-01":
                            by_account[num]["jan"] += amt
                        elif d and d[:7] == "2026-02":
                            by_account[num]["feb"] += amt
                        by_account[num]["name"] = name
                summary = {k: v for k, v in by_account.items()}
                account_info.append(f"Expense postings by account (Jan vs Feb): {json.dumps(summary)}")
            except Exception:
                pass

        context_parts.append(f"## CURRENT ACCOUNT STATE:\n" + "\n".join(account_info))

        # 4. Task type hint
        context_parts.append(f"## TASK TYPE: {plan.task_type.value}")
        context_parts.append("## Plan the minimum WRITE operations needed. Return JSON array.")

        # Ask Gemini to plan
        gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
        model = GEMINI_MODEL_VISION if e.get("_has_files") else GEMINI_MODEL

        full_context = "\n\n".join(context_parts)
        logger.info(f"Smart planner: asking Gemini to plan writes (model={model}, context={len(full_context)} chars)")

        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=full_context,
                config=types.GenerateContentConfig(
                    system_instruction=PLANNER_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            raw = response.text
            logger.info(f"Smart planner: Gemini response: {raw[:300]}")
            operations = json.loads(raw)
        except Exception as ex:
            logger.error(f"Smart planner: Gemini planning failed: {ex}")
            return

        if not isinstance(operations, list):
            operations = [operations]

        logger.info(f"Smart planner: {len(operations)} write operations planned")

        # Execute planned operations
        for i, op in enumerate(operations):
            method = op.get("method", "POST").upper()
            path = op.get("path", "")
            body = op.get("body", {})
            reasoning = op.get("reasoning", "")
            params = op.get("params")

            # Fix common path errors from Gemini
            path_fixes = {
                "/voucher": "/ledger/voucher",
                "/account": "/ledger/account",
                "/posting": "/ledger/posting",
                "/vatType": "/ledger/vatType",
                "/paymentType": "/invoice/paymentType",
            }
            for wrong, correct in path_fixes.items():
                if path == wrong:
                    logger.info(f"Smart planner: fixed path {wrong} → {correct}")
                    path = correct
                    break

            elapsed = time.time() - start
            if elapsed > 240:
                logger.warning(f"Smart planner: time limit, stopping at op {i+1}")
                break

            logger.info(f"Smart planner op {i+1}: {method} {path} — {reasoning[:60]}")

            # Fix common field name errors from Gemini
            body_str = json.dumps(body)
            if '"vendor"' in body_str:
                body_str = body_str.replace('"vendor"', '"supplier"')
                body = json.loads(body_str)
            if '"customer_id"' in body_str:
                body_str = body_str.replace('"customer_id"', '"customer"')
                body = json.loads(body_str)

            # Resolve account numbers to IDs in the body (Gemini uses numbers, API needs IDs)
            body = await self._resolve_account_refs(body)

            try:
                if method == "POST":
                    result = await self.client.post(path, body)
                elif method == "PUT":
                    params = op.get("params")
                    result = await self.client.put(path, body, params=params)
                elif method == "DELETE":
                    await self.client.delete(path)
                    result = {}
                else:
                    logger.warning(f"Unknown method: {method}")
                    continue

                # If we need an ID from this result for the next operation, Gemini can't predict it.
                # Store the result for potential reference.
                if isinstance(result, dict) and "value" in result:
                    created_id = result["value"].get("id")
                    if created_id:
                        # Replace placeholder IDs in remaining operations
                        placeholder = op.get("result_id_placeholder")
                        if placeholder:
                            for future_op in operations[i+1:]:
                                future_body = json.dumps(future_op.get("body", {}))
                                if placeholder in future_body:
                                    future_op["body"] = json.loads(
                                        future_body.replace(placeholder, str(created_id))
                                    )
                                future_path = future_op.get("path", "")
                                if placeholder in future_path:
                                    future_op["path"] = future_path.replace(placeholder, str(created_id))

                logger.info(f"Smart planner op {i+1}: success")

            except Exception as ex:
                logger.warning(f"Smart planner op {i+1} failed: {ex}")
                # Read the error and let Gemini know (for potential retry logic)
                # For now, just continue with remaining operations

        logger.info(f"Smart planner: completed {len(operations)} operations in {time.time()-start:.1f}s")

    async def _resolve_account_refs(self, body: dict) -> dict:
        """Resolve account references by number to IDs. Gemini plans with numbers, API needs IDs."""
        if not isinstance(body, dict):
            return body

        # Cache lookups
        if not hasattr(self, '_account_cache'):
            self._account_cache = {}

        async def resolve_account(obj):
            if isinstance(obj, dict):
                # Check if this is an account ref with number but no id
                if "account" in obj and isinstance(obj["account"], dict):
                    acc = obj["account"]
                    if "number" in acc and "id" not in acc:
                        num = str(acc["number"])
                        if num not in self._account_cache:
                            try:
                                r = await self.client.get("/ledger/account", params={
                                    "number": num, "fields": "id,number", "count": 1,
                                })
                                vals = r.get("values", [])
                                if vals:
                                    self._account_cache[num] = vals[0]["id"]
                            except Exception:
                                pass
                        if num in self._account_cache:
                            obj["account"] = {"id": self._account_cache[num]}

                # Recurse into nested dicts and lists
                for key, val in obj.items():
                    if isinstance(val, dict):
                        await resolve_account(val)
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                await resolve_account(item)

        await resolve_account(body)
        return body
