# Tripletex Task - Overview

**Last updated:** 2026-03-19T21:30 CET

## Challenge Summary

Build an AI agent that completes accounting tasks in Tripletex. You receive a task prompt (in one of 7 languages), use the Tripletex API to execute it, and get scored on correctness and efficiency.

Each submission gets a brand new Tripletex account — you always start from scratch.

## How It Works (Workflow)

1. Submit your HTTPS endpoint URL on the platform
2. We provision a fresh Tripletex sandbox account (new account per submission)
3. A randomly selected accounting task is sent to your `/solve` endpoint
4. Your agent reads the prompt, optionally processes attached files (PDFs, images)
5. Your agent calls the Tripletex API via a proxy to complete the task
6. Results are verified field-by-field against expected values
7. Your score updates on the rolling leaderboard

## Key Specifications

| Specification | Value |
|---|---|
| Total tasks | 30 different accounting scenarios |
| Variants per task | 56 (7 languages x 8 datasets) |
| Languages | Norwegian, English, Spanish, Portuguese, Nynorsk, German, French |
| Timeout | 5 minutes (300 seconds) per submission |
| Score range | 0.0 (failed) — up to 6.0 (perfect Tier 3 + best efficiency) |
| API | [Tripletex v2 REST API](https://kkpqfuj-amager.tripletex.dev/v2-docs/) via authenticated proxy |
| Authentication | Basic Auth (username: `0`, password: session token) |
| Endpoint | POST `/solve` returning `{"status": "completed"}` with HTTP 200 |
| Files | Some tasks include PDF or image attachments |

## Quick Start

1. Build a `/solve` endpoint that accepts POST requests with a task prompt and Tripletex credentials
2. Use an LLM to interpret the prompt and decide which API calls to make
3. Call the Tripletex API using the provided proxy URL and session token
4. Return `{"status": "completed"}` when done
5. Submit your endpoint URL at `https://app.ainm.no/submit/tripletex`

## Task Categories

There are 7 primary categories spanning 30 tasks:

1. **Employees** - Create employees, set roles, update contact info
2. **Customers & Products** - Register customers, create products
3. **Invoicing** - Create invoices, register payments, issue credit notes
4. **Travel Expenses** - Register or delete travel expense reports
5. **Projects** - Create projects linked to customers
6. **Corrections** - Delete or reverse incorrect entries
7. **Departments** - Create departments, enable accounting modules

Complexity ranges from single-call operations (Tier 1) to multi-step workflows (Tier 3).

## Competition Timeline

- **Start:** March 19, 2026 at 18:00 CET
- **End:** March 22, 2026 at 15:00 CET
- **Tier 1 tasks:** Available from start
- **Tier 2 tasks:** Opens early Friday (March 20)
- **Tier 3 tasks:** Opens early Saturday (March 21)
