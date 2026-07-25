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
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

_HTTP_TIMEOUT = 15.0   # seconds


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

def get_endpoint(region: str) -> str:
    """Return the block engine URL for the requested region (default: mainnet)."""
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
) -> Dict[str, BundleResult]:
    """
    Poll the block engine until all bundles reach a terminal state.

    Terminal states: ``confirmed``, ``finalized``, ``failed``.
    Bundles not seen in the response (block engine hasn't processed them yet)
    remain in the pending set and continue to be polled.

    Returns a dict mapping bundle_id → BundleResult.
    """
    results: Dict[str, BundleResult] = {
        bid: BundleResult(bundle_id=bid, success=False) for bid in bundle_ids
    }
    pending = set(bundle_ids)

    for attempt in range(1, max_attempts + 1):
        if not pending:
            break

        await asyncio.sleep(poll_delay)

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
                    icon = "✓" if ok else "✗"
                    logger.info(f"[JITO] {icon} Bundle {bid[:20]}… → {status}")

                elif status == "failed":
                    results[bid] = BundleResult(
                        bundle_id=bid,
                        success=False,
                        confirmed=False,
                        error=str(err) if err else "bundle failed",
                    )
                    pending.discard(bid)
                    logger.error(f"[JITO] ✗ Bundle {bid[:20]}… failed: {err}")

                else:
                    logger.debug(
                        f"[JITO] Bundle {bid[:20]}… → {status or 'pending'} "
                        f"(attempt {attempt}/{max_attempts})"
                    )

        except Exception as exc:
            logger.debug(f"[JITO] poll attempt {attempt} error: {exc}")

    for bid in pending:
        results[bid].error = f"Confirmation timeout after {max_attempts * poll_delay:.0f}s"
        logger.warning(f"[JITO] Bundle {bid[:20]}… timed out — may still land on-chain")

    return results
