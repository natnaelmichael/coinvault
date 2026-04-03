"""
Token Creator for pump.fun
Handles token creation, metadata upload, and deployment
"""
import requests
import json
import httpx
import asyncio
import base58

from typing import Optional, Dict, Any
from pathlib import Path
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from .config import config
from .logger import logger
from .notifications import notification_manager


class TokenMetadata:
    """Token metadata structure"""

    def __init__(
        self,
        name: str,
        symbol: str,
        description: str,
        image_path: Optional[str] = None,
        twitter: Optional[str] = None,
        telegram: Optional[str] = None,
        website: Optional[str] = None
    ):
        self.name = name
        self.symbol = symbol
        self.description = description
        self.image_path = image_path
        self.twitter = twitter
        self.telegram = telegram
        self.website = website

    def to_form_data(self) -> Dict[str, Any]:
        """Convert to form data for IPFS upload"""
        data = {
            'name': self.name,
            'symbol': self.symbol,
            'description': self.description,
            #twitter' : self.twitter,
            #'telegram' : self.telegram,
            #'website' : self.website,
            'showName': 'true'
        }

        if self.twitter:
            data['twitter'] = self.twitter
        if self.telegram:
            data['telegram'] = self.telegram
        if self.website:
            data['website'] = self.website

        return data


