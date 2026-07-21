"""
Solana transaction helper
Provides sign_and_send — deserialise a raw VersionedTransaction returned by
PumpPortal's trade-local API, refresh the blockhash, sign with the supplied
keypairs, broadcast via the RPC, and wait for confirmation.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import List, Optional

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from .logger import logger


@dataclass
class TxResult:
    success:   bool
    confirmed: bool = False
    signature: Optional[str] = None
    error:     Optional[str] = None


async def sign_and_send(
    client: AsyncClient,
    tx_bytes: bytes,
    signers: List[Keypair],
    *,
    max_confirm_attempts: int = 30,
    confirm_delay: float = 2.0,
) -> TxResult:
    """
    Deserialise *tx_bytes* (raw bytes from PumpPortal trade-local), refresh the
    blockhash, sign with every keypair in *signers*, submit, and poll for
    confirmation.

    Args:
        client:               Solana AsyncClient connected to the target cluster.
        tx_bytes:             Raw serialised VersionedTransaction bytes.
        signers:              Ordered list of Keypairs that must sign the transaction.
                              The first signer is also used to fetch the fee-payer's
                              blockhash context if needed.
        max_confirm_attempts: How many times to poll for confirmation.
        confirm_delay:        Seconds between confirmation polls.

    Returns:
        TxResult with success/confirmed flags, the base58 signature, or an error.
    """
    try:
        # ── 1. Deserialise ─────────────────────────────────────────────────────
        tx = VersionedTransaction.from_bytes(tx_bytes)

        # ── 2. Refresh the blockhash so the tx doesn't expire ─────────────────
        bh_resp = await client.get_latest_blockhash(commitment=Confirmed)
        recent_blockhash = bh_resp.value.blockhash
        tx.message.recent_blockhash = recent_blockhash

        # ── 3. Sign ────────────────────────────────────────────────────────────
        tx.sign(signers)

        # ── 4. Serialise & send ────────────────────────────────────────────────
        raw = bytes(tx)
        send_resp = await client.send_raw_transaction(
            raw,
            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed),
        )

        # send_resp.value is the base58 signature string
        sig = str(send_resp.value)
        logger.debug(f"Transaction sent: {sig}")

        # ── 5. Confirm ─────────────────────────────────────────────────────────
        for attempt in range(1, max_confirm_attempts + 1):
            await asyncio.sleep(confirm_delay)
            try:
                status_resp = await client.get_signature_statuses([send_resp.value])
                statuses = status_resp.value
                if statuses and statuses[0] is not None:
                    confirmation_status = statuses[0].confirmation_status
                    err = statuses[0].err
                    if err:
                        logger.error(f"Transaction failed on-chain: {err}")
                        return TxResult(
                            success=False, confirmed=False,
                            signature=sig, error=str(err),
                        )
                    # confirmed / finalized both count as done
                    if confirmation_status in ("confirmed", "finalized"):
                        return TxResult(success=True, confirmed=True, signature=sig)
            except Exception as poll_exc:
                logger.debug(f"Confirmation poll {attempt} error: {poll_exc}")

        # Timed out waiting for confirmation — the tx may still land
        logger.warning(f"Transaction {sig[:16]}... not confirmed after "
                       f"{max_confirm_attempts * confirm_delay:.0f}s — "
                       "it may still be processed by the network.")
        return TxResult(
            success=False, confirmed=False,
            signature=sig,
            error=f"Confirmation timeout after {max_confirm_attempts} attempts",
        )

    except Exception as exc:
        logger.error(f"sign_and_send error: {exc}")
        return TxResult(success=False, confirmed=False, error=str(exc))
