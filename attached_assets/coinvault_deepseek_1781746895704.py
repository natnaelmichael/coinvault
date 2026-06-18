#!/usr/bin/env python3
"""
Minimal Pump.fun Token Creator - No solders RPC dependencies
Uses raw HTTP requests for RPC calls, solders only for crypto
"""

import requests
import base58
import time
import json
from pathlib import Path
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# ============================================================================
# QUICKNODE CONFIGURATION
# ============================================================================

#QUICKNODE_DEVNET_URL = "https://yolo-late-sunset.solana-devnet.quiknode.pro/66aed0a364cb6b31a2db526f4b6f6d2a343756fd/"
QUICKNODE_DEVNET_URL = "https://yolo-late-sunset.solana-devnet.quiknode.pro/66aed0a364cb6b31a2db526f4b6f6d2a343756fd/"
# ============================================================================
# PURE REQUESTS RPC CLIENT - No solders for RPC calls
# ============================================================================

def rpc_call(method, params=[]):
    """Make a raw JSON-RPC call to QuickNode"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }

    response = requests.post(
        QUICKNODE_DEVNET_URL,
        json=payload,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(f"RPC error: {response.status_code} - {response.text}")

    result = response.json()

    if "error" in result:
        raise Exception(f"RPC method error: {result['error']}")

    return result["result"]

def get_slot():
    """Get current block height"""
    return rpc_call("getSlot")

def get_version():
    """Get Solana version"""
    return rpc_call("getVersion")

def get_balance(pubkey):
    """Get SOL balance in lamports"""
    result = rpc_call("getBalance", [pubkey])
    return result["value"]  # Returns lamports

def request_airdrop(pubkey, lamports):
    """Request airdrop on devnet"""
    return rpc_call("requestAirdrop", [pubkey, lamports])

def send_transaction(base64_tx):
    """Send a signed transaction (expects base64 encoded transaction)"""
    return rpc_call("sendTransaction", [base64_tx, {"encoding": "base64"}])

# ============================================================================
# CONNECTION TEST
# ============================================================================

def test_connection():
    """Test QuickNode connection without solders"""
    try:
        slot = get_slot()
        print(f"✅ Connected! Current slot: {slot}")

        version = get_version()
        print(f"✅ Solana version: {version.get('solana-core', 'unknown')}")

        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

# ============================================================================
# TOKEN CREATION
# ============================================================================

def create_token(
    dev_wallet: Keypair,
    token_name: str,
    token_symbol: str,
    description: str,
    image_path: str = None,
    twitter: str = "",
    telegram: str = "",
    website: str = "",
    initial_buy_sol: float = 0.0
):
    """
    Create a token on pump.fun using pure HTTP for RPC
    """

    print(f"\n🚀 Creating token: {token_name} ({token_symbol})")

    # 1. Generate mint keypair
    mint_keypair = Keypair()
    mint_address = str(mint_keypair.pubkey())
    print(f"🪙 Mint address: {mint_address}")

    # 2. Upload metadata (simplified for now)
    metadata_uri = "https://arweave.net/example-placeholder"
    print(f"📝 Metadata URI: {metadata_uri}")

    # 3. Get unsigned transaction from pump.fun API
    print("📝 Requesting transaction from pump.fun...")

    create_payload = {
        "publicKey": str(dev_wallet.pubkey()),
        "action": "create",
        "tokenMetadata": {
            "name": token_name,
            "symbol": token_symbol,
            "uri": metadata_uri,
        },
        "mint": mint_address,
        "denominatedInSol": "true",
        "amount": initial_buy_sol,
        "slippage": 5,
        "priorityFee": 0.002,
        "pool": "pump"
    }

    response = requests.post(
        "https://pumpportal.fun/api/trade-local",
        json=create_payload,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(f"Pump.fun API error: {response.status_code}\n{response.text[:500]}")

    # 4. Sign the transaction
    print("✍️ Signing transaction...")
    unsigned_tx = VersionedTransaction.from_bytes(response.content)
    signed_tx = VersionedTransaction(
        unsigned_tx.message,
        [mint_keypair, dev_wallet]  # mint signs FIRST, then dev wallet
    )

    # 5. Convert to base64 for sending
    import base64
    tx_base64 = base64.b64encode(bytes(signed_tx)).decode('ascii')

    # 6. Send via our pure-requests RPC
    print("📡 Sending via QuickNode...")
    result = send_transaction(tx_base64)

    signature = result
    print(f"\n✅ Token created successfully!")
    print(f"📝 Signature: {signature}")
    print(f"🔗 https://pump.fun/coin/{mint_address}")
    print(f"🔍 https://solscan.io/tx/{signature}")

    return {
        "success": True,
        "signature": signature,
        "mint": mint_address,
        "metadataUri": metadata_uri
    }

# ============================================================================
# BUNDLE BUY (Coming next)
# ============================================================================

def bundle_buy(wallets, token_mint, amount_per_wallet_sol):
    """
    Bundle buy a token with multiple wallets
    """
    print(f"\n🔄 Bundle buying {token_mint[:16]}...")
    print(f"   Wallets: {len(wallets)}")
    print(f"   Amount per wallet: {amount_per_wallet_sol} SOL")

    results = []
    for i, wallet in enumerate(wallets, 1):
        print(f"   [{i}/{len(wallets)}] Buying with {wallet.label}...")
        # Implementation coming next
        results.append({"wallet": wallet.label, "success": True})

    return results

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PUMP.FUN TOKEN CREATOR - Pure HTTP QuickNode Client")
    print("=" * 60)

    # 1. Test connection
    print("\n🔌 Testing QuickNode connection...")
    if not test_connection():
        print("\n❌ Connection failed. Check your URL.")
        exit(1)

    # 2. Generate test wallet (for devnet testing only)
    print("\n📦 Generating test wallet...")
    test_wallet = Keypair()
    wallet_address = str(test_wallet.pubkey())
    print(f"   Address: {wallet_address}")

    # 3. Request airdrop (devnet only)
    print("\n💧 Requesting 2 SOL from devnet faucet...")
    try:
        lamports = 2_000_000_000  # 2 SOL
        tx_hash = request_airdrop(wallet_address, lamports)
        print(f"   Airdrop TX: {tx_hash}")
        print("   Waiting 15 seconds for confirmation...")
        time.sleep(15)
    except Exception as e:
        print(f"   ⚠️  Airdrop failed: {e}")

    # 4. Check balance
    balance_lamports = get_balance(wallet_address)
    balance_sol = balance_lamports / 1_000_000_000
    print(f"\n💰 Wallet balance: {balance_sol} SOL")

    if balance_sol < 0.05:
        print(f"⚠️  Low balance. Try airdrop again or wait longer.")
    else:
        print("\n✅ Ready to create tokens!")

        # UNCOMMENT TO ACTUALLY CREATE A TOKEN
        # result = create_token(
        #     dev_wallet=test_wallet,
        #     token_name="My Devnet Test",
        #     token_symbol="DEVNET",
        #     description="Testing on devnet",
        #     initial_buy_sol=0.01
        # )

    print("\n" + "=" * 60)
    print("✅ QuickNode connection verified!")
    print("=" * 60)

    # Keep the REPL open for interactive testing
    import code
    code.interact(local=locals())
