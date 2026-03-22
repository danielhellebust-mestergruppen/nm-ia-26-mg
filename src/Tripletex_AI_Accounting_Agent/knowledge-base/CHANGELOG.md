# Knowledge Base Changelog

All updates to the knowledge base are logged here with timestamps.

## 2026-03-21T15:00 CET - Update 10: Cloudflare Tunnel timeout warning + scoring clarification

### 05-examples.md
- **IMPORTANT: Cloudflare Tunnel has a hard 120-second timeout.** Tasks can take up to 300 seconds (5 min), so longer tasks WILL fail through Cloudflare. **ngrok is now recommended** as the primary option for local HTTPS exposure.
- Not relevant for us (we deploy to Cloud Run), but good to know for debugging.

### 04-scoring.md
- **Added missing sentence:** "Normalization only affects the efficiency bonus — your correctness score never decreases." This confirms that efficiency benchmark recalculations (every 12h) can only affect the bonus portion, never reduce correctness scores.

### Other pages (01-overview, 02-endpoint, 03-sandbox)
- Minor editorial/wording changes only (title formatting, active vs passive voice). No substantive content changes. KB files retain extra useful context (actual proxy URL, competition timeline, auth details) not present on live pages.

## 2026-03-21T09:00 CET - Update 9: CRITICAL scoring clarification — GETs are FREE

### 04-scoring.md
- **CRITICAL DISCOVERY:** Call efficiency only counts **write calls (POST, PUT, DELETE, PATCH)**. **GET requests are NOT counted!**
- "GET requests are not counted — read as much as you need to understand the data."
- Error cleanliness also only counts **write call** errors
- **Impact:** We can freely use GETs to read/verify data, query existing entities, explore accounts — all without penalty. Only minimize POST/PUT/DELETE calls.

## 2026-03-20T17:00 CET - Update 8: Rate limits back to 10/3

### 04-scoring.md
- Rate limits back to 10/3 (verified/unverified). Tiers now show "open" again. Page seems to fluctuate.

## 2026-03-20T16:00 CET - Update 7: Rate limits reverted, page reset

### 04-scoring.md
- **Rate limits reverted:** Back to 4/2 (was 10/3). Tier schedule text also reverted to "opens early Friday" but Tier 2 tasks ARE still being assigned. Page may have been reset/redeployed.
- NOTE: Actual behavior unchanged — Tier 2 tasks confirmed active from live submissions.

## 2026-03-20T13:00 CET - Update 6: Rate limits INCREASED

### 04-scoring.md
- **Rate limits raised:** Verified teams per task per day: **4 → 10**. Unverified: **2 → 3**.
- With 30 tasks, verified teams now get 300 submissions/day (was 120). Much more room for iteration.

## 2026-03-20T12:00 CET - Update 5: Tier 1 and Tier 2 both confirmed OPEN

### 04-scoring.md
- Tier 1 changed from "available from competition start" → **"open"**
- Tier 2 confirmed **"open"** (previously caught in update 4)
- Tier 3 still "opens early Saturday"
- Tier 2 tasks (×2 multiplier) now live: invoice with payment, credit notes, project billing

## 2026-03-20T10:30 CET - Update 4: Tier 2 is OPEN

### 04-scoring.md
- **CRITICAL: Tier 2 is now open!** Changed from "opens early Friday. Check this page for updates." → "open"
- Tier 2 tasks: invoice with payment, credit notes, project billing (×2 multiplier)
- Tier 3 still says "opens early Saturday"

## 2026-03-20T01:00 CET - Update 3: Rate limit reduced

### 04-scoring.md
- **CHANGED:** Verified teams rate limit per task per day reduced from **5 → 4**. Unverified unchanged at 2.

## 2026-03-19T22:30 CET - Update 2: Examples page expanded

Only `05-examples.md` changed. Overview, endpoint, sandbox, scoring pages unchanged.

