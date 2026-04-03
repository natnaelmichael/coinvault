"""
Seller Module
Handles selling tokens and withdrawing funds
"""

import asyncio
import httpx
from typing import List, Optional, Dict, Any
from solders.transaction import VersionedTransaction, Transaction
from solders.message import MessageV0, Message
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.hash import Hash
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TxOpts
from solana.rpc.commitment import Confirmed

from .config import config
from .logger import logger
from .notifications import notification_manager

# Rent-exempt minimum for a plain account (0.00089088 SOL as of 2024)
RENT_EXEMPT_MINIMUM_LAMPORTS = 890880


class SellResult:
    """Result of a sell operation"""
    
    def __init__(
        self,
        wallet,
        success: bool,
        signature: Optional[str] = None,
        tokens_sold: float = 0.0,
        sol_received: float = 0.0,
        error: Optional[str] = None
    ):
        self.wallet = wallet
        self.success = success
        self.signature = signature
        self.tokens_sold = tokens_sold
        self.sol_received = sol_received
        self.error = error


class TokenSeller:
    """Handles token selling operations"""
    
    SELL_API_URL = "https://pumpportal.fun/api/trade-local"
    
    def __init__(self, rpc_client: AsyncClient):
        self.rpc_client = rpc_client
    
    async def _get_token_balance(self, wallet, token_mint: str) -> Optional[float]:
        """
        Fetch the SPL token balance for a wallet.

        Uses the getTokenAccountsByOwner RPC call to find the associated token
        account and return its UI amount (human-readable, already decimal-adjusted).
        Returns None if no token account exists or the call fails.
        """
        try:
            from solders.pubkey import Pubkey
            from spl.token.constants import TOKEN_PROGRAM_ID

            mint_pubkey = Pubkey.from_string(token_mint)
            response = await self.rpc_client.get_token_accounts_by_owner(
                wallet.public_key,
                {"mint": mint_pubkey},
            )
            accounts = response.value
            if not accounts:
                logger.warning(f"{wallet.label}: No token account found for {token_mint[:8]}...")
                return None

            # Take the first (and normally only) associated token account
            account_pubkey = accounts[0].pubkey
            balance_resp = await self.rpc_client.get_token_account_balance(account_pubkey)
            ui_amount = balance_resp.value.ui_amount
            if ui_amount is None:
                return 0.0
            return float(ui_amount)

        except Exception as e:
            logger.error(f"{wallet.label}: Failed to fetch token balance — {e}")
            return None

    async def sell_token(
        self,
        wallet,
        token_mint: str,
        amount_tokens: Optional[float] = None,
        percentage: Optional[int] = None,
        slippage_bps: Optional[int] = None
    ) -> SellResult:
        """
        Sell tokens from a single wallet
        
        Args:
            wallet: Wallet to sell from
            token_mint: Token mint address
            amount_tokens: Specific amount to sell (None for all)
            percentage: Percentage to sell (1-100, None for all)
            slippage_bps: Slippage in basis points
        
        Returns:
            SellResult object
        """
        try:
            sell_type = "all tokens"
            if amount_tokens:
                sell_type = f"{amount_tokens} tokens"
            elif percentage:
                sell_type = f"{percentage}% of tokens"
            
            logger.info(f"{wallet.label}: Selling {sell_type} of {token_mint[:8]}...")
            
            if config.dry_run_mode:
                logger.info(f"[DRY RUN] {wallet.label} would sell {sell_type}")
                return SellResult(
                    wallet=wallet,
                    success=True,
                    signature=f"DRY_RUN_SELL_{wallet.public_key}",
                    tokens_sold=amount_tokens or 1000000,
                    sol_received=0.5
                )

            # --- Resolve percentage to a concrete token quantity ---
            # PumpPortal has no native percentage field; we must fetch the wallet's
            # token balance and compute the exact amount to sell.
            if percentage and not amount_tokens:
                resolved_amount = await self._get_token_balance(wallet, token_mint)
                if resolved_amount is None:
                    error_msg = "Could not fetch token balance for percentage sell"
                    logger.error(f"{wallet.label}: {error_msg}")
                    return SellResult(wallet=wallet, success=False, error=error_msg)
                amount_tokens = resolved_amount * (percentage / 100.0)
                logger.info(
                    f"{wallet.label}: {percentage}% of {resolved_amount:.2f} tokens "
                    f"= {amount_tokens:.2f} tokens"
                )
            
            # Prepare sell request
            sell_data = {
                'publicKey': str(wallet.public_key),
                'action': 'sell',
                'mint': token_mint,
                'denominatedInSol': 'false',
                'slippage': (slippage_bps or config.default_slippage_bps) / 100,
                'priorityFee': 0.0005,
                'pool': 'pump'
            }
            
            # Add amount — by this point percentage has already been resolved to
            # amount_tokens above, so we only need two branches here.
            if amount_tokens:
                sell_data['amount'] = amount_tokens
            # If neither is set, omit 'amount' entirely → PumpPortal sells all tokens

            # Request transaction from API.
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.SELL_API_URL,
                    json=sell_data,
                    headers={'Content-Type': 'application/json'}
                )

            if response.status_code != 200:
                error_msg = f"API error: {response.status_code} - {response.text}"
                logger.error(f"{wallet.label}: {error_msg}")
                return SellResult(wallet=wallet, success=False, error=error_msg)

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
                logger.info(f"✓ {wallet.label}: Sell successful! Sig: {sig_str[:16]}...")
                logger.trade(f"{wallet.label} sold {sell_type}")
                
                return SellResult(
                    wallet=wallet,
                    success=True,
                    signature=sig_str,
                    tokens_sold=amount_tokens or 0
                )
            else:
                error_msg = "Transaction failed"
                logger.error(f"{wallet.label}: {error_msg}")
                return SellResult(wallet=wallet, success=False, error=error_msg)
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{wallet.label}: Sell failed - {error_msg}")
            return SellResult(wallet=wallet, success=False, error=error_msg)

    async def bundle_sell(
        self,
        wallets: List,
        token_mint: str,
        percentage: Optional[int] = None,
        slippage_bps: Optional[int] = None,
        delay_ms: int = 0
    ) -> List[SellResult]:
        """
        Sell tokens from multiple wallets

        Args:
            wallets: List of wallets to sell from
            token_mint: Token mint address
            percentage: Percentage of tokens to sell from each wallet (None = all)
            slippage_bps: Slippage in basis points
            delay_ms: Delay between sells in milliseconds (0 for simultaneous)

        Returns:
            List of SellResult objects
        """
        logger.info(f"💸 Bundle selling {token_mint[:8]}... from {len(wallets)} wallets")

        if delay_ms == 0:
            tasks = [
                self.sell_token(wallet, token_mint, percentage=percentage, slippage_bps=slippage_bps)
                for wallet in wallets
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = []
            for i, wallet in enumerate(wallets):
                try:
                    result = await self.sell_token(
                        wallet, token_mint, percentage=percentage, slippage_bps=slippage_bps
                    )
                    results.append(result)
                except Exception as e:
                    results.append(e)
                if i < len(wallets) - 1:
                    await asyncio.sleep(delay_ms / 1000.0)

        # Process results
        sell_results = []
        successful = 0
        failed = 0
        total_sol_received = 0.0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Sell task failed: {result}")
                failed += 1
            elif isinstance(result, SellResult):
                sell_results.append(result)
                if result.success:
                    successful += 1
                    total_sol_received += result.sol_received
                else:
                    failed += 1

        # Log summary
        logger.info(f"\n{'='*60}")
        logger.info(f"BUNDLE SELL COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total wallets: {len(wallets)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total SOL received: {total_sol_received:.4f}")
        logger.info(f"{'='*60}\n")

        if successful > 0:
            notification_manager.notify(
                "💸 Bundle Sell Complete",
                f"{successful}/{len(wallets)} successful\n{total_sol_received:.4f} SOL received",
                "normal",
                "success"
            )

        return sell_results

    async def withdraw_all_sol(
        self,
        from_wallets: List,
        to_wallet,
        leave_rent: bool = True
    ) -> Dict[str, Any]:
        """
        Withdraw all SOL from fund wallets to dev wallet.

        Builds one SystemProgram.transfer transaction per fund wallet,
        signs it with that wallet's keypair, and sends them all in
        parallel. Each transfer leaves behind RENT_EXEMPT_MINIMUM_LAMPORTS
        when leave_rent=True so the account stays alive.

        Args:
            from_wallets: Wallets to withdraw from
            to_wallet: Wallet to withdraw to (dev wallet)
            leave_rent: Leave rent-exempt minimum so the account stays open

        Returns:
            Summary dict with keys: success, total_withdrawn, results, dry_run
        """
        logger.info(f"🔄 Withdrawing SOL from {len(from_wallets)} wallets to {to_wallet.label}")

        if config.dry_run_mode:
            logger.info("[DRY RUN] Would withdraw all SOL to dev wallet")
            total = sum(w.balance_sol for w in from_wallets)
            logger.info(f"[DRY RUN] Total to withdraw: {total:.4f} SOL")
            return {'success': True, 'total_withdrawn': total, 'results': [], 'dry_run': True}

        tasks = [
            self._withdraw_single_wallet(wallet, to_wallet, leave_rent)
            for wallet in from_wallets
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful, failed = 0, 0
        total_withdrawn = 0.0
        result_list = []

        for wallet, result in zip(from_wallets, results):
            if isinstance(result, Exception):
                logger.error(f"{wallet.label}: Withdrawal raised exception — {result}")
                failed += 1
                result_list.append({'wallet': wallet.label, 'success': False, 'error': str(result)})
            elif result.get('success'):
                successful += 1
                total_withdrawn += result['amount_sol']
                result_list.append(result)
            else:
                failed += 1
                result_list.append(result)

        logger.info(f"\n{'='*60}")
        logger.info(f"WITHDRAW COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Successful: {successful}  |  Failed: {failed}")
        logger.info(f"Total withdrawn: {total_withdrawn:.6f} SOL")
        logger.info(f"{'='*60}\n")

        if successful > 0:
            notification_manager.notify(
                "💰 Withdrawal Complete",
                f"{successful}/{len(from_wallets)} wallets\n{total_withdrawn:.4f} SOL → {to_wallet.label}",
                "normal",
                "success"
            )

        return {
            'success': successful > 0,
            'total_withdrawn': total_withdrawn,
            'results': result_list,
            'dry_run': False,
        }

    async def _withdraw_single_wallet(
        self,
        from_wallet,
        to_wallet,
        leave_rent: bool
    ) -> Dict[str, Any]:
        """
        Transfer all withdrawable SOL from one wallet to another.

        Fetches the live on-chain balance, deducts an estimated fee
        (5000 lamports — one signature, median priority), and the
        rent-exempt reserve when requested, then builds + sends a
        legacy Transaction containing a single SystemProgram transfer.

        Returns a result dict with keys: wallet, success, amount_sol, signature, error.
        """
        try:
            # --- 1. Fetch live balance -----------------------------------------
            balance_resp = await self.rpc_client.get_balance(
                from_wallet.public_key, commitment=Confirmed
            )
            balance_lamports = balance_resp.value
            if balance_lamports is None:
                raise RuntimeError("Could not fetch on-chain balance")

            # --- 2. Calculate transferable amount --------------------------------
            fee_lamports = 5_000  # one signature at base fee
            reserve = RENT_EXEMPT_MINIMUM_LAMPORTS if leave_rent else 0
            transfer_lamports = balance_lamports - fee_lamports - reserve

            if transfer_lamports <= 0:
                msg = (
                    f"Balance too low to withdraw "
                    f"({balance_lamports / 1e9:.6f} SOL, need >{(fee_lamports + reserve) / 1e9:.6f})"
                )
                logger.warning(f"{from_wallet.label}: {msg}")
                return {'wallet': from_wallet.label, 'success': False, 'error': msg, 'amount_sol': 0.0}

            amount_sol = transfer_lamports / 1e9
            logger.info(
                f"{from_wallet.label}: Withdrawing {amount_sol:.6f} SOL "
                f"→ {to_wallet.label} ({to_wallet.public_key})"
            )

            # --- 3. Fetch a recent blockhash -------------------------------------
            blockhash_resp = await self.rpc_client.get_latest_blockhash()
            recent_blockhash: Hash = blockhash_resp.value.blockhash

            # --- 4. Build & sign legacy transaction ------------------------------
            ix = transfer(TransferParams(
                from_pubkey=from_wallet.public_key,
                to_pubkey=to_wallet.public_key,
                lamports=transfer_lamports,
            ))
            msg = Message.new_with_blockhash(
                [ix],
                from_wallet.public_key,  # fee payer
                recent_blockhash,
            )
            tx = Transaction.new_unsigned(msg)
            tx.sign([from_wallet.keypair], recent_blockhash)

            # --- 5. Send transaction ---------------------------------------------
            sig_resp = await self.rpc_client.send_raw_transaction(
                bytes(tx),
                opts=TxOpts(skip_preflight=False, max_retries=3),
            )

            sig_str = str(sig_resp.value)
            logger.info(f"✓ {from_wallet.label}: Withdraw OK — sig {sig_str[:16]}...")
            logger.trade(f"{from_wallet.label} withdrew {amount_sol:.6f} SOL to {to_wallet.label}")

            return {
                'wallet': from_wallet.label,
                'success': True,
                'amount_sol': amount_sol,
                'signature': sig_str,
                'error': None,
            }

        except Exception as e:
            logger.error(f"{from_wallet.label}: Withdraw failed — {e}")
            return {'wallet': from_wallet.label, 'success': False, 'error': str(e), 'amount_sol': 0.0}


# Global seller instance
_token_seller = None
_token_seller_client = None


def get_token_seller(rpc_client: AsyncClient) -> TokenSeller:
    """Get or create global token seller instance.
    Recreates if a different RPC client is supplied (e.g. after reconnect)."""
    global _token_seller, _token_seller_client
    if _token_seller is None or _token_seller_client is not rpc_client:
        _token_seller = TokenSeller(rpc_client)
        _token_seller_client = rpc_client
    return _token_seller
