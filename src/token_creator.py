"""
Token Creator for pump.fun
Handles token creation, metadata upload, and deployment.

IPFS upload supports two modes (set IPFS_MODE in .env):
  pumpfun  (default) — uploads via Pinata's IPFS API. (Originally hit
                      pump.fun's own /api/ipfs endpoint, but pump.fun no
                      longer allows direct metadata uploads there — that
                      endpoint is deprecated. Pinata is the replacement
                      PumpPortal's own docs now point to. Requires
                      PINATA_JWT to be set in .env.)
  local             — uploads via a locally-running IPFS daemon (ipfs daemon)
                      with a 2-stage reliability check:
                        Stage 1: pin locally + announce to the DHT
                        Stage 2: poll a public gateway until the content is
                                 reachable, then (and only then) send the
                                 on-chain transaction.
"""

import json
import asyncio
import httpx
from typing import Optional, Dict, Any
from pathlib import Path
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient

from .config import config
from .logger import logger
from .notifications import notification_manager
from .solana_tx import sign_and_send


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
        website: Optional[str] = None,
    ):
        self.name = name
        self.symbol = symbol
        self.description = description
        self.image_path = image_path
        self.twitter = twitter
        self.telegram = telegram
        self.website = website

    def to_form_data(self) -> Dict[str, Any]:
        """Convert to form data for pump.fun IPFS upload"""
        data = {
            "name": self.name,
            "symbol": self.symbol,
            "description": self.description,
            "showName": "true",
        }
        if self.twitter:
            data["twitter"] = self.twitter
        if self.telegram:
            data["telegram"] = self.telegram
        if self.website:
            data["website"] = self.website
        return data


