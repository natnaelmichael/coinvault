# coinvault — Project Context

Last updated: 2026-07-16, covering work from 2026-07-09 through 2026-07-16.

This file exists so a future LLM session (or Natnael, coming back after a break) can
pick this project up without re-deriving everything from scratch. It captures what
the project is, what's been fixed, what's known-intentional, and what's still open.

---

## 1. What this project is

**coinvault** is a Python-based memecoin launching/trading bot targeting pump.fun,
built by Natnael (3rd-year CS undergrad, Ontario, Canada) as a learning project —
he's a beginner at actually launching memecoins, comfortable with code. Built around
**PumpPortal** (`pumpportal.fun`), a free third-party service that builds unsigned
Solana transactions for pump.fun's create/buy/sell actions, which get signed and
broadcast locally (keys never leave the user's machine).

Interface: a Textual-based TUI (`tui.py`), run via `python3 -m src.main tui` from
the `coinvault/coinvault` project root. There's also a `cli.py` (uploaded but not
yet reviewed in depth in this thread).

## 2. File map (as last reviewed)

All files live in a package directory (imported as `.module` — package name is
`src`, confirmed via `__init__.py` and working `python -m src.pinata_test` invocations).

| File | Role |
|---|---|
| `config.py` | Loads all settings from `.env` / environment. Has `.set()` to persist changes back to `.env`, and `.validate()` for startup checks. |
| `token_creator.py` | `TokenCreator` class — builds metadata, uploads to IPFS, builds/sends the PumpPortal `create` transaction. |
| `buyer.py` | `TokenBuyer` — single and bundled multi-wallet buys. |
| `seller.py` | `TokenSeller` — sells and SOL withdrawals (rent-exempt-aware). |
| `wallet_manager.py` | `WalletManager` / `Wallet` — loads dev + fund wallets from `.env`, balance tracking, SOL distribution between wallets. |
| `solana_tx.py` | **New, added this thread.** Shared `sign_and_send()` pipeline (deserialize → refresh blockhash → sign → send → confirm), used by all three of `buyer.py`/`seller.py`/`token_creator.py`. |
| `pumpportal_api.py` | **New, added this thread.** `post_with_retry()` — retries PumpPortal `trade-local` POSTs on 502/503 only, exponential backoff. |
| `pinata_test.py` | **New, added this thread.** Standalone script to test the Pinata JWT/upload path in isolation, bypassing wallets/dry-run/PumpPortal entirely. |
| `logger.py` | Singleton `BotLogger`, logs to console + timestamped file under `logs/`. |
| `notifications.py` | Desktop/sound alerts (`plyer`/`pygame`, both currently unavailable in Natnael's environment — not blocking, just no alerts). |
| `tui.py` | The Textual TUI itself. Screens include Create Token, Bundle Buy, Sell & Withdraw, Pre-load Token, Manage Wallets, Settings. |
| `cli.py` | Uploaded, not yet reviewed in this thread. |

## 3. The PumpPortal `trade-local` request shape (verified against docs)

All three of create/buy/sell POST a JSON body to `https://pumpportal.fun/api/trade-local`
and get back **raw unsigned transaction bytes** (not JSON) to sign locally. Confirmed
field structure for `create`:

```json
{
  "publicKey": "<wallet pubkey base58>",
  "action": "create",
  "tokenMetadata": { "name": "...", "symbol": "...", "uri": "<metadata IPFS URL>" },
  "mint": "<new mint pubkey base58>",
  "denominatedInSol": "true",
  "amount": 0.01,
  "slippage": 10,
  "priorityFee": 0.00001,
  "pool": "pump"
}
```

`buy`/`sell` are the same shape minus `tokenMetadata`/`mint`-as-new-keypair (mint is
the existing token's address instead), with `action: "buy"|"sell"`.

**Confirmed correct in this codebase**, matched against PumpPortal's docs line-by-line
early in this project's history — field names, signer order (`[mint_keypair, wallet_keypair]`
for create), and the fact that `mint` is a **public** key string for `trade-local`
(only PumpPortal's separate Lightning/server-signed endpoint needs a secret key).

## 4. Chronological history of what's been found/fixed

1. **Dead pump.fun IPFS endpoint** (`token_creator.py`) — pump.fun's own `/api/ipfs`
   endpoint is deprecated and no longer accepts uploads. Replaced with a Pinata-based
   upload (`_upload_metadata_pumpfun`, despite the name it now uses Pinata, kept the
   method name for backward compat with the `IPFS_MODE=pumpfun` config value).
2. **Hardcoded live Pinata JWT** — `config.py` had a real, working Pinata JWT
   embedded as the `os.getenv()` fallback default (not a placeholder). This got
   exposed in this chat. **Natnael rotated/revoked the old key.** Fixed:
   `self.pinata_jwt = os.getenv("PINATA_JWT", "")`, plus a `validate()` check.
   Also fixed a bug where the original `pinata_jwt` variable was never attached to
   `self` at all (local variable, silently discarded).
3. **`get_token_creator()` missing `rpc_client` arg** in early `pinata_test.py` drafts
   — fixed by constructing `AsyncClient(config.rpc_url)` before calling it, matching
   the pattern already used in `wallet_manager.py`/`buyer.py`.
4. **Confirmed dry-run behavior**: `create_token()`'s dry-run check happens *before*
   the IPFS upload branch when called through `create_token()` normally... except
   log evidence from a real TUI run showed the metadata upload actually happening
   (not `[DRY RUN] Would upload...`) even in dry-run mode — meaning IPFS upload is
   real even during dry runs when triggered via the TUI's Create Token screen; only
   the on-chain transaction step is mocked. (`pinata_test.py`, by contrast, calls
   `_upload_metadata_pumpfun` directly and does still hit the dry-run short-circuit
   if `dry_run_mode` isn't force-disabled — which is why it explicitly flips
   `config.dry_run_mode = False` around its one call.)
5. **De-duplication + confirmation polling** — the "deserialize → refresh blockhash →
   sign → send" block was near-identically copy-pasted across `buyer.py`, `seller.py`,
   `token_creator.py`. Centralized into `solana_tx.py`'s `sign_and_send()`, which also
   adds `_wait_for_confirmation()` polling `get_signature_statuses` — previously
   **nothing in the codebase confirmed a transaction actually landed**; a signature
   coming back from `send_raw_transaction` only means the RPC node accepted and
   relayed it, not that it succeeded on-chain. Buy/sell/create results now only
   report `success=True` when actually confirmed.
   ⚠️ **Not tested against a live RPC endpoint** — no network access to Solana RPC
   from within these Claude sessions. Confirmation-polling logic (string-matching on
   `confirmation_status`) should be verified against whatever `solana-py` version is
   actually pinned before being trusted.
6. **Image-not-found abort** — a real run failed because the TUI's image path field
   didn't match the actual filename on disk (`(1)` suffix from a duplicate download).
   Not a code bug, just a path mismatch — resolved by user correcting the path.
7. **502 Bad Gateway on create** — nginx-level failure in front of PumpPortal's
   backend (transient infra issue, not a payload problem — 502s happen before any
   request validation). Fixed by adding `pumpportal_api.py`'s `post_with_retry()`,
   used by all three trade-local POST call sites. Retries only on 502/503, exponential
   backoff (1.5s/3s/6s), 3 attempts. Any other status (200, 400, 429) returns
   immediately, unretried.
8. **400 Bad Request on create** — this one *did* reach PumpPortal's validation logic
   (first time any create payload had gotten that far; the earlier 502 never reached
   the application). Bare `"Bad Request"` text body, no detail. Leading hypothesis:
   IPFS gateway propagation race — the create request was sent <1 second after Pinata
   confirmed the pin, and PumpPortal's backend likely fetches/validates the metadata
   URI before accepting a create request; `ipfs.io` (a third-party gateway) can lag
   several seconds to over a minute before it can independently discover freshly-pinned
   content. **Fix applied**: switched `PINATA_GATEWAY_URL` from `https://ipfs.io/ipfs`
   to `https://gateway.pinata.cloud/ipfs` — Pinata's own gateway serves directly from
   the storage that just accepted the pin, no discovery/propagation delay to wait out.
   No polling or webhook needed; this removes the race condition by construction.
   ⚠️ **Not yet re-tested** — this was the most recent change. The 400 hypothesis is
   plausible and well-reasoned but not confirmed; next live test is the actual
   verification.
9. **"Edit Pre-loaded" TUI feature** — added a 4th button to the Pre-load Token
   screen, letting users edit an existing pre-loaded token's fields in place rather
   than only being able to add new ones. Implementation note: uses `dict.update()`
   on the existing JSON entry rather than replacing it wholesale, specifically to
   preserve fields the edit form doesn't show (`status`, `mint`, `launched_at`) that
   get written by `_do_launch()` after a token goes live — a naive full-replace
   would have silently wiped that history on edit.

## 5. Things that are *intentionally* left as-is (do not "fix" without asking)

- **The blockhash-refresh-before-signing step** in the (now-shared) `sign_and_send()`
  pipeline: fetches a fresh blockhash and rebuilds the transaction message with it,
  rather than signing PumpPortal's returned transaction as-is (which is what
  PumpPortal's own official examples do — deserialize and sign directly, no refresh).
  Natnael confirmed this deviation is **intentional** ("I have #2 there on purpose to
  cause previous issues" — read as: kept deliberately for his own testing/learning
  purposes). It was already present identically in `buyer.py`/`seller.py`/`token_creator.py`
  before de-duplication, so centralizing it into `solana_tx.py` preserved it rather
  than reverting to the simpler official pattern. **Do not silently remove this.**

## 6. Environment / infra notes

- **Local dev machine**: macOS (Natnael's MacBook Pro), Python 3.9 (via
  CommandLineTools), project at `~/Youtube Projects/coinvault/coinvault`.
- **Package invocation**: must run `python3 -m src.<module>` from the
  `coinvault/coinvault` root (one level above `src/`), not from inside `src/` itself —
  relative imports (`.config`, `.token_creator`, etc.) require being addressed as a
  submodule of a real package; running bare or from the wrong cwd breaks this in two
  different ways (`No module named 'src'` vs `attempted relative import with no known
  parent package`), covered in detail in this thread if it recurs.
- **RPC endpoint decision**: currently pointed at a local `solana-test-validator`
  (`http://127.0.0.1:8899`) for safe testing with airdropped fake SOL. To exercise
  pump.fun's actual on-chain program locally, the validator needs `--clone` flags for
  all 5 pump.fun addresses already sitting in `config.py`'s defaults
  (`pumpfun_program_id`, `pumpfun_global`, `pumpfun_fee_recipient`,
  `pumpfun_event_authority`, `pumpfun_mint_authority`) plus `--url mainnet-beta` and
  `--reset` on restart (it persists ledger state in `./test-ledger` between runs
  otherwise). ⚠️ These 5 addresses are defaults baked into `config.py` from whenever
  the original bot skeleton was written — not independently re-verified against
  pump.fun's current live on-chain addresses in this thread; worth a spot-check if
  something seems off.
- **RPC provider for eventual real use**: researched free tiers — Alchemy (30M
  CU/month, most generous dedicated free tier), Helius (1M credits/month, 10 RPS,
  Solana-specific enhanced APIs — leaning towards this one for the project's actual
  needs), QuickNode (no permanent free tier, trial only), Chainstack/Ankr (~3M
  requests/month range), dRPC (210M CU/month but shared/public infra, not dedicated).
  No final decision made yet — noted as a future task.

## 7. Known gaps / open items (not yet done, worth raising if relevant)

- **cli.py** has not been reviewed at all in this thread — unknown whether it
  duplicates logic from `tui.py` or has its own bugs.
- **wallet_manager.py's transfer fee estimate** and **seller.py's withdrawal fee**
  are hardcoded at the base 5,000-lamport signature cost, no priority fee — fine
  normally, could cause slow/dropped transfers under network congestion.
- **No retry logic on the Pinata upload calls** — only the PumpPortal `trade-local`
  calls got `post_with_retry()`. If Pinata uploads turn out to be flaky too, same
  treatment could be applied there.
- **Bundle-buy / multi-wallet coordination** exists (`buyer.py`'s `bundle_buy`) but
  hasn't been a focus of review in this thread — worth a pass if that feature becomes
  active, both for correctness and for the market-manipulation/legal-gray-area
  considerations flagged earlier (coordinated multi-wallet buying followed by selling
  into retail is a pattern with real regulatory/reputational surface — not legal
  advice, just a flag).
- **Private key storage**: `DEV_WALLET_PRIVATE_KEY`/`FUND_WALLET_PRIVATE_KEYS` sit
  in `.env` in plaintext, unlike the Pinata JWT, these are **not rotatable** — a leak
  means permanent loss of whatever's in those wallets. Worth revisiting before this
  ever touches real mainnet funds at any scale (secrets manager, hardware wallet for
  the dev key, etc. — no action taken yet, just flagged).
- **The 400 fix (gateway swap) is unverified** — see item 8 in the history above.
  This is the most likely next thing to check when picking this back up.

## 8. General working notes for whoever picks this up

- Natnael prefers targeted, iterative fixes over broad rewrites, confirms before
  proceeding, values detailed technical explanations pitched at a CS-undergrad level.
- No em-dashes/en-dashes preference exists for *prose writing* elsewhere (economics
  papers etc.) — not confirmed whether that extends to code comments in this project;
  code comments in these files have used em-dashes throughout this thread without
  objection, so likely fine, but worth noting the general preference exists.
- This is a learning project first, a real trading tool second — explanations of
  *why*, not just *what*, have consistently been the useful mode here.
