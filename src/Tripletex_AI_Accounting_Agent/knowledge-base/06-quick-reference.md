# Tripletex Task - Quick Reference Card

**Last updated:** 2026-03-19T18:00 CET (initial fetch)

## At a Glance

```
Endpoint:     POST /solve (HTTPS, 300s timeout)
Auth:         Basic Auth - username: "0", password: session_token
Response:     {"status": "completed"} with HTTP 200
Tasks:        30 tasks, 56 variants each (7 languages x 8 datasets)
Max score:    6.0 per task (Tier 3 perfect + max efficiency)
Leaderboard:  Sum of best scores across all 30 tasks
```

## Request Shape

```
body.prompt                          -> task description (string, multilingual)
body.files[].filename                -> attachment filename
body.files[].content_base64          -> base64 encoded content
body.files[].mime_type               -> MIME type
body.tripletex_credentials.base_url  -> proxy API URL (use this, not direct)
body.tripletex_credentials.session_token -> auth password
```

## API Cheat Sheet

```python
auth = ("0", creds["session_token"])
base = creds["base_url"]

# GET list:    requests.get(f"{base}/employee", auth=auth, params={"fields": "id,firstName"})
# GET search:  requests.get(f"{base}/customer", auth=auth, params={"name": "Acme", "count": 10})
# POST create: requests.post(f"{base}/customer", auth=auth, json={"name": "X", "isCustomer": True})
# PUT update:  requests.put(f"{base}/employee/{id}", auth=auth, json={...})
# DELETE:      requests.delete(f"{base}/travelExpense/{id}", auth=auth)
```

## Available Endpoints

```
/employee          GET POST PUT
/customer          GET POST PUT
/product           GET POST
/invoice           GET POST
/order             GET POST
/travelExpense     GET POST PUT DELETE
/project           GET POST
/department        GET POST
/ledger/account    GET
/ledger/posting    GET
/ledger/voucher    GET POST DELETE
```

## Response Shapes

```json
// List response
{"fullResultSize": N, "values": [...]}

// Single entity creation
{"value": {"id": 123, ...}}
```

## Scoring Formula

```
score = correctness * tier_multiplier * efficiency_bonus

correctness      = points_earned / max_points  (0.0 to 1.0)
tier_multiplier  = 1 (Tier 1), 2 (Tier 2), 3 (Tier 3)
efficiency_bonus = 1.0 to 2.0 (only when correctness = 1.0, else 1.0)
```

## Rate Limits (Verified)

```
Concurrent submissions: 3
Per task per day:       5
```

## Tier Schedule

```
Tier 1: From start (March 19, 18:00 CET)
Tier 2: Early Friday (March 20)
Tier 3: Early Saturday (March 21)
```

## Critical Reminders

- Each submission gets a FRESH account - agent starts from scratch every time
- ALL API calls must go through the provided proxy base_url
- 4xx errors hurt your efficiency bonus - plan calls carefully
- Only perfect correctness (1.0) unlocks efficiency bonus
- Best score per task is retained - bad runs can't hurt you