class TokenCreator:
    """Handles token creation on pump.fun"""

    PINATA_UPLOAD_URL  = "https://uploads.pinata.cloud/v3/files"
    PINATA_GATEWAY_URL = "https://ipfs.io/ipfs"
    CREATE_TX_URL      = "https://pumpportal.fun/api/trade-local"

    def __init__(self, rpc_client: AsyncClient):
        self.rpc_client = rpc_client

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry-point — routes to the correct backend
    # ─────────────────────────────────────────────────────────────────────────

    async def upload_metadata_to_ipfs(
        self, metadata: TokenMetadata
    ) -> Optional[Dict[str, str]]:
        """
        Upload token image + metadata to IPFS.

        Routes to the local IPFS daemon when IPFS_MODE=local, otherwise uses
        the pump.fun /api/ipfs endpoint (default).

        Returns:
            {"metadataUri": "ipfs://..."} on success, None on failure.
        """
        logger.info(
            f"Uploading metadata for {metadata.name} ({metadata.symbol}) "
            f"[mode: {config.ipfs_mode}]..."
        )

        if config.dry_run_mode:
            logger.info("[DRY RUN] Would upload metadata to IPFS")
            return {"metadataUri": "ipfs://QmDRYRUNMODE123456789/metadata.json"}

        if config.ipfs_mode == "local":
            return await self._upload_metadata_local_ipfs(metadata)
        else:
            return await self._upload_metadata_pumpfun(metadata)

    # ─────────────────────────────────────────────────────────────────────────
    # Backend A — Pinata  (replaces the now-dead pump.fun /api/ipfs endpoint)
    # ─────────────────────────────────────────────────────────────────────────

    async def _upload_metadata_pumpfun(
        self, metadata: TokenMetadata
    ) -> Optional[Dict[str, str]]:
        """
        Upload image + metadata JSON to IPFS via Pinata.

        pump.fun's own /api/ipfs endpoint no longer accepts direct uploads
        (deprecated). Pinata is the replacement path PumpPortal's current
        docs use, so this mirrors that: upload the image, build the
        metadata JSON referencing the image's IPFS gateway URL, upload that,
        and return the metadata's gateway URL as metadataUri.

        Requires config.pinata_jwt (a Pinata JWT with upload scope) to be
        set. Get a free key at https://app.pinata.cloud/developers/api-keys
        """
        pinata_jwt = getattr(config, "pinata_jwt", None)
        if not pinata_jwt:
            logger.error(
                "PINATA_JWT is not configured. pump.fun's own /api/ipfs "
                "endpoint is deprecated, so a Pinata JWT is now required "
                "for IPFS_MODE=pumpfun. Add PINATA_JWT to your .env, or "
                "set IPFS_MODE=local to use your own IPFS daemon instead."
            )
            return None

        headers = {"Authorization": f"Bearer {pinata_jwt}"}

        try:
            image_path = Path(metadata.image_path).expanduser().resolve()
            if not image_path.exists():
                logger.error(f"Image file not found: {image_path}")
                return None

            file_content = image_path.read_bytes()
            file_name    = image_path.name
            mime_type    = self._get_mime_type(file_name)
            logger.info(f"[PINATA] Uploading image: {file_name} ({len(file_content):,} bytes)...")

            async with httpx.AsyncClient(timeout=60) as client:
                image_resp = await client.post(
                    self.PINATA_UPLOAD_URL,
                    headers=headers,
                    data={"network": "public"},
                    files={"file": (file_name, file_content, mime_type)},
                )

            if image_resp.status_code not in (200, 201):
                logger.error(f"[PINATA] Image upload failed {image_resp.status_code}: {image_resp.text}")
                return None

            image_cid = image_resp.json()["data"]["cid"]
            image_url = f"{self.PINATA_GATEWAY_URL}/{image_cid}"
            logger.info(f"  ✓ Image CID: {image_cid}")

            metadata_doc: Dict[str, Any] = {
                "name": metadata.name,
                "symbol": metadata.symbol,
                "description": metadata.description,
                "image": image_url,
                "showName": True,
            }
            if metadata.twitter:
                metadata_doc["twitter"] = metadata.twitter
            if metadata.telegram:
                metadata_doc["telegram"] = metadata.telegram
            if metadata.website:
                metadata_doc["website"] = metadata.website

            meta_bytes = json.dumps(metadata_doc).encode()
            logger.info(f"[PINATA] Uploading metadata JSON ({len(meta_bytes)} bytes)...")

            async with httpx.AsyncClient(timeout=60) as client:
                meta_resp = await client.post(
                    self.PINATA_UPLOAD_URL,
                    headers=headers,
                    data={"network": "public"},
                    files={"file": ("metadata.json", meta_bytes, "application/json")},
                )

            if meta_resp.status_code not in (200, 201):
                logger.error(f"[PINATA] Metadata upload failed {meta_resp.status_code}: {meta_resp.text}")
                return None

            meta_cid = meta_resp.json()["data"]["cid"]
            metadata_uri = f"{self.PINATA_GATEWAY_URL}/{meta_cid}"
            logger.info(f"✓ Pinata upload complete — URI: {metadata_uri}")
            return {"metadataUri": metadata_uri}

        except Exception as e:
            logger.error(f"[PINATA] upload exception: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Backend B — local IPFS daemon  (2-stage: pin+DHT then gateway verify)
    # ─────────────────────────────────────────────────────────────────────────

    async def _upload_metadata_local_ipfs(
        self, metadata: TokenMetadata
    ) -> Optional[Dict[str, str]]:
        """
        Upload image + metadata JSON to a locally-running IPFS daemon.

        Stage 1 — pin + DHT announce:
            After uploading each file the CID is pinned to the local node so
            it survives garbage collection, then a background task fires
            `routing/provide` to tell the DHT "I have this content".

        Stage 2 — gateway verification:
            Before proceeding the code polls https://ipfs.io/ipfs/<CID> until
            the content is reachable from the public internet (or times out).
            If the gateway check fails the method returns None, which causes
            create_token() to abort — no on-chain transaction is ever sent.
        """
        api = config.ipfs_local_api

        # ── 0. Sanity-check: is the daemon actually running? ─────────────────
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{api}/api/v0/id")
        except Exception:
            logger.error(f"[LOCAL IPFS] Daemon not reachable at {api}")
            logger.error("  → Start it with:  ipfs daemon")
            return None

        # ── 1. Upload image ───────────────────────────────────────────────────
        image_path = Path(metadata.image_path).expanduser().resolve()
        if not image_path.exists():
            logger.error(f"[LOCAL IPFS] Image not found: {image_path}")
            return None

        file_bytes = image_path.read_bytes()
        mime_type  = self._get_mime_type(image_path.name)
        logger.info(f"[LOCAL IPFS] Uploading image ({len(file_bytes):,} bytes)...")

        image_cid = await self._ipfs_add(api, file_bytes, image_path.name, mime_type)
        if not image_cid:
            return None
        logger.info(f"  ✓ Image CID: {image_cid}")

        # Stage 1 — pin + DHT announce image
        await self._ipfs_pin(api, image_cid, "image")
        asyncio.create_task(self._ipfs_dht_provide(api, image_cid, "image"))

        # Stage 2 — gateway verification for image
        if config.ipfs_gateway_verify:
            logger.info("[LOCAL IPFS] Stage 2 — verifying image on public gateway...")
            ok = await self._verify_on_gateway(image_cid, label="image")
            if not ok:
                logger.error(
                    "[LOCAL IPFS] ✗ Image not reachable on public gateway within "
                    f"{config.ipfs_gateway_timeout}s — transaction aborted."
                )
                return None

        # ── 2. Build and upload metadata JSON ────────────────────────────────
        metadata_doc: Dict[str, Any] = {
            "name":        metadata.name,
            "symbol":      metadata.symbol,
            "description": metadata.description,
            "image":       f"https://ipfs.io/ipfs/{image_cid}",
            "showName":    True,
        }
        if metadata.twitter:
            metadata_doc["twitter"]  = metadata.twitter
        if metadata.telegram:
            metadata_doc["telegram"] = metadata.telegram
        if metadata.website:
            metadata_doc["website"]  = metadata.website

        meta_bytes = json.dumps(metadata_doc, indent=2).encode()
        logger.info(f"[LOCAL IPFS] Uploading metadata JSON ({len(meta_bytes)} bytes)...")

        meta_cid = await self._ipfs_add(api, meta_bytes, "metadata.json", "application/json")
        if not meta_cid:
            return None
        logger.info(f"  ✓ Metadata CID: {meta_cid}")

        # Stage 1 — pin + DHT announce metadata
        await self._ipfs_pin(api, meta_cid, "metadata")
        asyncio.create_task(self._ipfs_dht_provide(api, meta_cid, "metadata"))

        # Stage 2 — gateway verification for metadata
        if config.ipfs_gateway_verify:
            logger.info("[LOCAL IPFS] Stage 2 — verifying metadata on public gateway...")
            ok = await self._verify_on_gateway(meta_cid, label="metadata")
            if not ok:
                logger.error(
                    "[LOCAL IPFS] ✗ Metadata not reachable on public gateway within "
                    f"{config.ipfs_gateway_timeout}s — transaction aborted."
                )
                return None

        metadata_uri = f"ipfs://{meta_cid}"
        logger.info(f"✓ Local IPFS upload complete — URI: {metadata_uri}")
        return {"metadataUri": metadata_uri}

    # ─────────────────────────────────────────────────────────────────────────
    # Local IPFS helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _ipfs_add(
        self, api: str, data: bytes, filename: str, mime_type: str
    ) -> Optional[str]:
        """
        POST data to /api/v0/add and return the CID string.
        The daemon returns one JSON object per file; we read the last one.
        """
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{api}/api/v0/add",
                    files={"file": (filename, data, mime_type)},
                )
            resp.raise_for_status()
            # The response may contain multiple newline-delimited JSON objects
            last_line = [l for l in resp.text.strip().splitlines() if l.strip()][-1]
            result = json.loads(last_line)
            return result["Hash"]
        except Exception as e:
            logger.error(f"[LOCAL IPFS] /api/v0/add failed for {filename}: {e}")
            return None

    async def _ipfs_pin(self, api: str, cid: str, label: str = "") -> None:
        """Pin a CID on the local node (Stage 1a)."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{api}/api/v0/pin/add?arg={cid}")
            resp.raise_for_status()
            logger.info(f"  ✓ Pinned {label} ({cid[:16]}...)")
        except Exception as e:
            logger.warning(f"  ⚠ Pin warning for {label} (non-fatal): {e}")

    async def _ipfs_dht_provide(self, api: str, cid: str, label: str = "") -> None:
        """
        Announce the CID to the DHT so peers know this node has it (Stage 1b).

        Runs as a fire-and-forget background task.  Uses routing/provide
        (Kubo ≥ 0.14); falls back to the legacy dht/provide endpoint.
        The endpoint streams NDJSON progress lines until complete — we read
        the response but don't block the main flow waiting for it.
        """
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                try:
                    resp = await client.post(
                        f"{api}/api/v0/routing/provide?arg={cid}&verbose=false"
                    )
                    resp.raise_for_status()
                except Exception:
                    resp = await client.post(
                        f"{api}/api/v0/dht/provide?arg={cid}&verbose=false"
                    )
                    resp.raise_for_status()
            logger.info(f"  ✓ DHT provide complete for {label} ({cid[:16]}...)")
        except Exception as e:
            logger.warning(f"  ⚠ DHT provide warning for {label} (non-fatal): {e}")

    async def _verify_on_gateway(
        self, cid: str, label: str = ""
    ) -> bool:
        """
        Stage 2: Poll https://ipfs.io/ipfs/<CID> until the content is
        reachable from the public internet, or until the configured timeout.

        Returns True if the gateway responds with HTTP < 400, False on timeout.
        """
        gateway_url = f"https://ipfs.io/ipfs/{cid}"
        timeout  = config.ipfs_gateway_timeout
        interval = config.ipfs_gateway_poll_interval
        elapsed  = 0.0
        attempt  = 0

        logger.info(
            f"  ⏳ Polling gateway for {label or cid[:16]} "
            f"(timeout: {timeout}s, every {interval}s)..."
        )

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            while elapsed < timeout:
                attempt += 1
                try:
                    resp = await client.head(gateway_url)
                    if resp.status_code < 400:
                        logger.info(
                            f"  ✓ {label} live on gateway after {elapsed:.0f}s "
                            f"(HTTP {resp.status_code}) — {gateway_url}"
                        )
                        return True
                    logger.info(
                        f"  [{attempt}] HTTP {resp.status_code} — "
                        f"retrying in {interval}s ({elapsed:.0f}/{timeout}s elapsed)"
                    )
                except httpx.TimeoutException:
                    logger.info(
                        f"  [{attempt}] Gateway timeout — "
                        f"retrying in {interval}s ({elapsed:.0f}/{timeout}s elapsed)"
                    )
                except Exception as e:
                    logger.info(
                        f"  [{attempt}] {e} — "
                        f"retrying in {interval}s ({elapsed:.0f}/{timeout}s elapsed)"
                    )

                wait = min(interval, timeout - elapsed)
                if wait <= 0:
                    break
                await asyncio.sleep(wait)
                elapsed += wait

        logger.error(
            f"  ✗ Gateway verification timed out after {timeout}s for "
            f"{label} — {gateway_url}"
        )
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_mime_type(self, filename: str) -> str:
        ext = Path(filename).suffix.lower()
        return {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".gif":  "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/png")

    # ─────────────────────────────────────────────────────────────────────────
    # Token creation (unchanged logic — just calls upload_metadata_to_ipfs)
    # ─────────────────────────────────────────────────────────────────────────

    async def create_token(
        self,
        creator_wallet,
        metadata: TokenMetadata,
        initial_buy_sol: float = 0.0,
        slippage_bps: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a token on pump.fun.

        The IPFS upload (and, in local mode, the 2-stage gateway verification)
        must succeed before any on-chain transaction is attempted.
        """
        try:
            logger.info(f"Creating token: {metadata.name} ({metadata.symbol})")

            ipfs_response = await self.upload_metadata_to_ipfs(metadata)
            if not ipfs_response:
                logger.error("IPFS upload/verification failed — transaction aborted.")
                return None

            metadata_uri = ipfs_response["metadataUri"]

            mint_keypair  = Keypair()
            mint_address  = str(mint_keypair.pubkey())
            logger.info(f"Token mint address: {mint_address}")

            if config.dry_run_mode:
                logger.info("[DRY RUN] Would create token on pump.fun")
                logger.info(f"[DRY RUN] Mint: {mint_address}")
                logger.info(f"[DRY RUN] Metadata URI: {metadata_uri}")
                if initial_buy_sol > 0:
                    logger.info(f"[DRY RUN] Initial buy: {initial_buy_sol} SOL")
                return {
                    "success":     True,
                    "signature":   "DRY_RUN_SIGNATURE_" + mint_address[:8],
                    "mint":        mint_address,
                    "metadataUri": metadata_uri,
                    "creator":     str(creator_wallet.public_key),
                    "initialBuy":  initial_buy_sol,
                }

            slippage_pct   = (slippage_bps or config.default_slippage_bps) / 100
            slippage_value = (
                int(slippage_pct)
                if float(slippage_pct).is_integer()
                else float(slippage_pct)
            )

            create_data = {
                "publicKey": str(creator_wallet.public_key),
                "action": "create",
                "tokenMetadata": {
                    "name": metadata.name,
                    "symbol": metadata.symbol,
                    "uri": metadata_uri,
                },
                "mint": mint_address,
                "denominatedInSol": "true",
                "amount": initial_buy_sol,
                "slippage": slippage_value,
                "priorityFee": 0.0005,
                "pool": "pump",
            }

            logger.debug(
                f"Sending create payload (mint={mint_address[:8]}…): {create_data}"
            )

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.CREATE_TX_URL,
                    headers={"Content-Type": "application/json"},
                    content=json.dumps(create_data),
                )

            if response.status_code != 200:
                try:
                    err = response.json()
                except Exception:
                    err = response.text
                logger.error(f"PumpPortal create failed {response.status_code}: {err}")
                return None

            # Deserialize, refresh blockhash, sign, send, and confirm —
            # shared pipeline (see solana_tx.py). Preserves the
            # blockhash-refresh-before-signing behavior exactly as before.
            logger.info("Sending token creation transaction...")
            result = await sign_and_send(
                self.rpc_client,
                response.content,
                signers=[mint_keypair, creator_wallet.keypair],
            )

            if result.success and result.confirmed:
                logger.info(f"✓ Token created! Signature: {result.signature}")
                logger.trade(f"Created {metadata.symbol} — Mint: {mint_address}")
                notification_manager.notify(
                    "🪙 Token Created!",
                    f"{metadata.name} ({metadata.symbol})\nMint: {mint_address[:8]}...",
                    "normal",
                    "success",
                )
                return {
                    "success":     True,
                    "signature":   result.signature,
                    "mint":        mint_address,
                    "metadataUri": metadata_uri,
                    "creator":     str(creator_wallet.public_key),
                    "initialBuy":  initial_buy_sol,
                }

            logger.error(f"Token creation failed or unconfirmed: {result.error}")
            return None

        except Exception as e:
            logger.error(f"Failed to create token: {e}")
            notification_manager.error_alert("Token Creation Failed", str(e))
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

_token_creator: Optional["TokenCreator"] = None
_token_creator_client = None


def get_token_creator(rpc_client: AsyncClient) -> TokenCreator:
    """Return the global TokenCreator, recreating it if the RPC client changed."""
    global _token_creator, _token_creator_client
    if _token_creator is None or _token_creator_client is not rpc_client:
        _token_creator = TokenCreator(rpc_client)
        _token_creator_client = rpc_client
    return _token_creator
