---
name: Wave sell & browser auto-open
description: Phase 1 (auto browser open) and Phase 2 (monitor auto-nav + S hotkey sell-all) implementation decisions.
---

## What was built

### Phase 1 — Browser auto-open
- `config.AUTO_OPEN_BROWSER` env var (default true) gates `webbrowser.open()`.
- Fires in CLI at both create-token paths and in TUI `CreateTokenPane._do_create` + `PreloadPane._do_launch`.

### Phase 2 — Monitor auto-nav + sell-all hotkey
- After successful token creation in TUI, `ContentSwitcher.current = "pane-monitor"` then `MonitorPane._on_token_picked(mint)`.
- `MonitorPane` has `Binding("s", "sell_all", ...)` and `_FOOTER_DEFAULT` class attribute used by both `compose` and the `_do_sell_all` worker to restore footer text.
- `seller.wave_sell_all()`: wave 1 = dev + fund[:wave_size-1], wave 2 = fund[wave_size-1:], then `withdraw_all_sol`. Default `SELL_WAVE_SIZE=4` (dev + 3 fund).
- `_do_sell_all` is a `@work(exclusive=True)` worker; updates footer live, restores it in `finally`.

## Key decisions
**Why `_FOOTER_DEFAULT` as a class attribute:** both `compose()` and `_do_sell_all` need the same string; avoids duplication and drift.
**Why `wave_size` counts the dev wallet slot:** user specified "dev + 3 fund" = 4 total in wave 1, so `SELL_WAVE_SIZE=4` maps cleanly; fund-only installs just skip the dev slot.
**Why forward-reference to `MonitorPane` inside `CreateTokenPane._do_create` is safe:** the reference is inside a method body, evaluated at call-time, not at class-definition time.
