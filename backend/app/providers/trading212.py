"""Read-only client for the Trading 212 Public API (https://docs.trading212.com/api).

Only the endpoints the sync needs: account summary and the three history lists. Auth is HTTP
Basic with `API_KEY:API_SECRET`; a key created before secrets existed is sent bare in the
`Authorization` header (the API's "legacy" scheme). Rate limits are per account and tight on the
history endpoints (6 requests a minute), so every response's `x-ratelimit-*` headers are honoured:
when a window is used up the client sleeps until `x-ratelimit-reset`, and a 429 is retried.
"""

from __future__ import annotations

import base64
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

BASE_URLS = {
    "live": "https://live.trading212.com",
    "demo": "https://demo.trading212.com",
}

_MAX_429_RETRIES = 6
_PAGE_LIMIT = 50


class Trading212Error(Exception):
    """Anything that stops a sync: bad key, missing permission, network, unexpected reply."""


class Trading212AuthError(Trading212Error):
    pass


def _auth_header(api_key: str, api_secret: str) -> str:
    if not api_secret:
        return api_key
    token = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode("ascii")
    return f"Basic {token}"


class Trading212Client:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        environment: str = "live",
        *,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if environment not in BASE_URLS:
            raise ValueError(f"unknown Trading 212 environment {environment!r}")
        self._http = http or httpx.Client(timeout=30.0)
        self._base = BASE_URLS[environment]
        self._headers = {"Authorization": _auth_header(api_key, api_secret), "Accept": "application/json"}
        self._sleep = sleep
        self._clock = clock

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Trading212Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------

    def _wait_for_reset(self, response: httpx.Response, fallback: float) -> None:
        reset = response.headers.get("x-ratelimit-reset")
        try:
            wait = float(reset) - self._clock() + 0.5 if reset else fallback
        except ValueError:
            wait = fallback
        self._sleep(min(max(wait, 0.5), 120.0))

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{self._base}{path}"
        for _ in range(_MAX_429_RETRIES + 1):
            try:
                response = self._http.get(url, params=params, headers=self._headers)
            except httpx.HTTPError as exc:
                raise Trading212Error(f"Couldn't reach Trading 212: {exc}") from exc

            if response.status_code == 429:
                self._wait_for_reset(response, fallback=10.0)
                continue
            if response.status_code == 401:
                raise Trading212AuthError("Trading 212 rejected the API key. Check the key and secret.")
            if response.status_code == 403:
                raise Trading212AuthError(
                    "The API key is missing a permission. It needs read access to account data and history."
                )
            if response.status_code >= 400:
                raise Trading212Error(f"Trading 212 returned HTTP {response.status_code}: {response.text[:200]}")

            if response.headers.get("x-ratelimit-remaining") == "0":
                self._wait_for_reset(response, fallback=10.0)
            try:
                return response.json()
            except ValueError as exc:
                raise Trading212Error("Trading 212 sent a reply that isn't JSON") from exc
        raise Trading212Error("Trading 212 kept rate-limiting the request; try again in a few minutes")

    # -- endpoints ---------------------------------------------------------

    def account_summary(self) -> dict[str, Any]:
        return self._get("/api/v0/equity/account/summary")

    def _paged(
        self, path: str, stop_after_page: Callable[[list[dict]], bool] | None = None
    ) -> Iterator[dict]:
        """Yield every item across pages, following `nextPagePath`. `stop_after_page` lets the
        caller end early (e.g. once a whole page is already known)."""
        next_path: str | None = path
        params: dict[str, Any] | None = {"limit": _PAGE_LIMIT}
        while next_path:
            page = self._get(next_path, params)
            items = list(page.get("items") or [])
            yield from items
            if stop_after_page is not None and stop_after_page(items):
                return
            next_path = page.get("nextPagePath")
            params = None  # nextPagePath already carries limit and cursor

    def orders(self, stop_after_page: Callable[[list[dict]], bool] | None = None) -> Iterator[dict]:
        return self._paged("/api/v0/equity/history/orders", stop_after_page)

    def dividends(self, stop_after_page: Callable[[list[dict]], bool] | None = None) -> Iterator[dict]:
        return self._paged("/api/v0/equity/history/dividends", stop_after_page)

    def transactions(self, stop_after_page: Callable[[list[dict]], bool] | None = None) -> Iterator[dict]:
        return self._paged("/api/v0/equity/history/transactions", stop_after_page)
