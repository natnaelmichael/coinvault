# 🚀 Pump.fun Bot - Phase 2 Complete

**Open-source Solana pump.fun trading bot with full token creation and bundle trading capabilities.**

## ✅ What's Included in This Release

### Phase 2 Features (FULLY IMPLEMENTED):
- 🪙 **Token Creation** - Create tokens on pump.fun with metadata and IPFS upload
- 🔄 **Bundle Buying** - Buy tokens simultaneously with multiple wallets
- 💸 **Bundle Selling** - Sell and withdraw from all wallets at once
- 📊 **Wallet Management** - Full SOL distribution and balance tracking
- 🔔 **Notifications** - Desktop alerts and sound notifications
- 🛡️ **Safety Features** - Dry-run mode, confirmations, comprehensive logging

## 🎯 Quick Start

### 1. Installation

```bash
# Make setup script executable
chmod +x setup.sh

# Run setup (creates venv, installs dependencies)
./setup.sh
```

### 2. Configuration

```bash
# Copy example config
cp .env.example .env

# Edit with your settings
nano .env
```

**Required settings:**
```env
# Generate wallets first, then add keys here
DEV_WALLET_PRIVATE_KEY=your_dev_wallet_key_here
FUND_WALLET_PRIVATE_KEYS=key1,key2,key3

# Safety (keep these ON for testing!)
DRY_RUN_MODE=true
REQUIRE_CONFIRMATION=true
```

### 3. Generate Wallets

```bash
# Activate virtual environment
source venv/bin/activate

# Generate 6 wallets (1 dev + 5 fund)
python main.py generate-wallets --count 6

# Copy the private keys to your .env file
```

### 4. Verify Configuration

```bash
python main.py config-check
```

Should show: ✅ Configuration is valid!

### 5. Start the Bot

```bash
python main.py start
```

---

## 📖 Full Workflow Example

### Complete Token Launch

```bash
# 1. Start bot
source venv/bin/activate
python main.py start

# 2. Fund dev wallet (buy SOL from exchange, send to dev wallet address)

# 3. Distribute SOL to fund wallets
Menu → Option 2: Distribute SOL
Amount: 0.1 SOL per wallet

# 4. Create token
Menu → Option 3: Create New Token
- Name: My Awesome Token
- Symbol: MAT
- Description: Best token ever
- Image: ./my-token.png (optional)
- Social links: (optional)
- Initial buy: 0.1 SOL

# 5. Bundle buy (create volume)
Menu → Option 4: Bundle Buy Token
- Token mint: [from creation]
- Amount: 0.05 SOL per wallet
- Wallets: All
- Delay: 0ms (simultaneous)

# 6. Monitor & manage...

# 7. Bundle sell & withdraw
Menu → Option 6: Sell & Withdraw All
- Sell: All tokens
- Withdraw: Yes
```

---

## 🎨 Token Creation Guide

### Image Requirements

- **Size:** 512x512px to 1000x1000px
- **Format:** PNG or JPEG
- **File size:** Under 5MB
- **Style:** Eye-catching, meme-friendly, square aspect ratio

### Good Token Ideas

✅ Unique meme concepts
✅ Community-driven projects
✅ Simple, bold designs
✅ Clear value proposition

❌ Copyrighted content
❌ Generic/boring concepts
❌ Overly complex designs

---

## 💰 Budget Planning

### Minimum Budget (Testing)
- Token creation: 0.02 SOL (~$2)
- Initial buy: 0.1 SOL (~$10)
- Buffer: 0.05 SOL
- **Total: ~$12-15**

### Recommended Budget (Real Launch)
- Token creation: 0.02 SOL
- Initial buy: 0.5-1 SOL
- Bundle buys: 2-5 SOL
- Marketing: Variable
- **Total: ~$250-750**

---

## 🔧 Menu Options

### 1. View Wallet Balances
- Shows all wallets
- Real-time SOL balances
- Total across all wallets

### 2. Distribute SOL
- Send SOL from dev wallet to fund wallets
- Configurable amount per wallet
- Dry-run support

### 3. Create New Token ⭐ NEW
- Upload image to IPFS
- Add metadata (name, symbol, description)
- Optional social links
- Initial buy capability
- Returns mint address

### 4. Bundle Buy Token ⭐ NEW
- Buy with multiple wallets simultaneously
- Configurable amount per wallet
- Optional delay between buys
- Creates volume and chart activity

### 5. Monitor Token
- Coming in Phase 3
- Real-time price tracking
- Bonding curve progress

