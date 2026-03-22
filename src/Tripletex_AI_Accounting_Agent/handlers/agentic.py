"""Fallback agentic handler — lets Gemini plan and execute API calls step by step."""
import json
import logging
import time

from google import genai
from google.genai import types

from config import GOOGLE_API_KEY, GEMINI_MODEL
from handlers.base import BaseHandler
from handlers.invoice import ensure_bank_account
from llm.schemas import TaskPlan
from llm.api_reference import API_REFERENCE
from llm.accounting_knowledge import ACCOUNTING_KNOWLEDGE

logger = logging.getLogger("handler.agentic")

MAX_STEPS = 15
MAX_TIME_S = 240  # 4 min safety margin within 5 min timeout

AGENT_SYSTEM_PROMPT = """You are an AI accounting agent executing Tripletex API calls to complete an accounting task.

You will be given a task prompt and must plan and execute API calls step by step.
After each call, you'll see the result and decide the next action.

""" + ACCOUNTING_KNOWLEDGE + """
""" + API_REFERENCE + """

## How to respond

Return a JSON object with one of these actions:

1. **Make an API call:**
{"action": "api_call", "method": "GET|POST|PUT|DELETE", "path": "/endpoint/path", "params": {}, "body": {}, "reasoning": "why this call"}

2. **Task is complete:**
{"action": "done", "reasoning": "what was accomplished"}

## Rules
- Authentication is handled automatically (Basic Auth with session token)
- Use the base_url from credentials for all calls
- After POST, the response contains the created entity with its ID — use it for subsequent calls
- Parse error messages and fix the issue in one retry
- For invoicing: set bank account on 1920 first, then customer → order → invoice
- For employees: need userType=EXTENDED and department.id
- For admin role: PUT /employee/entitlement/:grantEntitlementsByTemplate?employeeId=X&template=ALL_PRIVILEGES
- invoiceDueDate should be 14 days after invoiceDate
- Product numbers may already exist — search first with GET /product?number=X
- Travel expense dates go inside travelDetails, not top level
- PUT /invoice/{id}/:payment uses query params, not JSON body
"""


class AgenticHandler(BaseHandler):
    """Fallback handler that uses Gemini to plan and execute API calls."""

    async def execute(self, plan: TaskPlan) -> None:
        start = time.time()
        client = genai.Client(api_key=GOOGLE_API_KEY)

        # Ensure bank account for any invoicing tasks
        try:
            await ensure_bank_account(self.client)
        except Exception:
            pass

        # Build initial context — handle both dict and list entities safely
        ents = plan.entities if isinstance(plan.entities, dict) else {"data": plan.entities}
        partial_context = ents.get("_partial_context", "")
        recovery_note = f"\n\n## RECOVERY MODE:\n{partial_context}\n" if partial_context else ""
        original_prompt = ents.get("_original_prompt", json.dumps(ents, ensure_ascii=False, default=str))
        clean_ents = {k: v for k, v in ents.items() if not str(k).startswith("_")} if isinstance(ents, dict) else ents

        conversation = [
            f"## Task to complete:\n{original_prompt}\n\n"
            f"## Task type hint: {plan.task_type.value}\n"
            f"## Extracted entities: {json.dumps(clean_ents, ensure_ascii=False, default=str)}\n"
            f"{recovery_note}\n"
            f"Plan and execute the API calls needed. Start with the first call."
        ]

        for step in range(MAX_STEPS):
            elapsed = time.time() - start
            if elapsed > MAX_TIME_S:
                logger.warning(f"Agentic: time limit reached after {step} steps ({elapsed:.0f}s)")
                break

            # Ask Gemini for next action
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents="\n\n".join(conversation),
                    config=types.GenerateContentConfig(
                        system_instruction=AGENT_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                action = json.loads(response.text)
            except Exception as e:
                logger.error(f"Agentic: Gemini call failed: {e}")
                break

            logger.info(f"Agentic step {step+1}: {action.get('action')} — {action.get('reasoning', '')[:80]}")

            if action.get("action") == "done":
                logger.info(f"Agentic: completed in {step+1} steps")
                break

            if action.get("action") != "api_call":
                logger.warning(f"Agentic: unknown action {action.get('action')}")
                break

            # Execute the API call
            method = action.get("method", "GET").upper()
            path = action.get("path", "")
            params = action.get("params")
            body = action.get("body")

            try:
                if method == "GET":
                    result = await self.client.get(path, params=params)
                    result_str = json.dumps(result, ensure_ascii=False, default=str)[:1000]
                elif method == "POST":
                    result = await self.client.post(path, body or {})
                    result_str = json.dumps(result, ensure_ascii=False, default=str)[:1000]
                elif method == "PUT":
                    result = await self.client.put(path, body or {}, params=params)
                    result_str = json.dumps(result, ensure_ascii=False, default=str)[:1000]
                elif method == "DELETE":
                    await self.client.delete(path)
                    result_str = '{"status": "deleted"}'
                else:
                    result_str = f'{{"error": "Unknown method {method}"}}'

                conversation.append(
                    f"## Step {step+1} result:\n"
                    f"**{method} {path}** → SUCCESS\n"
                    f"```json\n{result_str}\n```\n"
                    f"What's the next step?"
                )
                logger.info(f"Agentic: {method} {path} → ok")

            except Exception as e:
                error_str = str(e)[:500]
                conversation.append(
                    f"## Step {step+1} result:\n"
                    f"**{method} {path}** → ERROR\n"
                    f"```\n{error_str}\n```\n"
                    f"Parse the error and decide: fix and retry, or try a different approach?"
                )
                logger.warning(f"Agentic: {method} {path} → error: {error_str[:100]}")

        elapsed = time.time() - start
        logger.info(f"Agentic handler finished in {elapsed:.1f}s")
