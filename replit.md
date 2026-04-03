# Pump.fun Bot (Phase 2)

An open-source automated trading and token creation tool for the Solana blockchain, targeting the pump.fun platform.

## Architecture

- **Language:** Python 3.12
- **Package Manager:** pip
- **Type:** CLI/TUI application (no web frontend)
- **Entry Point:** `main.py`

## Project Structure

```
pumpfun2/
├── main.py                # Entry point
├── requirements.txt       # Python dependencies
├── .env                   # Environment config (gitignored)
├── src/
│   ├── cli.py             # CLI menus and commands
│   ├── tui.py             # Textual TUI mode
│   ├── config.py          # Config/env loading
│   ├── wallet_manager.py  # Wallet generation and SOL distribution
│   ├── token_creator.py   # Token creation + IPFS upload
│   ├── buyer.py           # Bundle buy operations
│   ├── seller.py          # Bundle sell + SOL withdrawal
│   ├── logger.py          # Logging system
│   ├── notifications.py   # Desktop/audio alerts
│   └── __init__.py
├── data/                  # Persistent data (created at runtime)
└── logs/                  # Log files (created at runtime)
```

## Running the App

- **CLI mode (main):** `python3 main.py start`
- **TUI mode:** `python3 main.py tui`
- **Config check:** `python3 main.py config-check`
- **Generate wallets:** `python3 main.py generate-wallets`

## Configuration

Copy `.env` (already present) and fill in your wallet private keys and Solana RPC URL.

Key settings:
- `DRY_RUN_MODE=true` — safe by default, no real SOL is spent
- `SOLANA_NETWORK=mainnet-beta` — can switch to `devnet` for testing
- `DEV_WALLET_PRIVATE_KEY` — your main/dev wallet private key
- `FUND_WALLET_PRIVATE_KEYS` — comma-separated fund wallet keys

## Workflow

- **Start application** — runs `python3 main.py start` in console mode

## Dependencies Fixed

- `nacl` renamed to `PyNaCl>=1.5.0` in requirements.txt (original package name was incorrect)