### 6. Sell & Withdraw All ⭐ NEW
- Sell from all wallets simultaneously
- Sell all, percentage, or specific amount
- Withdraw remaining SOL to dev wallet
- Complete fund extraction

### 7. Manage Wallets
- Add new fund wallets
- Remove wallets
- Export wallet keys

### 8. Settings
- Toggle dry-run mode
- Toggle confirmations
- Toggle notifications
- Adjust alert settings

---

## 🛡️ Safety Features

### Dry-Run Mode
- **Default:** ON
- Test all operations without spending SOL
- Perfect for learning the bot
- Shows what WOULD happen

### Confirmations
- Required before major actions
- Review transaction details
- Prevents accidental operations

### Logging
- All actions logged to files
- Console output with color coding
- Trade-specific logging
- Error tracking

---

## 📁 File Structure

```
pumpfun2/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Main interface (Phase 2 integrated)
│   ├── config.py           # Configuration management
│   ├── wallet_manager.py   # Wallet operations
│   ├── token_creator.py    # Token creation ⭐ NEW
│   ├── buyer.py            # Bundle buying ⭐ NEW
│   ├── seller.py           # Bundle selling ⭐ NEW
│   ├── logger.py           # Logging system
│   └── notifications.py    # Alert system
├── config/                 # Config files
├── logs/                   # Log files
├── data/                   # Data storage
│   └── created_tokens.json # Token tracking
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── setup.sh                # Setup script
├── .env.example            # Config template
└── README.md              # This file
```

---

## ⚙️ Configuration Options

### Network Settings
```env
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_NETWORK=mainnet-beta
```

### Trading Settings
```env
DEFAULT_SLIPPAGE_BPS=500      # 5% slippage
MAX_BUY_AMOUNT_SOL=1.0
MIN_BUY_AMOUNT_SOL=0.01
```

### Safety Settings
```env
DRY_RUN_MODE=true             # No real transactions
REQUIRE_CONFIRMATION=true     # Confirm before actions
```

### Automation (Phase 3+)
```env
AUTO_SELL_ENABLED=false
AUTO_SELL_PROFIT_MULTIPLIER=2.0
AUTO_WITHDRAW_ENABLED=false
```

---

## 🚨 Important Notes

### ⚠️ USE AT YOUR OWN RISK
- This bot executes REAL transactions with REAL funds
- Always start with DRY_RUN_MODE=true
- Test thoroughly before going live
- Never invest more than you can afford to lose
- DYOR (Do Your Own Research)

### 🔐 Security
- **Never share your private keys**
- Keep .env file secure
- Don't commit .env to version control
- Store backups securely

### 📊 Expectations
- Token success is NOT guaranteed
- Most pump.fun tokens fail
- Market conditions vary greatly
- This is high-risk activity

---

## 🐛 Troubleshooting

### "ModuleNotFoundError"
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### "Configuration errors found"
```bash
# Check your .env file
python main.py config-check
```

### "Insufficient balance"
```bash
# Fund your dev wallet with SOL
# Check balances: Option 1 in menu
```

### Transactions failing
- Check RPC endpoint is working
- Verify sufficient SOL in wallet
- Try increasing slippage
- Check Solana network status

---

## 📚 Additional Resources

- **Solana Docs:** https://docs.solana.com
- **pump.fun:** https://pump.fun
- **Discord:** [Your Discord]
- **Twitter:** [Your Twitter]

---

## 🗺️ Roadmap

### ✅ Phase 1: Core Infrastructure (COMPLETE)
- Wallet management
- Balance tracking
- Configuration system
- Logging & notifications

### ✅ Phase 2: Token Operations (COMPLETE)
- Token creation with IPFS
- Bundle buying
- Bundle selling
- SOL distribution

### 🚧 Phase 3: Monitoring & Automation (Next)
- Real-time price tracking
- Bonding curve monitoring
- Auto-sell on targets
- Portfolio analytics

### 📅 Phase 4: Advanced Features
- Strategy engine
- Risk management
- Multi-token management
- Advanced analytics

### 📅 Phase 5: Security & Polish
- Encrypted wallet storage
- Master password
- Backup system
- UI improvements

---

## 📜 License

MIT License - See LICENSE file

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Test thoroughly
4. Submit a pull request

---

## ⚡ Quick Commands Reference

```bash
# Setup
./setup.sh
source venv/bin/activate

# Generate wallets
python main.py generate-wallets --count 6

# Check config
python main.py config-check

# Start bot
python main.py start

# Deactivate venv
deactivate
```

---

**Built with ❤️ for the Solana community**

**Remember: This is for educational purposes. Trade responsibly!**
