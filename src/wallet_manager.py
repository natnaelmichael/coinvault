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
from rich.console import Console
from rich.table import Table

from .config import config


console = Console()


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
        """Create wallet from base58 encoded private key"""
        try:
            key_bytes = base58.b58decode(private_key)
            keypair = Keypair.from_bytes(key_bytes)
            return cls(keypair, label)
        except Exception as e:
            raise ValueError(f"Invalid private key: {e}")
    
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
        console.print("[cyan]Initializing Wallet Manager...[/cyan]")
        
        # Initialize RPC client
        self.rpc_client = AsyncClient(config.rpc_url)
        
        # Load dev wallet
        if config.dev_wallet_key:
            try:
                self.dev_wallet = Wallet.from_private_key(config.dev_wallet_key, "Dev Wallet")
                console.print(f"[green]✓[/green] Dev wallet loaded: {str(self.dev_wallet.public_key)[:12]}...")
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to load dev wallet: {e}")
        else:
            console.print("[yellow]⚠[/yellow] DEV_WALLET_PRIVATE_KEY not set in .env")
        
        # Load fund wallets from .env (FUND_WALLET_PRIVATE_KEYS=key1,key2,key3)
        if not config.fund_wallet_keys:
            console.print("[yellow]⚠[/yellow] No FUND_WALLET_PRIVATE_KEYS found in .env")
        else:
            self.fund_wallets = []  # Reset to avoid duplicates on re-init
            for i, key in enumerate(config.fund_wallet_keys, 1):
                try:
                    wallet = Wallet.from_private_key(key, f"Fund Wallet {i}")
                    self.fund_wallets.append(wallet)
                    console.print(f"[green]✓[/green] Fund wallet {i} loaded: {str(wallet.public_key)[:12]}...")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to load fund wallet {i}: {e}")
        
        console.print(f"[green]✓[/green] Loaded {len(self.fund_wallets)} fund wallet(s)")
        
        # Fetch initial balances
        await self.update_all_balances()
    
    async def update_all_balances(self):
        """Update SOL balances for all wallets"""
        tasks = []
        
        if self.dev_wallet:
            tasks.append(self._update_wallet_balance(self.dev_wallet))
        
        for wallet in self.fund_wallets:
            tasks.append(self._update_wallet_balance(wallet))
        
        if tasks:
            await asyncio.gather(*tasks)
    
    async def _update_wallet_balance(self, wallet: Wallet):
        """Update balance for a single wallet"""
        try:
            response = await self.rpc_client.get_balance(wallet.public_key, commitment=Confirmed)
            if response.value is not None:
                wallet.balance_sol = response.value / 1e9  # Convert lamports to SOL
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Failed to fetch balance for {wallet}: {e}")
    
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
        
        console.print(table)
    
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
            console.print("[red]✗[/red] Dev wallet not configured")
            return False
        
        if not self.fund_wallets:
            console.print("[red]✗[/red] No fund wallets configured")
            return False
        
        total_needed = amount_per_wallet * len(self.fund_wallets)
        
        # Check if dev wallet has enough balance
        if self.dev_wallet.balance_sol < total_needed + 0.01:  # +0.01 for fees
            console.print(f"[red]✗[/red] Insufficient balance in dev wallet")
            console.print(f"    Need: {total_needed:.4f} SOL + fees")
            console.print(f"    Have: {self.dev_wallet.balance_sol:.4f} SOL")
            return False
        
        console.print(f"[cyan]Distributing {amount_per_wallet:.4f} SOL to {len(self.fund_wallets)} wallets...[/cyan]")
        
        if config.dry_run_mode:
            console.print("[yellow]🔴 DRY RUN MODE - No actual transfers will be made[/yellow]")
            for wallet in self.fund_wallets:
                console.print(f"    Would send {amount_per_wallet:.4f} SOL to {wallet.label}")
            return True

        console.print(f"\n[bold cyan]Distributing {amount_per_wallet:.4f} SOL to {len(self.fund_wallets)} wallets...[/bold cyan]\n")

        successful = 0
        failed = 0

        for wallet in self.fund_wallets:
            result = await self._transfer_sol(self.dev_wallet, wallet, amount_per_wallet)
            if result:
                successful += 1
            else:
                failed += 1

        console.print(f"\n{'─'*60}")
        console.print(f"[bold]Distribution Summary[/bold]")
        console.print(f"  Successful: [green]{successful}[/green]  |  Failed: [red]{failed}[/red]")
        console.print(f"  Total sent: [green]{amount_per_wallet * successful:.4f} SOL[/green]")
        console.print(f"{'─'*60}\n")

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

        # Print pending line before sending
        console.print(
            f"  [dim]{timestamp}[/dim]  "
            f"[cyan]{to_wallet.label}[/cyan]  "
            f"[dim]{str(to_wallet.public_key)[:20]}...[/dim]  "
            f"[yellow]{amount_sol:.4f} SOL[/yellow]  ",
            end=""
        )

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
            console.print(f"[dim]sig: {sig_str[:20]}...[/dim]  [bold green]✓ OK[/bold green]")
            return True

        except Exception as e:
            console.print(f"[bold red]✗ FAILED[/bold red]  [dim red]{e}[/dim red]")
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
        console.print(f"[green]✓[/green] Added {wallet.label}: {str(wallet.public_key)[:12]}...")
        
        if not private_key:
            console.print(f"[yellow]⚠[/yellow] Save this private key: {wallet.get_private_key_base58()}")
        
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
            console.print(f"[yellow]Removed {removed.label}[/yellow]")
            
            # Re-label remaining wallets
            for i, wallet in enumerate(self.fund_wallets, 1):
                wallet.label = f"Fund Wallet {i}"
            
            return True
        else:
            console.print(f"[red]✗[/red] Invalid wallet index: {index}")
            return False
    
    async def close(self):
        """Clean up resources"""
        if self.rpc_client:
            await self.rpc_client.close()


# Global wallet manager instance
wallet_manager = WalletManager()
