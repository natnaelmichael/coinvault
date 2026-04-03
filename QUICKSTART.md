# ⚡ Pump.fun Bot - 5 Minute Quickstart

## Step 1: Install (2 minutes)

```bash
# Make setup executable
chmod +x setup.sh

# Run setup
./setup.sh

# Activate virtual environment
source venv/bin/activate
```

## Step 2: Generate Wallets (1 minute)

```bash
# Generate 6 wallets (1 dev + 5 fund)
python main.py generate-wallets --count 6
```

**⚠️ SAVE THE OUTPUT!** Copy all private keys somewhere secure.

## Step 3: Configure (1 minute)

```bash
# Copy example config
cp .env.example .env

# Edit config
nano .env
```

**Add your wallet keys:**
```env
DEV_WALLET_PRIVATE_KEY=<first_wallet_private_key>
FUND_WALLET_PRIVATE_KEYS=<key2>,<key3>,<key4>,<key5>,<key6>

# Keep these for testing:
DRY_RUN_MODE=true
REQUIRE_CONFIRMATION=true
```

Save and exit (Ctrl+X, Y, Enter)

## Step 4: Verify (30 seconds)

```bash
python main.py config-check
```

Should show: ✅ Configuration is valid!

## Step 5: Test Run (30 seconds)

```bash
python main.py start
```

### Test the Features:

1. **View Balances** (Option 1)
   - See your wallets (all 0.0000 SOL - expected!)

2. **Distribute SOL** (Option 2)
   - Enter: 0.1 SOL
   - See: [DRY RUN] messages (no real SOL sent)

3. **Create Token** (Option 3)
   - Name: Test Token
   - Symbol: TEST
   - Description: Testing
   - Image: No
   - Socials: No
   - Initial buy: 0.1 SOL
   - See: Token created with mock mint address

4. **Bundle Buy** (Option 4)
   - Token mint: [copy from creation]
   - Amount: 0.05 SOL
   - Wallets: All
   - See: Mock bundle buy complete

5. **Sell & Withdraw** (Option 6)
   - Token mint: [same as above]
   - Option: 1 (sell all)
   - Withdraw: Yes
   - See: Mock sell complete

**✅ If all tests show [DRY RUN] messages, you're ready!**

---

## 🚀 Going Live

### Before Real Trading:

1. **Fund Your Dev Wallet**
   ```bash
   # Get your dev wallet address
   python main.py start → Option 1
   
   # Send SOL from exchange (Coinbase, Binance, etc.)
   # Recommended: 1-5 SOL to start
   ```

2. **Disable Dry-Run Mode**
   ```bash
   nano .env
   
   # Change:
   DRY_RUN_MODE=false
   
   # Keep this ON!
   REQUIRE_CONFIRMATION=true
   ```

3. **Start Small**
   - Test with 0.01 SOL amounts first
   - Verify transactions on Solscan
   - Gradually increase as comfortable

---

## 📋 Common First Actions

### Create Your First Token

```
python main.py start
→ Option 2: Distribute SOL (0.1 per wallet)
→ Option 3: Create Token
   - Have your image ready (512x512 PNG)
   - Prepare description
   - Set initial buy (0.1-0.5 SOL)
→ Token created! Note the mint address
```

### Bundle Buy

```
→ Option 4: Bundle Buy
   - Enter token mint address
   - Amount: 0.05 SOL per wallet
   - Use all wallets
   - No delay (simultaneous)
→ Creates volume on chart
```

### Exit Strategy

```
→ Option 6: Sell & Withdraw
   - Enter token mint
   - Sell: All tokens
   - Withdraw: Yes
→ All SOL returns to dev wallet
```

---

## 🆘 Quick Troubleshooting

**"Configuration errors"**
→ Check .env file has wallet keys

**"ModuleNotFoundError"**
→ Run: `pip install -r requirements.txt`

**"Insufficient balance"**
→ Fund your dev wallet with SOL

**Transactions failing**
→ Increase slippage in .env
→ Check Solana network status

---

## 🎯 Next Steps

1. ✅ Complete this quickstart
2. 📖 Read full README.md
3. 🎨 Prepare token artwork
4. 💰 Fund dev wallet
5. 🧪 Test in dry-run
6. 🚀 Launch your token!

---

## 🔗 Important Links

- **Full Docs:** README.md
- **Solscan:** https://solscan.io
- **Pump.fun:** https://pump.fun

---

**Remember: Start with DRY_RUN_MODE=true and small amounts!**

**Good luck! 🚀**
