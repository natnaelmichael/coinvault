#!/usr/bin/env python3
"""
Minimal Pump.fun Token Creator - No unnecessary complexity
Dependencies: requests, base58, solders, solana
"""

import requests
import base58
import time
from pathlib import Path
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client
from solana.rpc.types import TxOpts

# ============================================================================
# CONFIGURATION - Put these in a .env file or hardcode for testing
# ============================================================================
RPC_URL = "https://your-quicknode-rpc.com"  # Get from QuickNode/Helius
PINATA_JWT = "your_pinata_jwt"
DEV_WALLET_PRIVATE_KEY = "base58_private_key_here"

# ============================================================================
# IPFS UPLOAD - Single function, no complexity
# ============================================================================
def upload_to_ipfs(image_path: str, metadata: dict) -> str:
    """Upload image + JSON to Pinata, return metadata URI"""
    
    # Step 1: Upload image
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    image_response = requests.post(
        "https://uploads.pinata.cloud/v3/files",
        headers={"Authorization": f"Bearer {PINATA_JWT}"},
        files={"file": (Path(image_path).name, image_data)},
        data={"network": "public"}
    )
    image_cid = image_response.json()["data"]["cid"]
    image_url = f"https://ipfs.io/ipfs/{image_cid}"
    
    # Step 2: Upload metadata JSON
    metadata["image"] = image_url
    metadata_file = ("metadata.json", json.dumps(metadata).encode(), "application/json")
    
    meta_response = requests.post(
        "https://uploads.pinata.cloud/v3/files",
        headers={"Authorization": f"Bearer {PINATA_JWT}"},
        files={"file": metadata_file},
        data={"network": "public"}
    )
    meta_cid = meta_response.json()["data"]["cid"]
    
    return f"https://ipfs.io/ipfs/{meta_cid}"

# ============================================================================
# PUMP.FUN TOKEN CREATION - The core logic
# ============================================================================
def create_token(
    dev_wallet: Keypair,
    token_name: str,
    token_symbol: str,
    description: str,
    image_path: str,
    twitter: str = "",
    telegram: str = "",
    website: str = "",
    initial_buy_sol: float = 0.0
) -> str:
    """
    Create a token on pump.fun
    
    Returns: Transaction signature
    """
    
    # 1. Upload metadata to IPFS
    print(f"📤 Uploading metadata for {token_name}...")
    metadata_uri = upload_to_ipfs(image_path, {
        "name": token_name,
        "symbol": token_symbol,
        "description": description,
        "twitter": twitter,
        "telegram": telegram,
        "website": website
    })
    print(f"   Metadata URI: {metadata_uri}")
    
    # 2. Generate mint keypair (this will be your token's mint address)
    mint_keypair = Keypair()
    print(f"🪙 Mint address: {mint_keypair.pubkey()}")
    
    # 3. Request unsigned transaction from pump.fun API
    print(f"📝 Requesting transaction from pump.fun...")
    response = requests.post(
        "https://pumpportal.fun/api/trade-local",
        json={
            "publicKey": str(dev_wallet.pubkey()),
            "action": "create",
            "tokenMetadata": {
                "name": token_name,
                "symbol": token_symbol,
                "uri": metadata_uri,
            },
            "mint": str(mint_keypair.pubkey()),
            "denominatedInSol": "true",
            "amount": initial_buy_sol,
            "slippage": 5,
            "priorityFee": 0.002,  # Increased from 0.0005 to 0.002 SOL
            "pool": "pump"
        },
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code != 200:
        raise Exception(f"API error: {response.status_code} - {response.text}")
    
    # 4. Deserialize the transaction
    tx_bytes = response.content
    unsigned_tx = VersionedTransaction.from_bytes(tx_bytes)
    
    # 5. SIGN IN CORRECT ORDER: mint keypair FIRST, then dev wallet
    #    The mint keypair must sign first because it's creating the mint account
    print(f"✍️ Signing transaction...")
    signed_tx = VersionedTransaction(
        unsigned_tx.message,
        [mint_keypair, dev_wallet]  # Order matters!
    )
    
    # 6. Send to blockchain with retry logic
    rpc_client = Client(RPC_URL)
    
    for attempt in range(3):
        try:
            print(f"📡 Sending transaction (attempt {attempt + 1}/3)...")
            result = rpc_client.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, max_retries=0)  # No retries - we handle them
            )
            
            signature = str(result.value)
            print(f"✅ Token created! Signature: {signature}")
            print(f"🔗 https://pump.fun/coin/{mint_keypair.pubkey()}")
            print(f"🔍 https://solscan.io/tx/{signature}")
            return signature
            
        except Exception as e:
            error_msg = str(e)
            if "Blockhash not found" in error_msg:
                print(f"   Blockhash expired, retrying in {2 ** attempt}s...")
                time.sleep(2 ** attempt)
                continue
            else:
                raise Exception(f"Transaction failed: {error_msg}")
    
    raise Exception("Max retries exceeded")

# ============================================================================
# MAIN - Run this to create your token
# ============================================================================
if __name__ == "__main__":
    # Load your dev wallet
    dev_wallet = Keypair.from_base58_string(DEV_WALLET_PRIVATE_KEY)
    print(f"👛 Dev wallet: {dev_wallet.pubkey()}")
    
    # Create your token
    signature = create_token(
        dev_wallet=dev_wallet,
        token_name="My Awesome Token",
        token_symbol="MAT",
        description="This is my awesome pump.fun token",
        image_path="/path/to/your/image.png",
        twitter="https://x.com/mytoken",
        telegram="https://t.me/mytoken",
        website="https://mytoken.com",
        initial_buy_sol=0.1  # Optional: buy tokens immediately after creation
    )
    
    print(f"\n🎉 Success! Token mint: {mint_keypair.pubkey()}")