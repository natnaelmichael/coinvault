"""
Solana Transaction Utilities
─────────────────────────────
Shared "deserialize → refresh blockhash → sign → send → confirm" pipeline.

This was previously copy-pasted, nearly identically, across buyer.py,
seller.py, and token_creator.py. Centralizing it here means a fix or
improvement (like the confirmation polling below) applies everywhere at
once, instead of needing to be made in three places and risking drift
between them.

Note: the blockhash-refresh-before-signing step is kept exactly as it was
in all three original files (fetch a fresh blockhash and rebuild the
message with it, rather than signing PumpPortal's returned transaction
as-is). That's a deliberate deviation from PumpPortal's own minimal
example — not reverted here, just centralized.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional

from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.keypair import Keypair
from solders.signature import Signature
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from .logger import logger


@dataclass
class SendResult:
    """Outcome of sending (and optionally confirming) a transaction."""
    success: bool
    signature: Optional[str] = None
    confirmed: bool = False
    error: Optional[str] = None


async def sign_and_send(
    rpc_client: AsyncClient,
    unsigned_tx_bytes: bytes,
    signers: List[Keypair],
    skip_preflight: bool = True,
    max_retries: int = 3,
    confirm: bool = True,
    confirm_timeout_seconds: float = 30.0,
    confirm_poll_interval_seconds: float = 1.0,
) -> SendResult:
    """
    Deserialize a PumpPortal-style unsigned transaction, swap in a fresh
    blockhash, sign it with the given signers, send it, and (unless
    confirm=False) poll until it lands, fails on-chain, or times out.

    Args:
        rpc_client:      Shared AsyncClient
        unsigned_tx_bytes: Raw bytes as returned by PumpPortal's trade-local
                           endpoint (response.content)
        signers:         Keypairs to sign with, in the order PumpPortal's
                           returned message expects them
        skip_preflight:  Passed through to send_raw_transaction
        max_retries:     Passed through to send_raw_transaction
        confirm:         If False, returns immediately after sending —
                           signature is returned but confirmed stays False.
                           Useful if a caller wants to confirm multiple
                           sends concurrently rather than one at a time.
        confirm_timeout_seconds: How long to poll before giving up
        confirm_poll_interval_seconds: Delay between polls

    Returns:
        SendResult — check both `.success` and `.confirmed`. A transaction
        can be `success=True, confirmed=False` if confirm=False was passed;
        that is NOT the same as a failure.
    """
    try:
        unsigned_tx = VersionedTransaction.from_bytes(unsigned_tx_bytes)

        blockhash_resp = await rpc_client.get_latest_blockhash()
        fresh_blockhash = blockhash_resp.value.blockhash

        old_msg = unsigned_tx.message
        if not isinstance(old_msg, MessageV0):
            return SendResult(
                success=False,
                error=f"Expected MessageV0 from PumpPortal, got {type(old_msg).__name__}",
            )

        new_msg = MessageV0(
            header=old_msg.header,
            account_keys=old_msg.account_keys,
            recent_blockhash=fresh_blockhash,
            instructions=old_msg.instructions,
            address_table_lookups=old_msg.address_table_lookups,
        )

        signed_tx = VersionedTransaction(new_msg, signers)

        send_resp = await rpc_client.send_raw_transaction(
            bytes(signed_tx),
            opts=TxOpts(skip_preflight=skip_preflight, max_retries=max_retries),
        )

        if not send_resp.value:
            return SendResult(success=False, error="RPC returned no signature")

        sig_str = str(send_resp.value)

        if not confirm:
            return SendResult(success=True, signature=sig_str, confirmed=False)

        confirmed = await _wait_for_confirmation(
            rpc_client,
            send_resp.value,
            confirm_timeout_seconds,
            confirm_poll_interval_seconds,
        )

        if not confirmed:
            return SendResult(
                success=False,
                signature=sig_str,
                confirmed=False,
                error=(
                    f"Sent but not confirmed within {confirm_timeout_seconds}s "
                    f"— it may still land later, or may have failed/expired. "
                    f"Check signature {sig_str} manually before assuming success."
                ),
            )

        return SendResult(success=True, signature=sig_str, confirmed=True)

    except Exception as e:
        return SendResult(success=False, error=str(e))


async def _wait_for_confirmation(
    rpc_client: AsyncClient,
    signature: Signature,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> bool:
    """
    Poll get_signature_statuses until the transaction reaches at least
    'confirmed' commitment, reports an on-chain error, or the timeout
    elapses. Returns True only for a landed transaction with no error —
    a transaction that lands but carries a program error (e.g. slippage
    exceeded) is treated as NOT successful.

    NOTE: this hasn't been exercised against a live RPC endpoint in this
    review (no network access to Solana RPC from where this was written) —
    the shape of `get_signature_statuses`'s response and the exact string
    values of `confirmation_status` can vary slightly across solana-py
    versions. Worth a quick real test against devnet before trusting this
    in production; the string-matching below is deliberately loose
    (substring check, lowercased) to be resilient to enum-vs-string
    differences, but verify against whatever version you have pinned.
    """
    elapsed = 0.0
    while elapsed < timeout_seconds:
        try:
            resp = await rpc_client.get_signature_statuses([signature])
            status = resp.value[0]
            if status is not None:
                if status.err is not None:
                    logger.error(f"Tx {str(signature)[:16]}... failed on-chain: {status.err}")
                    return False
                conf = str(status.confirmation_status).lower()
                if "confirmed" in conf or "finalized" in conf:
                    return True
        except Exception as e:
            logger.warning(f"Confirmation poll error: {e}")

        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds

    logger.warning(f"Tx {str(signature)[:16]}... not confirmed within {timeout_seconds}s")
    return False
