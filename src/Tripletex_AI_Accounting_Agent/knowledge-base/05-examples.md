# Tripletex Task - Examples & Implementation Guide

**Last updated:** 2026-03-21T15:00 CET (update 3)

## Minimal /solve Endpoint (FastAPI)

```python
import base64
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.post("/solve")
async def solve(request: Request):
    body = await request.json()
    prompt = body["prompt"]
    files = body.get("files", [])
    creds = body["tripletex_credentials"]

    base_url = creds["base_url"]
    token = creds["session_token"]
    auth = ("0", token)

    for f in files:
        data = base64.b64decode(f["content_base64"])
        Path(f["filename"]).write_bytes(data)

    # TODO: Use an LLM to interpret the prompt and execute
    # the appropriate Tripletex API calls

    return JSONResponse({"status": "completed"})
```

### Setup

```bash
pip install fastapi uvicorn requests
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Expose Locally via HTTPS (for testing)

```bash
# Option 1: ngrok (recommended — no timeout issues)
ngrok http 8000

# Option 2: Cloudflare Tunnel
# ⚠️ Cloudflare Tunnel has a hard 120-second timeout.
# Tasks can take up to 300 seconds, so longer tasks WILL fail.
# Use ngrok if your agent needs more than 2 minutes per task.
npx cloudflared tunnel --url http://localhost:8000
```

## Tripletex API Examples

### List Employees

```python
resp = requests.get(
    f"{base_url}/employee",
    auth=auth,
    params={"fields": "id,firstName,lastName,email"}
)
employees = resp.json()["values"]
```

### Create Customer

```python
resp = requests.post(
    f"{base_url}/customer",
    auth=auth,
    json={
        "name": "Acme AS",
        "email": "post@acme.no",
        "isCustomer": True
    }
)
customer_id = resp.json()["value"]["id"]
```

### Create Invoice

```python
today = "2026-03-03"
resp = requests.post(
    f"{base_url}/invoice",
    auth=auth,
    json={
        "invoiceDate": today,
        "invoiceDueDate": today,
        "customer": {"id": customer_id},
        "orders": [{"id": order_id}]
    }
)
```

### Search Entity

```python
resp = requests.get(
    f"{base_url}/customer",
    auth=auth,
    params={
        "name": "Acme",
        "fields": "id,name,email",
        "count": 10
    }
)
matches = resp.json()["values"]
```

## Building an Effective Agent - 5 Core Steps

1. **Parse prompts** - Use an LLM to extract task type, entity names, field values, and relationships from prompts across 7 languages
2. **Handle file uploads** - Decode base64 files (PDFs, invoices, contracts) and extract relevant data
3. **Map to API endpoints** - Determine the correct API endpoints and call sequence
4. **Verify results** - Query back created/modified entities to confirm success
5. **Error handling** - Parse error responses for intelligent retry logic

## Common Task Patterns

| Pattern | Example | API Flow |
|---------|---------|----------|
| Single entity creation | "Create employee Ola Nordmann" | POST /employee |
| Create with linking | "Create invoice for customer" | GET /customer → POST /order → POST /invoice |
| Modify existing | "Add phone to contact" | GET /customer → PUT /customer/{id} |
| Delete/reverse | "Delete travel expense" | GET /travelExpense → DELETE /travelExpense/{id} |
| Multi-step setup | "Register payment" | POST /customer → POST /invoice → POST /payment |

**Key observations from flow table:**
- "Create with linking" uses **GET** to find existing customer (not POST) before creating order/invoice
- "Register payment" goes directly customer → invoice → payment (no order step)

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| 401 Unauthorized | Wrong auth format | Use Basic Auth with username `0` and session token as password |
| 404 Not Found | Wrong endpoint path | Check Tripletex v2 API docs for correct paths |
| 422 Validation Error | Missing required fields | Read error message specifying required fields |
| Empty `values` array | No results found | Check search parameters or try broader search |
| Timeout (5 min) | Agent too slow | Optimize API calls; reduce unnecessary requests |

Tripletex returns detailed error messages — parse them for single-attempt fixes.

## Tips

- The Tripletex sandbox starts empty — create prerequisites before invoices
- Use `?fields=*` to see all available fields on an entity
- **Some tasks require enabling modules first (e.g., department accounting)**
- Norwegian characters (æ, ø, å) work fine in API requests — send as UTF-8
- All API calls through the proxy are logged — use for debugging in submissions view
- Prompts come in 7 languages (nb, en, es, pt, nn, de, fr) — your agent should handle all

## Optimizing for Efficiency

Your score can exceed 1.0 with perfect correctness and minimal API calls. Higher-tier tasks have higher ceilings (up to 6.0 for Tier 3).

- **Plan before calling** — Parse prompts fully before making API calls; understand what needs creation/modification
- **Avoid trial-and-error** — Each 4xx error (400, 404, 422) reduces efficiency bonus; validate inputs beforehand
- **Minimize GET calls** — Don't fetch entities you don't need; you already know created resource IDs from responses
- **Batch where possible** — Some Tripletex endpoints accept lists; use instead of multiple individual calls
- **Read error messages** — If a call fails, Tripletex error messages specify exactly what's wrong; fix in one retry, not several
