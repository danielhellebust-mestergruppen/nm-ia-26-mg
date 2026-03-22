import json
import logging
import os
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import LOG_LEVEL
from file_processing.processor import process_files
from llm.classifier import classify_and_extract_two_stage as classify_and_extract
from tripletex_client.client import TripletexClient
from handlers.registry import REGISTRY

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agent")

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/solve")
async def solve(request: Request):
    body = await request.json()
    prompt = body["prompt"]
    files = body.get("files", [])
    creds = body["tripletex_credentials"]

    # Log raw task JSON to /tasks folder
    try:
        tasks_dir = Path("/tmp/tasks")
        tasks_dir.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        # Save without session token for safety
        log_body = {k: v for k, v in body.items() if k != "tripletex_credentials"}
        log_body["_base_url"] = creds.get("base_url", "")
        task_file = tasks_dir / f"task_{ts}.json"
        with open(task_file, "w") as f:
            json.dump(log_body, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved task to {task_file}")
    except Exception:
        pass

    start = time.time()
    task_type = "unknown"
    entities = {}
    error = None
    api_calls = []

    # Patch client to track API calls
    client = TripletexClient(creds["base_url"], creds["session_token"])
    _orig_get = client.get
    _orig_post = client.post
    _orig_put = client.put
    _orig_delete = client.delete

    async def tracked_get(path, **kw):
        api_calls.append({"method": "GET", "path": path})
        return await _orig_get(path, **kw)

    async def tracked_post(path, json_body):
        api_calls.append({"method": "POST", "path": path})
        return await _orig_post(path, json_body)

    async def tracked_put(path, json_body, **kw):
        api_calls.append({"method": "PUT", "path": path})
        return await _orig_put(path, json_body, **kw)

    async def tracked_delete(path):
        api_calls.append({"method": "DELETE", "path": path})
        return await _orig_delete(path)

    client.get = tracked_get
    client.post = tracked_post
    client.put = tracked_put
    client.delete = tracked_delete

    try:
        # Process files
        pdf_texts, image_parts = process_files(files)
        context = prompt
        if pdf_texts:
            context += "\n\n--- Extracted file content ---\n" + "\n\n".join(pdf_texts)

        # LLM: classify + extract
        task_plan = await classify_and_extract(context, image_parts)
        task_type = task_plan.task_type.value
        entities = task_plan.entities

        # Ensure entities is a dict (classifier might return list for unknown tasks)
        if not isinstance(task_plan.entities, dict):
            task_plan.entities = {"_raw": task_plan.entities}

        # Store original prompt and file info for handlers
        task_plan.entities["_original_prompt"] = context
        task_plan.entities["_has_files"] = len(files) > 0

        # Lightweight account scan — only scan what the task type needs
        from handlers.account_scanner import scan_account_light
        account_ctx = await scan_account_light(client, task_plan.task_type.value)
        task_plan.entities["_account"] = account_ctx

        # For complex/file-based tasks, use the smart planner instead of hardcoded handlers
        from handlers.smart_planner import SmartPlannerHandler
        complex_types = {"unknown"}
        # These task types have good handlers that work with files — don't override to smart planner
        file_capable_types = {"create_employee", "create_supplier_invoice", "create_voucher", "create_invoice", "year_end_closing", "bank_reconciliation"}
        use_smart = task_plan.task_type.value in complex_types or (len(files) > 0 and task_plan.task_type.value not in file_capable_types)

        # Dispatch to handler
        logger.info(f"Routing: type={task_type}, use_smart={use_smart}, files={len(files)}, in_registry={task_plan.task_type in REGISTRY}")
        if task_plan.task_type not in REGISTRY and not use_smart:
            error = f"No handler for: {task_type}"
        else:
            if use_smart:
                handler = SmartPlannerHandler(client)
                logger.info(f"Using smart planner for {task_type} (complex/file task)")
            else:
                handler = REGISTRY[task_plan.task_type](client)
            try:
                await handler.execute(task_plan)
            except Exception as handler_err:
                error = f"{type(handler_err).__name__}: {handler_err}"
                logger.error(f"Handler failed: {error}")
                logger.info("Attempting agentic recovery...")

                # Fall back to agentic mode to salvage partial points
                try:
                    from handlers.agentic import AgenticHandler
                    from llm.schemas import TaskType
                    recovery = AgenticHandler(client)
                    recovery_plan = task_plan
                    recovery_plan.entities["_handler_error"] = str(handler_err)
                    recovery_plan.entities["_partial_context"] = (
                        f"The deterministic handler for '{task_type}' failed with: {handler_err}. "
                        f"Some API calls may have already been made. "
                        f"Try to complete the remaining steps to finish the task."
                    )
                    await recovery.execute(recovery_plan)
                    error = f"RECOVERED after: {error}"
                    logger.info("Agentic recovery completed")
                except Exception as recovery_err:
                    logger.error(f"Agentic recovery also failed: {recovery_err}")

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.error(traceback.format_exc())

    elapsed = round(time.time() - start, 1)

    # Single structured summary log
    summary = {
        "prompt": prompt[:500],
        "files": len(files),
        "task_type": task_type,
        "entities": entities,
        "api_calls": len(api_calls),
        "api_detail": [f"{c['method']} {c['path']}" for c in api_calls],
        "elapsed_s": elapsed,
        "status": "ok" if not error else "error",
        "error": error,
    }
    logger.info(f"SUBMISSION_SUMMARY: {json.dumps(summary, ensure_ascii=False)}")

    return JSONResponse({"status": "completed"})
