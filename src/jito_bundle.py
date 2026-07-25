"""
Jito MEV Bundle helper
Submits groups of signed Solana transactions to the Jito block engine as
atomic bundles: either ALL land in the same block, or NONE do.

Jito limits: 5 transactions per bundle maximum.  One slot is consumed by the
mandatory tip transaction, leaving 4 payload slots per bundle.

No new dependencies — uses httpx (already installed) and solders.

Usage (from seller.py / token_creator.py):
    from .jito_bundle import build_tip_tx, send_bundle, poll_bundle_statuses
"""

from __future__ import annotations

import asyncio
import base64
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import httpx
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from .logger import logger


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Jito rotates through 8 tip accounts; one is chosen randomly per bundle.
JITO_TIP_ACCOUNTS: List[str] = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvB6pexAmX32HvWLjgAobB4FV5QLM3uBd6",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9ypeXQbFHNDMFe5r5R6Rlcof7e2MLNYMFQMJ3Y",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6cv",
]

# Regional block engine endpoints (same JSON-RPC URL for sendBundle and
# getBundleStatuses — the method field in the payload distinguishes them).
JITO_ENDPOINTS: Dict[str, str] = {
    "mainnet":   "https://mainnet.block-engine.jito.labs.io/api/v1/bundles",
    "amsterdam": "https://amsterdam.mainnet.block-engine.jito.labs.io/api/v1/bundles",
    "ny":        "https://ny.mainnet.block-engine.jito.labs.io/api/v1/bundles",
    "tokyo":     "https://tokyo.mainnet.block-engine.jito.labs.io/api/v1/bundles",
    "frankfurt": "https://frankfurt.mainnet.block-engine.jito.labs.io/api/v1/bundles",
}

# Maximum sell-transaction slots per bundle (1 slot reserved for the tip tx).
MAX_TXS_PER_BUNDLE: int = 4

# Conservative validity window for a Solana blockhash.
# The network drops txs after ~150 slots (~60 s on mainnet), but variance
# means it can be as short as 60 s.  We use 55 s to give ourselves a buffer.
BLOCKHASH_VALIDITY_SECONDS: float = 55.0

_HTTP_TIMEOUT = 15.0   # seconds

# ── 4C: Cached fastest endpoint (set once by pick_fastest_endpoint) ───────────
_cached_fastest_endpoint: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BundleResult:
    bundle_id:    Optional[str]
    success:      bool
    confirmed:    bool                = False
    tx_signatures: List[str]         = field(default_factory=list)
    error:        Optional[str]       = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def scale_tip(current_lamports: int, multiplier: float, max_lamports: int) -> int:
    """
    Multiply *current_lamports* by *multiplier*, capping at *max_lamports*.
    Used by the 4A retry loop to escalate the tip on each failed attempt.
    """
    return min(int(current_lamports * multiplier), max_lamports)


def get_endpoint(region: str) -> str:
    """
    Return the block engine URL for the requested region (default: mainnet).
    For runtime auto-selection based on measured latency, call get_endpoint_async().
    """
    region = region.lower().strip()
    if region == "auto":
        # Synchronous call site — return the cached result or fall back to mainnet
        return _cached_fastest_endpoint or JITO_ENDPOINTS["mainnet"]
    return JITO_ENDPOINTS.get(region, JITO_ENDPOINTS["mainnet"])


