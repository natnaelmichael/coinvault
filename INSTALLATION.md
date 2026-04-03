# 📦 Installation Guide - Pump.fun Bot Phase 2

## 🚀 Complete Installation Instructions

### Step 1: Download & Extract

```bash
# Download pumpfun2.tar.gz
# Then extract:
tar -xzf pumpfun2.tar.gz
cd pumpfun2
```

### Step 2: Run Setup

```bash
# Make setup script executable
chmod +x setup.sh

# Run automated setup
./setup.sh
```

**What setup.sh does:**
- ✅ Checks Python version (3.9+ required)
- ✅ Creates virtual environment
- ✅ Installs all dependencies
- ✅ Creates necessary directories
- ✅ Copies .env.example to .env

### Step 3: Activate Virtual Environment

```bash
# Every time you open a new terminal:
source venv/bin/activate

# You should see (venv) in your prompt
```

### Step 4: Generate Wallets

```bash
python main.py generate-wallets --count 6
```

**⚠️ CRITICAL: Save this output!**
- Copy all private keys to a secure location
- You'll need these for the .env file
- Never share these keys with anyone

### Step 5: Configure .env

```bash
# Edit configuration file
nano .env
```

**Add your wallet keys:**
```env
# Use the FIRST wallet as dev wallet
DEV_WALLET_PRIVATE_KEY=<wallet_1_private_key>

# Use remaining wallets as fund wallets (comma-separated, NO SPACES)
FUND_WALLET_PRIVATE_KEYS=<wallet_2_key>,<wallet_3_key>,<wallet_4_key>,<wallet_5_key>,<wallet_6_key>

# Keep these settings for testing
DRY_RUN_MODE=true
REQUIRE_CONFIRMATION=true
```

**Save and exit:**
- Press `Ctrl + X`
- Press `Y` to confirm
- Press `Enter`

### Step 6: Verify Installation

```bash
python main.py config-check
```

**Expected output:**
```
✓ Configuration is valid!

╔══════════════════════════════════════════════════════════════╗
║                  PUMP.FUN BOT CONFIGURATION                  ║
╠══════════════════════════════════════════════════════════════╣
║ Mode: 🔴 DRY RUN                                            ║
║ Network: mainnet-beta                                      ║
║ Dev Wallet: Configured                                       ║
║ Fund Wallets: 5 configured                                   ║
╚══════════════════════════════════════════════════════════════╝
```

### Step 7: Test Run

```bash
python main.py start
```

**Test each feature:**
1. View Balances (shows 0.0000 - expected!)
2. Distribute SOL (shows [DRY RUN])
3. Create Token (shows [DRY RUN])
4. Bundle Buy (shows [DRY RUN])
5. Sell & Withdraw (shows [DRY RUN])

If all features show `[DRY RUN]` messages, installation is **complete!** ✅

---

## 🔧 Platform-Specific Instructions

### macOS

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.9+
brew install python@3.11

# Continue with normal installation
chmod +x setup.sh
./setup.sh
```

### Linux (Ubuntu/Debian)

```bash
# Install Python 3.9+
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# Continue with normal installation
chmod +x setup.sh
./setup.sh
```

### Windows

**Option 1: WSL (Recommended)**
```bash
# Install WSL2 with Ubuntu
wsl --install

# Then follow Linux instructions above
```

**Option 2: Native Windows**
```cmd
:: Install Python 3.11 from python.org
:: Download: https://www.python.org/downloads/

:: Open PowerShell as Administrator
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

:: Edit .env manually with Notepad
notepad .env
```

---

## 🐛 Troubleshooting

### "Command not found: python"
Try `python3` instead:
```bash
python3 main.py start
```

Or create alias:
```bash
alias python=python3
```

### "Permission denied: ./setup.sh"
Make it executable:
```bash
chmod +x setup.sh
```

### "No module named 'click'"
Virtual environment not activated:
```bash
source venv/bin/activate
```

Or reinstall dependencies:
```bash
pip install -r requirements.txt
```

### "Configuration errors found"
Check your .env file:
```bash
cat .env | grep WALLET
```

Make sure:
- Private keys are base58 encoded (88 characters)
- No spaces in FUND_WALLET_PRIVATE_KEYS
- Both DEV and FUND keys are set

### "Python version 3.9 or higher required"
Update Python:
```bash
# macOS
brew install python@3.11

# Linux
sudo apt install python3.11

# Windows
# Download from python.org
```

---

## ✅ Verification Checklist

Before going live, verify:

- [ ] Python 3.9+ installed
- [ ] Virtual environment created
- [ ] All dependencies installed
- [ ] Wallets generated and saved
- [ ] .env file configured
- [ ] Config check passes
- [ ] Dry-run test successful
- [ ] All features tested
- [ ] Private keys backed up securely

---

## 🔐 Security Checklist

- [ ] .env file is NOT committed to git
- [ ] Private keys stored securely offline
- [ ] .gitignore includes .env
- [ ] Backups of private keys made
- [ ] Understanding of DRY_RUN_MODE
- [ ] Never shared keys with anyone

---

## 📚 Next Steps

1. ✅ Complete installation
2. 📖 Read QUICKSTART.md
3. 📖 Read full README.md
4. 🧪 Test all features in dry-run
5. 💰 Fund dev wallet (when ready)
6. 🚀 Launch your first token!

---

## 🆘 Getting Help

**Check logs:**
```bash
ls -la logs/
tail -100 logs/pumpfun_bot_*.log
```

**Verify file structure:**
```bash
ls -la
ls -la src/
```

**Test Python imports:**
```bash
python -c "import solana; print('✓ solana')"
python -c "import click; print('✓ click')"
python -c "import rich; print('✓ rich')"
```

---

## 🎉 Installation Complete!

Your pump.fun bot is ready to use.

**Remember:**
- Start with DRY_RUN_MODE=true
- Test thoroughly before going live
- Start with small amounts
- Never invest more than you can afford to lose

**Good luck! 🚀**
