"""
PumpPortal API helper — retry wrapper for the trade-local endpoint.

PumpPortal is a free third-party service with no uptime SLA. Transient
502/503 responses (their backend briefly unreachable behind nginx) happen
occasionally and say nothing about whether your request was valid —
retrying with a short backoff clears most of them without any user
intervention. A 400, 429, or any other status is returned immediately
without retrying, since those represent either success or a real problem
(bad request, rate limit) that blindly retrying wouldn't fix.
"""

import asyncio
from typing import Optional

import httpx

from .logger import logger

RETRYABLE_STATUS_CODES = {502, 503}


async def post_with_retry(
    url: str,
    *,
    json_body: Optional[dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[dict] = None,
    timeout: float = 30,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.5,
) -> httpx.Response:
    """
    POST with retries on 502/503 only, using exponential backoff
    (1.5s, 3s, 6s, ... by default).

    Any other status code — 200, 400, 429, etc. — is returned immediately
    on the first attempt, unretried.

    On a network-level failure (timeout, connection refused) on every
    attempt, re-raises the underlying httpx exception. On exhausting all
    retries against 502/503, returns the last such response so the caller
    can log/handle it exactly like any other failed response.
    """
    last_response: Optional[httpx.Response] = None
    last_exception: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if content is not None:
                    response = await client.post(url, headers=headers, content=content)
                else:
                    response = await client.post(url, headers=headers, json=json_body)

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response  # success, or a non-retryable error — return as-is

            last_response = response
            logger.warning(
                f"[{response.status_code}] {url} — attempt {attempt}/{max_attempts} "
                f"failed. {'Retrying...' if attempt < max_attempts else 'Giving up.'}"
            )

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exception = e
            logger.warning(
                f"Network error on {url} — attempt {attempt}/{max_attempts}: {e}. "
                f"{'Retrying...' if attempt < max_attempts else 'Giving up.'}"
            )

        if attempt < max_attempts:
            delay = base_delay_seconds * (2 ** (attempt - 1))
            await asyncio.sleep(delay)

    if last_response is not None:
        return last_response
    raise last_exception
