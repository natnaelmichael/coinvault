"""
PumpPortal API helper
Provides post_with_retry — an httpx POST wrapper with automatic retry on
transient server errors (502, 503, 429) and network timeouts.

All HTTP calls to PumpPortal's trade-local endpoint go through this module.
"""

import asyncio
from typing import Optional

import httpx


_DEFAULT_TIMEOUT   = 30.0   # seconds per attempt
_DEFAULT_RETRIES   = 4
_RETRY_DELAY_BASE  = 1.5    # seconds (doubles on each retry)
_RETRYABLE_CODES   = {429, 500, 502, 503, 504}


async def post_with_retry(
    url: str,
    *,
    json_body: Optional[dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[dict] = None,
    timeout: float = _DEFAULT_TIMEOUT,
    max_retries: int = _DEFAULT_RETRIES,
) -> httpx.Response:
    """
    POST *url* with automatic retry on transient errors.

    Exactly one of json_body or content must be supplied:
      - json_body : dict  → serialised to JSON by httpx; sets Content-Type automatically.
      - content   : bytes → sent as-is; caller is responsible for the Content-Type header.

    Returns the httpx.Response from the final successful (or last) attempt.
    Raises the underlying exception only if all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    delay = _RETRY_DELAY_BASE

    for attempt in range(1, max_retries + 2):   # +1 for the initial attempt
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if json_body is not None:
                    response = await client.post(url, json=json_body, headers=headers or {})
                else:
                    response = await client.post(url, content=content, headers=headers or {})

            if response.status_code not in _RETRYABLE_CODES:
                return response

            last_exc = None   # not a hard exception — just a retryable status
            if attempt > max_retries:
                return response  # return the last bad response rather than raising

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt > max_retries:
                raise

        wait = min(delay, 30.0)
        await asyncio.sleep(wait)
        delay *= 2

    # Should not be reached, but satisfies type checkers
    if last_exc:
        raise last_exc
    raise RuntimeError(f"post_with_retry: exhausted retries for {url}")
