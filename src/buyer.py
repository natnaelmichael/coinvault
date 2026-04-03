"""
Buyer Module
Handles buying tokens on pump.fun with multiple wallets
"""

import asyncio
import httpx
from typing import List, Optional, Dict, Any
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts

from .config import config
from .logger import logger
from .notifications import notification_manager


class BuyResult:
    """Result of a buy operation"""
    
    def __init__(
        self,
        wallet,
        success: bool,
        signature: Optional[str] = None,
        amount_sol: float = 0.0,
        tokens_received: float = 0.0,
        error: Optional[str] = None
    ):
        self.wallet = wallet
        self.success = success
        self.signature = signature
        self.amount_sol = amount_sol
        self.tokens_received = tokens_received
        self.error = error


class TokenBuyer:
    """Handles token buying operations"""
    
    BUY_API_URL = "https://pumpportal.fun/api/trade-local"
    
    def __init__(self, rpc_client: AsyncClient):
        self.rpc_client = rpc_client
    
    async def buy_token(
        self,
        wallet,
        token_mint: str,
        amount_sol: float,
        slippage_bps: Optional[int] = None
    ) -> BuyResult:
        """
        Buy tokens with a single wallet
        
        Args:
            wallet: Wallet to buy with
            token_mint: Token mint address
            amount_sol: Amount of SOL to spend
            slippage_bps: Slippage in basis points
        
        Returns:
            BuyResult object
        """
        try:
            logger.info(f"{wallet.label}: Buying {amount_sol} SOL worth of {token_mint[:8]}...")
            
            if config.dry_run_mode:
                logger.info(f"[DRY RUN] {wallet.label} would buy {amount_sol} SOL")
                return BuyResult(
                    wallet=wallet,
                    success=True,
                    signature=f"DRY_RUN_BUY_{wallet.public_key}",
                    amount_sol=amount_sol,
                    tokens_received=amount_sol * 1000000  # Mock tokens
                )
            
            # Prepare buy request
            buy_data = {
                'publicKey': str(wallet.public_key),
                'action': 'buy',
                'mint': token_mint,
                'denominatedInSol': 'true',
                'amount': amount_sol,
                'slippage': (slippage_bps or config.default_slippage_bps) / 100,
                'priorityFee': 0.0005,
                'pool': 'pump'
            }
            
            # Request transaction from API.
            # Using httpx.AsyncClient so this await yields to the event loop
            # while waiting, allowing other wallet coroutines to run concurrently.
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.BUY_API_URL,
                    json=buy_data,
                    headers={'Content-Type': 'application/json'}
                )

            if response.status_code != 200:
                error_msg = f"API error: {response.status_code} - {response.text}"
                logger.error(f"{wallet.label}: {error_msg}")
                return BuyResult(wallet=wallet, success=False, error=error_msg)
            
            # Parse transaction, inject a fresh blockhash, and sign.
            # The blockhash embedded in PumpPortal's returned transaction expires
            # quickly — fetching a fresh one before signing prevents
            # "Blockhash not found" preflight failures.
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

            signed_tx = VersionedTransaction(new_msg, [wallet.keypair])
            
            # Send transaction — skip_preflight avoids simulation using a cached
            # blockhash state that can disagree with the actual network.
            signature = await self.rpc_client.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, max_retries=3)
            )
            
            if signature.value:
                sig_str = str(signature.value)
                logger.info(f"✓ {wallet.label}: Buy successful! Sig: {sig_str[:16]}...")
                logger.trade(f"{wallet.label} bought {amount_sol} SOL worth")
                
                return BuyResult(
                    wallet=wallet,
                    success=True,
                    signature=sig_str,
                    amount_sol=amount_sol
                )
            else:
                error_msg = "Transaction failed"
                logger.error(f"{wallet.label}: {error_msg}")
                return BuyResult(wallet=wallet, success=False, error=error_msg)
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{wallet.label}: Buy failed - {error_msg}")
            return BuyResult(wallet=wallet, success=False, error=error_msg)
    
    async def bundle_buy(
        self,
        wallets: List,
        token_mint: str,
        amount_per_wallet_sol: float,
        slippage_bps: Optional[int] = None,
        delay_ms: int = 0
    ) -> List[BuyResult]:
        """
        Buy tokens with multiple wallets simultaneously
        
        Args:
            wallets: List of wallets to buy with
            token_mint: Token mint address
            amount_per_wallet_sol: Amount of SOL per wallet
            slippage_bps: Slippage in basis points
            delay_ms: Delay between buys in milliseconds (0 for simultaneous)
        
        Returns:
            List of BuyResult objects
        """
        logger.info(f"🔄 Bundle buying {token_mint[:8]}... with {len(wallets)} wallets")
        logger.info(f"   Amount per wallet: {amount_per_wallet_sol} SOL")
        logger.info(f"   Total: {amount_per_wallet_sol * len(wallets)} SOL")
        
        # Execute buys — simultaneous if no delay, staggered if delay is set.
        # NOTE: Sleeping between task *creation* has no effect when using gather(),
        # because gather() fires all coroutines at once regardless. The delay must
        # happen between actual awaited executions.
        if delay_ms == 0:
            # True parallel: all wallets hit the API at the same time
            tasks = [
                self.buy_token(wallet, token_mint, amount_per_wallet_sol, slippage_bps)
                for wallet in wallets
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Staggered: await each buy individually with a real sleep in between
            results = []
            for i, wallet in enumerate(wallets):
                try:
                    result = await self.buy_token(wallet, token_mint, amount_per_wallet_sol, slippage_bps)
                    results.append(result)
                except Exception as e:
                    results.append(e)
                if i < len(wallets) - 1:  # No sleep after the last wallet
                    await asyncio.sleep(delay_ms / 1000.0)
        
        # Process results
        buy_results = []
        successful = 0
        failed = 0
        total_spent = 0.0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Buy task failed: {result}")
                failed += 1
            elif isinstance(result, BuyResult):
                buy_results.append(result)
                if result.success:
                    successful += 1
                    total_spent += result.amount_sol
                else:
                    failed += 1
        
        # Log summary
        logger.info(f"\n{'='*60}")
        logger.info(f"BUNDLE BUY COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total wallets: {len(wallets)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total spent: {total_spent} SOL")
        logger.info(f"{'='*60}\n")
        
        # Send notification
        if successful > 0:
            notification_manager.notify(
                "🔄 Bundle Buy Complete",
                f"{successful}/{len(wallets)} successful\n{total_spent:.4f} SOL spent",
                "normal",
                "success"
            )
        
        return buy_results


# Global buyer instance
_token_buyer = None
_token_buyer_client = None


def get_token_buyer(rpc_client: AsyncClient) -> TokenBuyer:
    """Get or create global token buyer instance.
    Recreates if a different RPC client is supplied (e.g. after reconnect)."""
    global _token_buyer, _token_buyer_client
    if _token_buyer is None or _token_buyer_client is not rpc_client:
        _token_buyer = TokenBuyer(rpc_client)
        _token_buyer_client = rpc_client
    return _token_buyer