### 05-examples.md
- **NEW: "Common Errors" table** — 5-row table (Error/Cause/Fix) replacing the old bullet list. Adds two new entries: "Empty `values` array" (no results found) and "Timeout (5 min)" (agent too slow)
- **CRITICAL NEW TIP: "Some tasks require enabling modules first (e.g., department accounting)"** — department tasks may fail without module activation
- **NEW TIP:** `?fields=*` to discover all available fields on any entity
- **NEW:** Language codes listed explicitly: nb, en, es, pt, nn, de, fr
- **RESTRUCTURED:** "Key Constraints" + "Optimization Strategies" merged into clearer "Tips" and "Optimizing for Efficiency" sections

## 2026-03-19T21:30 CET - Update 1: Documentation enrichment across all pages

All 5 source pages had new content compared to initial fetch. Changes by file:

### 01-overview.md
- **NEW:** "Quick Start" section with 5 steps including submit URL (`https://app.ainm.no/submit/tripletex`)
- **NEW:** API documentation link: `https://kkpqfuj-amager.tripletex.dev/v2-docs/`
- **NEW:** "Files" row in key facts table (some tasks include PDF/image attachments)
- **NEW:** Explicit note: "Each submission gets a brand new Tripletex account"

### 02-endpoint-spec.md (major update)
- **NEW:** Real example prompt in request JSON: `"Opprett en ansatt med navn Ola Nordmann, ola@example.org. Han skal være kontoadministrator."`
- **NEW:** Proxy URL revealed: `https://tx-proxy.ainm.no/v2`
- **NEW:** Detailed field descriptions table for the request schema (7 fields documented)
- **NEW:** "Requirements" section (HTTPS, 5-min timeout, status response, proxy requirement)
- **NEW:** "API Tips" section (fields param, pagination, DELETE path pattern, response wrapping)
- **NEW:** Full auth code example with `requests.get` call

### 03-sandbox.md
- **NEW:** "What You Can Do" section (4 sandbox use cases)
- **EXPANDED:** "Logging Into the Web UI" now has 4 detailed steps (was 3 brief bullets)
- **EXPANDED:** "Getting Your Sandbox" now lists what you receive (UI URL, API base URL, session token)

### 04-scoring.md (critical strategy info)
- **CRITICAL:** Tier task examples now explicitly listed in Task Assignment:
  - Tier 1: create employee, create customer, **create invoice**
  - Tier 2: invoice with payment, credit notes, project billing
  - Tier 3: bank reconciliation from CSV, error correction in ledger, year-end closing
- **NOTE:** "create invoice" appears as Tier 1 in task assignment but Tier 2 in the multiplier table — ambiguous
- **NEW:** "The efficiency bonus only applies to perfect submissions"
- **EXPANDED:** Task Assignment section with variant info (56 = 7 languages × 8 data sets)
- **EXPANDED:** Best Score section with 4 detailed bullet points

### 05-examples.md
- **NEW:** Task Patterns API flow TABLE showing exact endpoint sequences:
  - Create with linking: GET /customer → POST /order → POST /invoice
  - Register payment: POST /customer → POST /invoice → POST /payment (no order step!)
  - Delete/reverse: GET → DELETE pattern
- **NEW:** "Key Constraints" section (empty accounts, UTF-8 æøå, proxy logging, 7 languages)
- **EXPANDED:** Optimization section with 5 specific tips

## 2026-03-19T18:00 CET - Initial Creation

- Created `01-overview.md` - Challenge overview, task categories, specifications
- Created `02-endpoint-spec.md` - /solve endpoint schema, API endpoints, auth details
- Created `03-sandbox.md` - Sandbox setup, URLs, code examples, differences vs competition
- Created `04-scoring.md` - Scoring formula, tiers, efficiency bonus, rate limits
- Created `05-examples.md` - FastAPI template, API code examples, implementation guide
- Created `06-quick-reference.md` - Quick reference card with all key info at a glance
- Source URLs:
  - https://app.ainm.no/docs/tripletex/overview
  - https://app.ainm.no/docs/tripletex/sandbox
  - https://app.ainm.no/docs/tripletex/endpoint
  - https://app.ainm.no/docs/tripletex/scoring
  - https://app.ainm.no/docs/tripletex/examples