class TokenCreator:
    """Handles token creation on pump.fun"""

    # pump.fun API endpoints
    # IPFS metadata upload goes directly to pump.fun (pumpportal has no /api/ipfs).
    # The trade/create endpoint lives on pumpportal.fun.
    IPFS_UPLOAD_URL = "https://pump.fun/api/ipfs"
    CREATE_TX_URL = "https://pumpportal.fun/api/trade-local"

    # pump.fun's /api/ipfs endpoint validates that requests look like they come
    # from a browser. Without a matching User-Agent + Origin it returns 404.
    IPFS_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Origin": "https://pump.fun",
        "Referer": "https://pump.fun/",
    }

    def __init__(self, rpc_client: AsyncClient):
        self.rpc_client = rpc_client

    async def upload_metadata_to_ipfs(
        self,
        metadata: TokenMetadata
    ) -> Optional[Dict[str, str]]:
        """
        Upload token metadata and image to IPFS

        Args:
            metadata: Token metadata object

        Returns:
            Dict with metadataUri or None if failed
        """
        try:
            logger.info(f"Uploading metadata for {metadata.name} ({metadata.symbol}) to IPFS...")

            if config.dry_run_mode:
                logger.info("[DRY RUN] Would upload metadata to IPFS")
                return {
                    'metadataUri': 'ipfs://QmDRYRUNMODE123456789/metadata.json'
                }

            # Prepare form data
            form_data = metadata.to_form_data()

            # Prepare image file
            files = None
            if metadata.image_path:
                image_path = Path(metadata.image_path).expanduser().resolve()
                logger.debug(f"Resolved image path: {image_path} (exists: {image_path.exists()})")
                if image_path.exists():
                    with open(image_path, 'rb') as f:
                        file_content = f.read()
                    file_name = image_path.name
                    mime_type = self._get_mime_type(file_name)
                    files = {'file': (file_name, file_content, mime_type)}
                    logger.info(f"Image loaded: {file_name} ({len(file_content):,} bytes)")
                else:
                    logger.error(f"Image file not found: {image_path}")
                    logger.error("Token creation requires an image — please check the path and try again")
                    return None
            else:
                logger.error("No image path provided — pump.fun requires an image for token creation")
                return None

            # Upload to IPFS.
            # pump.fun/api/ipfs requires browser-like headers (User-Agent, Origin,
            # Referer) — requests without them get a 404 from the Next.js server.
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.IPFS_UPLOAD_URL,
                    data=form_data,
                    files=files,
                    headers=self.IPFS_HEADERS,
                )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✓ Metadata uploaded to IPFS: {result.get('metadataUri', 'Unknown')}")
                return result
            else:
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                logger.error(f"IPFS upload failed: {response.status_code}")
                logger.error(f"IPFS error detail: {error_detail}")
                return None

        except Exception as e:
            logger.error(f"Failed to upload metadata to IPFS: {e}")
            return None

    def _get_mime_type(self, filename: str) -> str:
        """Get MIME type from filename"""
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        return mime_types.get(ext, 'image/png')

    async def create_token(
        self,
        creator_wallet,
        metadata: TokenMetadata,
        initial_buy_sol: float = 0.0,
        slippage_bps: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a token on pump.fun

        Args:
            creator_wallet: Wallet to create token with (dev wallet)
            metadata: Token metadata
            initial_buy_sol: Amount of SOL for initial buy (optional)
            slippage_bps: Slippage in basis points (optional, uses default if None)

        Returns:
            Dict with token info or None if failed
        """
        try:
            logger.info(f"Creating token: {metadata.name} ({metadata.symbol})")

            # Upload metadata to IPFS
            ipfs_response = await self.upload_metadata_to_ipfs(metadata)
            if not ipfs_response:
                logger.error("Failed to upload metadata, aborting token creation")
                return None

            metadata_uri = ipfs_response['metadataUri']

            # Generate new keypair for the token mint
            mint_keypair = Keypair()
            mint_address = str(mint_keypair.pubkey())
            # PumpPortal's 'create' action requires the full 64-byte keypair encoded as
            # base58 in the 'mint' field — it uses the secret key server-side to derive
            # and register the mint address. The keypair is ALSO used below to co-sign
            # the returned VersionedTransaction (mint keypair must be first signer).
            mint_keypair_b58 = base58.b58encode(bytes(mint_keypair)).decode("utf-8")

            logger.info(f"Token mint address: {mint_address}")

            if config.dry_run_mode:
                logger.info("[DRY RUN] Would create token on pump.fun")
                logger.info(f"[DRY RUN] Mint: {mint_address}")
                logger.info(f"[DRY RUN] Metadata URI: {metadata_uri}")
                if initial_buy_sol > 0:
                    logger.info(f"[DRY RUN] Initial buy: {initial_buy_sol} SOL")

                return {
                    'success': True,
                    'signature': 'DRY_RUN_SIGNATURE_' + mint_address[:8],
                    'mint': mint_address,
                    'metadataUri': metadata_uri,
                    'creator': str(creator_wallet.public_key),
                    'initialBuy': initial_buy_sol
                }

            # Prepare create transaction request.
            # NOTE: PumpPortal expects slippage as a plain percent (e.g. 5), not bps (e.g. 500).
            slippage_pct = (slippage_bps or config.default_slippage_bps) / 100
            # Some PumpPortal deployments are picky and reject floats like 5.0 — prefer int when possible.
            slippage_value = int(slippage_pct) if float(slippage_pct).is_integer() else float(slippage_pct)

            create_data = {
                'publicKey': str(creator_wallet.public_key),
                'action': 'create',
                'tokenMetadata': {
                    'name': metadata.name,
                    'symbol': metadata.symbol,
                    'uri': metadata_uri,
                },
                # PumpPortal requires the full 64-byte mint keypair as base58
                # so it can co-sign the mint account creation server-side.
                'mint': mint_keypair_b58,
                'denominatedInSol': 'true',
                'amount': initial_buy_sol,
                'slippage': slippage_value,
                'priorityFee': 0.0005,
                'pool': 'pump',
            }

            # Request transaction from pump.fun API.
            # IMPORTANT: PumpPortal's /api/trade-local expects form-encoded data for the
            # PumpPortal /api/trade-local expects a JSON body with Content-Type: application/json
            logger.debug(f"Sending create payload: {create_data}")
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.CREATE_TX_URL,
                    headers={'Content-Type': 'application/json'},
                    content=json.dumps(create_data),      # JSON body, not form data
                )

            if response.status_code != 200:
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                logger.error(f"Failed to get create transaction: {response.status_code}")
                logger.error(f"API error detail: {error_detail}")
                # Always log raw response text as well (PumpPortal sometimes returns plain-text errors)
                try:
                    logger.error(f"API raw response: {response.text}")
                except Exception:
                    pass
                return None

            # Parse transaction.
            # Mint keypair MUST be first signer per PumpPortal docs.
            #tx_data = response.content
            '''unsigned_tx = VersionedTransaction.from_bytes(response.content)
            signed_tx = VersionedTransaction(unsigned_tx.message, [mint_keypair, creator_wallet.keypair])'''
            unsigned_tx = VersionedTransaction.from_bytes(response.content)
            blockhash_resp = await self.rpc_client.get_latest_blockhash()
            fresh_blockhash = blockhash_resp.value.blockhash

            old_msg = unsigned_tx.message
            new_msg = MessageV0(
                header=old_msg.header,
                account_keys=old_msg.account_keys,
                recent_blockhash=fresh_blockhash,
                instructions=old_msg.instructions,
                address_table_lookups=old_msg.address_table_lookups,
            )

            signed_tx = VersionedTransaction(new_msg, [mint_keypair, creator_wallet.keypair])

            # Send transaction
            logger.info("Sending token creation transaction...")
            #
            #
            #
            #Errors with launching token are likely past this line.
            #
            #
            #
            signature = await self.rpc_client.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, max_retries=3)
            )

            if signature.value:
                sig_str = str(signature.value)
                logger.info(f"✓ Token created! Signature: {sig_str}")
                logger.trade(f"Created {metadata.symbol} - Mint: {mint_address}")

                # Send notification
                notification_manager.notify(
                    "🪙 Token Created!",
                    f"{metadata.name} ({metadata.symbol})\nMint: {mint_address[:8]}...",
                    "normal",
                    "success"
                )

                return {
                    'success': True,
                    'signature': sig_str,
                    'mint': mint_address,
                    'metadataUri': metadata_uri,
                    'creator': str(creator_wallet.public_key),
                    'initialBuy': initial_buy_sol
                }
            else:
                logger.error("Failed to send transaction")
                return None

        except Exception as e:
            logger.error(f"Failed to create token: {e}")
            notification_manager.error_alert("Token Creation Failed", str(e))
            return None


# Global token creator instance
_token_creator: Optional['TokenCreator'] = None
_token_creator_client = None


def get_token_creator(rpc_client: AsyncClient) -> TokenCreator:
    """Get or create global token creator instance.
    Recreates if a different RPC client is supplied (e.g. after reconnect)."""
    global _token_creator, _token_creator_client
    if _token_creator is None or _token_creator_client is not rpc_client:
        _token_creator = TokenCreator(rpc_client)
        _token_creator_client = rpc_client
    return _token_creator
