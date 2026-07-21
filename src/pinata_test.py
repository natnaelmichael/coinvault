"""
pinata_test.py — standalone Pinata JWT check.

Dry-run mode short-circuits before ever calling Pinata, so it can't confirm
PINATA_JWT actually works. This script calls the real upload path directly,
bypassing dry-run, wallets, and PumpPortal entirely.

Run from your project root:  python -m src.pinata_test
(or adjust the relative imports below to match wherever this lands)
"""
import asyncio
from solana.rpc.async_api import AsyncClient

from .config import config
from .token_creator import get_token_creator, TokenMetadata


async def main() -> None:
    if not config.pinata_jwt:
        print("✗ PINATA_JWT is not set in .env — nothing to test.")
        return

    metadata = TokenMetadata(
        name="Pinata Test Token",
        symbol="TEST",
        description="Throwaway metadata to confirm Pinata uploads work.",
        image_path="coinvault logo.jpeg",  # any small local image; swap path as needed
    )

    # TokenCreator's constructor requires an rpc_client (same pattern used by
    # wallet_manager.py and buyer.py), even though this script never actually
    # sends a transaction — it's only used elsewhere in TokenCreator, not by
    # _upload_metadata_pumpfun, but the constructor needs it regardless.
    rpc_client = AsyncClient(config.rpc_url)
    try:
        creator = get_token_creator(rpc_client)
        was_dry_run, config.dry_run_mode = config.dry_run_mode, False  # force a real call
        try:
            result = await creator._upload_metadata_pumpfun(metadata)
        finally:
            config.dry_run_mode = was_dry_run  # restore whatever it was
    finally:
        await rpc_client.close()

    if result:
        print(f"✓ Pinata upload succeeded: {result['metadataUri']}")
    else:
        print("✗ Pinata upload failed — check the [PINATA] error log above.")


if __name__ == "__main__":
    asyncio.run(main())
