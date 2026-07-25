---
name: Jito MEV Bundle Implementation
description: Full Jito integration covering options 3, 4B, 4C, 4A — what's where and key design decisions.
---

## Summary
Full Jito MEV bundle implementation across src/jito_bundle.py, src/seller.py, src/token_creator.py, src/config.py, src/tui.py, src/solana_tx.py.

## Key design decisions

### Bundle limits
- Max 5 txs per Jito bundle; 1 reserved for the tip tx → MAX_TXS_PER_BUNDLE=4 payload slots.
- Tip tx is a legacy Transaction (solders.transaction.Transaction); sell/create txs are VersionedTransaction. Both base64-encoded in the same bundle — Jito accepts mixed types.

### Shared blockhash
All txs in a bundle must share one blockhash. sign_tx(tx_bytes, signers, blockhash) in solana_tx.py is the low-level primitive; sign_and_send() calls it internally.

### Blockhash validity window
BLOCKHASH_VALIDITY_SECONDS = 55.0 (conservative; network actually ~60–90s). Used by the 4A retry loop to decide whether to reuse signed sell txs or re-fetch from PumpPortal.

### 4C endpoint auto-select
pick_fastest_endpoint() probes all 5 regional engines with getBundleStatuses([]) and caches the winner in _cached_fastest_endpoint. Cached for process lifetime — only runs once. JITO_ENDPOINT=auto triggers it.

### 4B streaming
poll_bundle_statuses() accepts on_status callback. jito_wave_sell() accepts on_progress, passes it through. TUI _do_sell_all closure updates the footer Static directly (safe — runs in async worker on event loop).

### 4A retry (approach B)
Outer loop in jito_wave_sell():
- Only retry wallets whose bundle timed out (confirmed + hard-rejected are final).
- If elapsed < 55s: reuse existing signed sell txs, only rebuild tip with higher lamports.
- If elapsed ≥ 55s: full re-fetch from PumpPortal + new blockhash + re-sign.
- scale_tip(current, multiplier, max) helper in jito_bundle.py.
- Config: JITO_MAX_RETRIES=3, JITO_TIP_MULTIPLIER=2.0, JITO_MAX_TIP_SOL=0.05

### .env vars to activate
```
JITO_ENABLED=true
JITO_TIP_SOL=0.001
JITO_ENDPOINT=mainnet   # or: amsterdam|ny|tokyo|frankfurt|auto
JITO_MAX_RETRIES=3
JITO_TIP_MULTIPLIER=2.0
JITO_MAX_TIP_SOL=0.05
```
.env edits are sandbox-blocked — user must add these manually.

### Token creation Jito path
TokenCreator._jito_create() wraps the PumpPortal create tx in [tip_tx, create_tx] bundle.
Switched in create_token() on config.jito_enabled.

### poll_bundle_statuses endpoint
Both sendBundle and getBundleStatuses use the SAME URL (/api/v1/bundles) — distinguished by the method field in the JSON-RPC body.

### err field handling in getBundleStatuses response
{"Ok": null} = success, null = success, error dict = failure. Check: `err is None or err == {"Ok": None} or (isinstance(err, dict) and err.get("Ok") is None and len(err) == 1)`

**Why:** Jito docs are inconsistent about the err format; the defensive check handles all observed variants.