async def pick_fastest_endpoint(probe_timeout: float = 4.0) -> str:
    """
    Ping all regional block engines in parallel and return the URL with the
    lowest round-trip time.

    Uses a lightweight getBundleStatuses call with an empty list — valid JSON-RPC
    that every endpoint accepts and processes quickly.  Result is cached so
    subsequent calls return instantly without hitting the network again.

    Called automatically when JITO_ENDPOINT=auto is set in .env.
    """
    global _cached_fastest_endpoint
    if _cached_fastest_endpoint is not None:
        return _cached_fastest_endpoint

    logger.info("[JITO] 4C — probing regional endpoints to find the fastest…")

    async def _probe(name: str, url: str):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=probe_timeout) as client:
                await client.post(
                    url,
                    json={"jsonrpc": "2.0", "id": 1,
                          "method": "getBundleStatuses", "params": [[]]},
                    headers={"Content-Type": "application/json"},
                )
            elapsed = time.monotonic() - t0
            logger.debug(f"[JITO] {name:12s} → {elapsed * 1000:.0f}ms")
            return name, url, elapsed
        except Exception as exc:
            logger.debug(f"[JITO] {name:12s} → unreachable ({exc})")
            return name, url, float("inf")

    probes = await asyncio.gather(
        *[_probe(name, url) for name, url in JITO_ENDPOINTS.items()],
        return_exceptions=True,
    )

    best_name, best_url, best_ms = "mainnet", JITO_ENDPOINTS["mainnet"], float("inf")
    for result in probes:
        if isinstance(result, Exception):
            continue
        name, url, elapsed = result
        if elapsed < best_ms:
            best_name, best_url, best_ms = name, url, elapsed

    label = f"{best_ms * 1000:.0f}ms" if best_ms < float("inf") else "unreachable"
    logger.info(f"[JITO] ✓ Fastest endpoint: {best_name} ({label})")

    _cached_fastest_endpoint = best_url
    return best_url


async def get_endpoint_async(region: str) -> str:
    """
    Async version of get_endpoint — supports 'auto' mode.

    When region == 'auto', fires pick_fastest_endpoint() (cached after first call).
    Otherwise returns the named endpoint URL synchronously.
    """
    if region.lower().strip() == "auto":
        return await pick_fastest_endpoint()
    return JITO_ENDPOINTS.get(region.lower().strip(), JITO_ENDPOINTS["mainnet"])


def pick_tip_account() -> Pubkey:
    """Pick a random Jito tip account for this bundle."""
    return Pubkey.from_string(random.choice(JITO_TIP_ACCOUNTS))


def build_tip_tx(tip_keypair: Keypair, tip_lamports: int, blockhash: Hash) -> bytes:
    """
    Build and sign a legacy SystemProgram.transfer to a random Jito tip account.

    The tip transaction must share the same blockhash as the payload transactions
    so the entire bundle is treated atomically by the block engine.

    Returns the raw signed transaction bytes.
    """
    tip_pubkey = pick_tip_account()
    ix = transfer(TransferParams(
        from_pubkey=tip_keypair.pubkey(),
        to_pubkey=tip_pubkey,
        lamports=tip_lamports,
    ))
    msg = Message.new_with_blockhash(
        [ix],
        tip_keypair.pubkey(),
        blockhash,
    )
    tx = Transaction.new_unsigned(msg)
    tx.sign([tip_keypair], blockhash)
    return bytes(tx)


# ─────────────────────────────────────────────────────────────────────────────
# Network calls
# ─────────────────────────────────────────────────────────────────────────────

async def send_bundle(
    signed_tx_bytes_list: List[bytes],
    endpoint_url: str,
) -> BundleResult:
    """
    POST a bundle of fully-signed transactions to the Jito block engine.

    ``signed_tx_bytes_list`` must contain at most 5 transactions total
    (including the tip transaction, which should be first).

    Returns a BundleResult; on acceptance the ``bundle_id`` UUID is set so
    you can poll for confirmation via ``poll_bundle_statuses``.
    """
    if len(signed_tx_bytes_list) > 5:
        return BundleResult(
            bundle_id=None,
            success=False,
            error=f"Bundle exceeds 5-transaction limit ({len(signed_tx_bytes_list)} txs)",
        )

    encoded = [base64.b64encode(tx).decode() for tx in signed_tx_bytes_list]
    payload = {
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "sendBundle",
        "params":  [encoded],
    }

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                endpoint_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        data = resp.json()

        if "result" in data:
            bundle_id = data["result"]
            logger.info(f"[JITO] Bundle submitted ✓  id={bundle_id[:20]}…")
            return BundleResult(bundle_id=bundle_id, success=True)

        if "error" in data:
            err_msg = data["error"].get("message", str(data["error"]))
            logger.error(f"[JITO] Bundle rejected: {err_msg}")
            return BundleResult(bundle_id=None, success=False, error=err_msg)

        logger.error(f"[JITO] Unexpected response: {data}")
        return BundleResult(bundle_id=None, success=False, error=str(data))

    except Exception as exc:
        logger.error(f"[JITO] send_bundle error: {exc}")
        return BundleResult(bundle_id=None, success=False, error=str(exc))


