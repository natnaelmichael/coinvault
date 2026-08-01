"""
Wallet Manager
Handles wallet creation, management, and balance tracking
"""

from typing import List, Dict, Optional
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.message import Message
from solders.transaction import Transaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
import base58
import asyncio
from rich.table import Table

from .config import config
from .logger import logger


class Wallet:
    """Represents a single Solana wallet"""
    
    def __init__(self, keypair: Keypair, label: str = ""):
        self.keypair = keypair
        self.public_key = keypair.pubkey()
        self.label = label
        self.balance_sol = 0.0
        self.token_balances: Dict[str, float] = {}
    
    def __str__(self):
        return f"{self.label or 'Wallet'} ({str(self.public_key)[:8]}...)"
    
    @classmethod
    def from_private_key(cls, private_key: str, label: str = "") -> 'Wallet':
        """Create wallet from base58 encoded private key.

        Expects the standard 64-byte Solana keypair (secret key || public key)
        encoded as base58 — the format exported by most Solana wallets and
        Phantom's "Export Private Key" function.
        """
        if not private_key or not private_key.strip():
            raise ValueError(
                "Private key is empty. "
                "Set DEV_WALLET_PRIVATE_KEY (or FUND_WALLET_PRIVATE_KEYS) in your .env file."
            )
        stripped = private_key.strip()
        try:
            key_bytes = base58.b58decode(stripped)
        except Exception as e:
            raise ValueError(
                f"Private key is not valid base58 ({e}). "
                "Make sure you copied the full key without extra spaces or line breaks."
            )
        if len(key_bytes) != 64:
            raise ValueError(
                f"Private key decoded to {len(key_bytes)} bytes — expected 64. "
                "Solana private keys are 64 bytes (secret key + public key). "
                "If your key is 32 bytes, it may be a seed-only format not supported here."
            )
        try:
            keypair = Keypair.from_bytes(key_bytes)
        except Exception as e:
            raise ValueError(f"Could not construct keypair from key bytes: {e}")
        return cls(keypair, label)
    
    @classmethod
    def generate_new(cls, label: str = "") -> 'Wallet':
        """Generate a new random wallet"""
        keypair = Keypair()
        return cls(keypair, label)
    
    def get_private_key_base58(self) -> str:
        """Export private key as base58 string"""
        return base58.b58encode(bytes(self.keypair)).decode('utf-8')


