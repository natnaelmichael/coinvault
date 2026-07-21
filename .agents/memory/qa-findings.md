---
name: QA findings — July 2026 full codebase review
description: Bugs found and fixed; durable rules for this codebase going forward.
---

## Durable rules

**Missing helper modules are silent until first trade**
`src/solana_tx.py` and `src/pumpportal_api.py` were absent but imported at the top of buyer/seller/token_creator. The app only crashes when those modules are first imported (not at startup), so the missing files slip past a casual `python3 main.py start`. Any new buyer/seller/creator functionality must stay within these two files or import from them.

**Why:** The 3 trading modules share identical sign-and-send + HTTP-retry pipelines. Extracting them to helper modules prevents drift, but the helpers must actually exist.

**How to apply:** If you add a new module that calls PumpPortal or signs a Solana tx, import from `src/pumpportal_api.py` and `src/solana_tx.py` rather than re-implementing.

---

**bundle_sell positional-arg contract**
`bundle_sell(wallets, mint, amount_tokens, percentage)` — callers (cli.py:984, tui.py:1307) pass `amount_tokens` as the 3rd positional and `percentage` as 4th. The function signature must keep this order. Do NOT reorder or remove `amount_tokens`.

**Why:** was previously missing the `amount_tokens` param, causing the wrong value to land in `percentage`.

---

**Falsy-check on optional floats**
`if amount_tokens:` treats `0.0` as falsy. Always use `if amount_tokens is not None:` when the caller may legitimately pass zero. Applies to sell_token and anywhere optional numeric params appear.

---

**gather() exceptions must produce result objects**
`asyncio.gather(..., return_exceptions=True)` can return Exception objects in the results list. These must be wrapped in the matching Result dataclass (BuyResult/SellResult) so the returned list length always equals the wallets list length. UI code iterates by index and assumes 1-to-1 correspondence.

---

**blocking os.system() in async context**
Sound playback on macOS/Linux used `os.system()` directly — blocks the event loop. Always offload to `run_in_executor`. Fixed in notifications.py.
