from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class RateLimiter:
    min_interval_seconds: float
    _last_call_ts: float = 0.0

    def wait(self) -> None:
        now = time.time()
        wait_for = self.min_interval_seconds - (now - self._last_call_ts)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_call_ts = time.time()


class AstarApiClient:
    def __init__(
        self,
        bearer_token: str,
        base_url: str = "https://api.ainm.no/astar-island",
        timeout_seconds: int = 30,
    ) -> None:
        if not bearer_token:
            raise ValueError("Missing bearer token")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
            }
        )
        self._simulate_limiter = RateLimiter(min_interval_seconds=0.21)  # <=5 rps
        self._submit_limiter = RateLimiter(min_interval_seconds=0.55)  # <=2 rps

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> Any:
        url = f"{self.base_url}{path}"
        last_err: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code == 429:
                    if attempt == max_retries:
                        raise RuntimeError(f"HTTP 429 on {path}: {response.text[:400]}")
                    retry_after = response.headers.get("Retry-After")
                    wait_s = float(retry_after) if retry_after else 1.25 * (attempt + 1)
                    time.sleep(wait_s)
                    continue
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status_code} on {path}: {response.text[:400]}"
                    )
                return response.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == max_retries:
                    break
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"API request failed {method} {path}: {last_err}") from last_err

    def list_rounds(self) -> list[dict[str, Any]]:
        return self._request("GET", "/rounds")

    def get_round(self, round_id: str) -> dict[str, Any]:
        return self._request("GET", f"/rounds/{round_id}")

    def get_budget(self) -> dict[str, Any]:
        return self._request("GET", "/budget")

    def simulate(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._simulate_limiter.wait()
        return self._request("POST", "/simulate", json_payload=payload)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._submit_limiter.wait()
        return self._request("POST", "/submit", json_payload=payload)

    def my_rounds(self) -> list[dict[str, Any]]:
        return self._request("GET", "/my-rounds")

    def my_predictions(self, round_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/my-predictions/{round_id}")

    def analysis(self, round_id: str, seed_index: int) -> dict[str, Any]:
        return self._request("GET", f"/analysis/{round_id}/{seed_index}")

    def replay(self, round_id: str, seed_index: int) -> dict[str, Any]:
        payload = {"round_id": round_id, "seed_index": int(seed_index)}
        return self._request("POST", "/replay", json_payload=payload)

    def leaderboard(self) -> list[dict[str, Any]]:
        return self._request("GET", "/leaderboard")