class WalletManager:
    """Manages all wallets (dev + fund wallets)"""
    
    def __init__(self):
        self.dev_wallet: Optional[Wallet] = None
        self.fund_wallets: List[Wallet] = []
        self.rpc_client: Optional[AsyncClient] = None
    
    async def initialize(self):
        """Initialize wallet manager with configured wallets"""
        logger.info("Initializing Wallet Manager...")

        # Initialize RPC client
        self.rpc_client = AsyncClient(config.rpc_url)

        # Load dev wallet
        if config.dev_wallet_key:
            try:
                self.dev_wallet = Wallet.from_private_key(config.dev_wallet_key, "Dev Wallet")
                logger.info(f"✓ Dev wallet loaded: {str(self.dev_wallet.public_key)[:12]}...")
            except Exception as e:
                logger.error(f"✗ Failed to load dev wallet: {e}")
        else:
            logger.warning("DEV_WALLET_PRIVATE_KEY not set in .env")

        # Load fund wallets from .env (FUND_WALLET_PRIVATE_KEYS=key1,key2,key3)
        if not config.fund_wallet_keys:
            logger.warning("No FUND_WALLET_PRIVATE_KEYS found in .env")
        else:
            self.fund_wallets = []  # Reset to avoid duplicates on re-init
            for i, key in enumerate(config.fund_wallet_keys, 1):
                try:
                    wallet = Wallet.from_private_key(key, f"Fund Wallet {i}")
                    self.fund_wallets.append(wallet)
                    logger.info(f"✓ Fund wallet {i} loaded: {str(wallet.public_key)[:12]}...")
                except Exception as e:
                    logger.warning(f"Failed to load fund wallet {i}: {e}")

        logger.info(f"✓ Loaded {len(self.fund_wallets)} fund wallet(s)")
        
        # Fetch initial balances
        await self.update_all_balances()
    
    async def update_all_balances(self):
        """Update SOL balances for all wallets.

        Requests are staggered by 80 ms each so that a bank of wallets doesn't
        hit the public RPC (api.mainnet-beta.solana.com) rate-limit all at once.
        Each individual fetch retries up to 3 times with exponential backoff
        before giving up, so transient 429s are handled transparently.
        """
        wallets: list = []
        if self.dev_wallet:
            wallets.append(self.dev_wallet)
        wallets.extend(self.fund_wallets)

        async def _staggered(wallet: "Wallet", index: int) -> None:
            if index > 0:
                await asyncio.sleep(index * 0.08)   # 80 ms stagger per wallet
            await self._update_wallet_balance(wallet)

        if wallets:
            await asyncio.gather(*(_staggered(w, i) for i, w in enumerate(wallets)))

    async def _update_wallet_balance(self, wallet: "Wallet") -> None:
        """Fetch and store the SOL balance for one wallet.

        Retries up to 3 times with 0.5 s → 1.0 s → 1.5 s backoff so that
        public-RPC rate-limit errors (which silently returned 0 before) are
        recovered automatically.  On permanent failure the previous balance is
        preserved and a warning is logged.
        """
        max_attempts = 3
        last_err: Exception | None = None

        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    await asyncio.sleep(0.5 * attempt)   # 0.5 s, 1.0 s
                response = await self.rpc_client.get_balance(
                    wallet.public_key, commitment=Confirmed
                )
                if response.value is not None:
                    wallet.balance_sol = response.value / 1_000_000_000
                return   # success — exit retry loop
            except Exception as exc:
                last_err = exc

        logger.warning(
            f"Balance fetch failed for {wallet} after {max_attempts} attempts: {last_err}"
        )
    
    def get_total_balance(self) -> float:
        """Get total SOL balance across all wallets"""
        total = 0.0
        if self.dev_wallet:
            total += self.dev_wallet.balance_sol
        for wallet in self.fund_wallets:
            total += wallet.balance_sol
        return total
    
    def display_balances(self):
        """Display formatted table of wallet balances"""
        table = Table(title="💰 Wallet Balances", show_header=True, header_style="bold magenta")
        table.add_column("Label", style="cyan", width=20)
        table.add_column("Address", style="white", width=44)
        table.add_column("Balance (SOL)", justify="right", style="green")
        
        if self.dev_wallet:
            table.add_row(
                self.dev_wallet.label,
                str(self.dev_wallet.public_key),
                f"{self.dev_wallet.balance_sol:.4f}"
            )
        
        for wallet in self.fund_wallets:
            table.add_row(
                wallet.label,
                str(wallet.public_key),
                f"{wallet.balance_sol:.4f}"
            )
        
        # Add total row
        table.add_row(
            "[bold]TOTAL[/bold]",
            "",
            f"[bold]{self.get_total_balance():.4f}[/bold]",
            style="bold yellow"
        )
        
        from rich.console import Console as _Console
        _Console().print(table)
    
    async def distribute_sol(self, amount_per_wallet: float, from_dev: bool = True) -> bool:
        """
        Distribute SOL from dev wallet to all fund wallets
        
        Args:
            amount_per_wallet: Amount of SOL to send to each fund wallet
            from_dev: Whether to distribute from dev wallet (vs manual source)
        
        Returns:
            True if distribution was successful
        """
        if not self.dev_wallet:
            logger.error("✗ Dev wallet not configured")
            return False

        if not self.fund_wallets:
            logger.error("✗ No fund wallets configured")
            return False

        total_needed = amount_per_wallet * len(self.fund_wallets)

        if self.dev_wallet.balance_sol < total_needed + 0.01:  # +0.01 for fees
            logger.error(
                f"✗ Insufficient balance in dev wallet — "
                f"need {total_needed:.4f} SOL + fees, "
                f"have {self.dev_wallet.balance_sol:.4f} SOL"
            )
            return False

        logger.info(f"Distributing {amount_per_wallet:.4f} SOL to {len(self.fund_wallets)} wallets...")

        if config.dry_run_mode:
            logger.info("[DRY RUN] No actual transfers will be made")
            for wallet in self.fund_wallets:
                logger.info(f"  Would send {amount_per_wallet:.4f} SOL to {wallet.label}")
            return True

        successful = 0
        failed = 0

        for wallet in self.fund_wallets:
            result = await self._transfer_sol(self.dev_wallet, wallet, amount_per_wallet)
            if result:
                successful += 1
            else:
                failed += 1

        logger.info(
            f"Distribution summary — "
            f"successful: {successful}, failed: {failed}, "
            f"total sent: {amount_per_wallet * successful:.4f} SOL"
        )

        await self.update_all_balances()
        return failed == 0

    async def _transfer_sol(self, from_wallet: 'Wallet', to_wallet: 'Wallet', amount_sol: float) -> bool:
        """
        Transfer a fixed amount of SOL from one wallet to another.

        Builds a legacy SystemProgram.transfer transaction, signs it with
        from_wallet's keypair, and sends it. Prints a detailed status line
        with timestamp, destination, amount, and pass/fail indicator.
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        lamports = int(amount_sol * 1e9)

        try:
            blockhash_resp = await self.rpc_client.get_latest_blockhash()
            recent_blockhash = blockhash_resp.value.blockhash

            ix = transfer(TransferParams(
                from_pubkey=from_wallet.public_key,
                to_pubkey=to_wallet.public_key,
                lamports=lamports,
            ))
            msg = Message.new_with_blockhash(
                [ix],
                from_wallet.public_key,
                recent_blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([from_wallet.keypair], recent_blockhash)

            sig_resp = await self.rpc_client.send_raw_transaction(
                bytes(tx),
                opts=TxOpts(skip_preflight=False, max_retries=3),
            )

            sig_str = str(sig_resp.value)
            logger.info(
                f"✓ {timestamp}  {to_wallet.label}  "
                f"{str(to_wallet.public_key)[:20]}...  "
                f"{amount_sol:.4f} SOL  sig: {sig_str[:20]}..."
            )
            return True

        except Exception as e:
            logger.error(f"✗ Transfer to {to_wallet.label} FAILED: {e}")
            return False
    
    def add_fund_wallet(self, private_key: Optional[str] = None) -> Wallet:
        """
        Add a new fund wallet
        
        Args:
            private_key: Optional private key. If not provided, generates new wallet
        
        Returns:
            The newly created Wallet object
        """
        wallet_num = len(self.fund_wallets) + 1
        
        if private_key:
            wallet = Wallet.from_private_key(private_key, f"Fund Wallet {wallet_num}")
        else:
            wallet = Wallet.generate_new(f"Fund Wallet {wallet_num}")
        
        self.fund_wallets.append(wallet)
        logger.info(f"✓ Added {wallet.label}: {str(wallet.public_key)[:12]}...")

        if not private_key:
            logger.warning(f"Save this private key: {wallet.get_private_key_base58()}")
        
        return wallet
    
    def remove_fund_wallet(self, index: int) -> bool:
        """
        Remove a fund wallet by index
        
        Args:
            index: Index of the wallet to remove (0-based)
        
        Returns:
            True if wallet was removed successfully
        """
        if 0 <= index < len(self.fund_wallets):
            removed = self.fund_wallets.pop(index)
            logger.info(f"Removed {removed.label}")

            # Re-label remaining wallets
            for i, wallet in enumerate(self.fund_wallets, 1):
                wallet.label = f"Fund Wallet {i}"

            return True
        else:
            logger.error(f"✗ Invalid wallet index: {index}")
            return False
    
    async def close(self):
        """Clean up resources"""
        if self.rpc_client:
            await self.rpc_client.close()


# Global wallet manager instance
wallet_manager = WalletManager()
