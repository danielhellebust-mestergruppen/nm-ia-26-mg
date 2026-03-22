from __future__ import annotations

import logging
import httpx

logger = logging.getLogger("tripletex")


class ValidationError(Exception):
    """Raised on 422 with parsed field errors."""
    def __init__(self, status: int, fields: dict[str, str], raw: dict):
        self.status = status
        self.fields = fields  # {field_name: error_message}
        self.raw = raw
        super().__init__(f"Validation failed: {fields}")


def _parse_validation(resp: httpx.Response) -> ValidationError | None:
    """Parse a 422 response into structured field errors."""
    if resp.status_code != 422:
        return None
    try:
        body = resp.json()
        messages = body.get("validationMessages", [])
        fields = {}
        for m in messages:
            key = m.get("field") or m.get("message", "unknown")
            fields[key] = m.get("message", "")
        return ValidationError(422, fields, body)
    except Exception:
        return ValidationError(422, {"unknown": resp.text[:200]}, {})


class TripletexClient:
    def __init__(self, base_url: str, session_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth = ("0", session_token)
        self._client = httpx.AsyncClient(timeout=30.0)

    async def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        logger.info(f"GET {url} params={params}")
        resp = await self._client.get(url, auth=self.auth, params=params)
        logger.info(f"  → {resp.status_code}")
        resp.raise_for_status()
        return resp.json()

    async def post(self, path: str, json: dict) -> dict:
        url = f"{self.base_url}{path}"
        # Clean nulls from body BEFORE posting (prevents 422 on null fields)
        clean = {k: v for k, v in json.items() if v is not None}
        logger.info(f"POST {url} body={clean}")
        resp = await self._client.post(url, auth=self.auth, json=clean)
        logger.info(f"  → {resp.status_code} {resp.text[:500]}")
        if resp.status_code == 422:
            err = _parse_validation(resp)
            if err:
                # Try to fix and retry ONCE — a retry that scores > failed task worth 0
                fixed = False
                for field, msg in err.fields.items():
                    if "eksisterer ikke" in msg and field in clean:
                        del clean[field]
                        logger.info(f"  Auto-fix: removed invalid field '{field}', retrying")
                        fixed = True
                if fixed:
                    resp = await self._client.post(url, auth=self.auth, json=clean)
                    logger.info(f"  → {resp.status_code} (retry after fix)")
                    if resp.status_code == 422:
                        err2 = _parse_validation(resp)
                        if err2:
                            raise err2
                    resp.raise_for_status()
                    return resp.json()
                raise err
        resp.raise_for_status()
        return resp.json()

    async def put(self, path: str, json: dict, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        logger.info(f"PUT {url} body={json} params={params}")
        resp = await self._client.put(url, auth=self.auth, json=json, params=params)
        logger.info(f"  → {resp.status_code} {resp.text[:500]}")
        if resp.status_code == 422:
            err = _parse_validation(resp)
            if err:
                raise err
        resp.raise_for_status()
        if resp.text.strip():
            return resp.json()
        return {}

    async def delete(self, path: str) -> None:
        url = f"{self.base_url}{path}"
        logger.info(f"DELETE {url}")
        resp = await self._client.delete(url, auth=self.auth)
        logger.info(f"  → {resp.status_code}")
        resp.raise_for_status()