async def poll_bundle_statuses(
    bundle_ids: List[str],
    endpoint_url: str,
    *,
    max_attempts: int = 25,
    poll_delay:   float = 2.0,
    on_status: Optional[Callable[[str], None]] = None,
) -> Dict[str, BundleResult]:
    """
    Poll the block engine until all bundles reach a terminal state.

    Terminal states: ``confirmed``, ``finalized``, ``failed``.
    Bundles not seen in the response remain pending and continue to be polled.

    Args:
        on_status: Optional callback called after each poll round with a
                   Rich-markup status string — used by the TUI to stream live
                   progress into the footer without blocking the async loop.

    Returns a dict mapping bundle_id → BundleResult.
    """
    total   = len(bundle_ids)
    results: Dict[str, BundleResult] = {
        bid: BundleResult(bundle_id=bid, success=False) for bid in bundle_ids
    }
    pending = set(bundle_ids)

    def _emit(msg: str) -> None:
        if on_status is not None:
            try:
                on_status(msg)
            except Exception:
                pass

    for attempt in range(1, max_attempts + 1):
        if not pending:
            break

        await asyncio.sleep(poll_delay)

        confirmed_count = total - len(pending)
        _emit(
            f"[bold yellow]⚡ Jito:[/bold yellow] "
            f"{confirmed_count}/{total} confirmed  "
            f"[dim]│[/dim] polling attempt {attempt}/{max_attempts}…"
        )

        payload = {
            "jsonrpc": "2.0",
            "id":      1,
            "method":  "getBundleStatuses",
            "params":  [list(pending)],
        }

        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(
                    endpoint_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            data   = resp.json()
            values = data.get("result", {}).get("value", [])

            for entry in values:
                bid    = entry.get("bundle_id", "")
                if bid not in pending:
                    continue

                status = entry.get("confirmation_status", "")
                err    = entry.get("err")
                sigs   = entry.get("transactions", [])

                # err is {"Ok": null} or null on success; an error dict otherwise
                ok = (
                    err is None
                    or err == {"Ok": None}
                    or (isinstance(err, dict) and err.get("Ok") is None and len(err) == 1)
                )

                if status in ("confirmed", "finalized"):
                    results[bid] = BundleResult(
                        bundle_id=bid,
                        success=ok,
                        confirmed=True,
                        tx_signatures=sigs,
                        error=None if ok else str(err),
                    )
                    pending.discard(bid)
                    icon  = "✓" if ok else "✗"
                    color = "green" if ok else "red"
                    logger.info(f"[JITO] {icon} Bundle {bid[:20]}… → {status}")
                    _emit(
                        f"[bold yellow]⚡ Jito:[/bold yellow] "
                        f"[{color}]{icon} {bid[:14]}…[/{color}] → {status}  "
                        f"[dim]({total - len(pending)}/{total} done)[/dim]"
                    )

                elif status == "failed":
                    results[bid] = BundleResult(
                        bundle_id=bid,
                        success=False,
                        confirmed=False,
                        error=str(err) if err else "bundle failed",
                    )
                    pending.discard(bid)
                    logger.error(f"[JITO] ✗ Bundle {bid[:20]}… failed: {err}")
                    _emit(
                        f"[bold yellow]⚡ Jito:[/bold yellow] "
                        f"[red]✗ {bid[:14]}…[/red] → failed"
                    )

                else:
                    logger.debug(
                        f"[JITO] Bundle {bid[:20]}… → {status or 'pending'} "
                        f"(attempt {attempt}/{max_attempts})"
                    )

        except Exception as exc:
            logger.debug(f"[JITO] poll attempt {attempt} error: {exc}")

    for bid in pending:
        timeout_secs = f"{max_attempts * poll_delay:.0f}s"
        results[bid].error = f"Confirmation timeout after {timeout_secs}"
        logger.warning(f"[JITO] Bundle {bid[:20]}… timed out — may still land on-chain")
        _emit(
            f"[bold yellow]⚡ Jito:[/bold yellow] "
            f"[yellow]⏳ {bid[:14]}…[/yellow] timed out after {timeout_secs} "
            f"[dim](may still confirm)[/dim]"
        )

    return results
