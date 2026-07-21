#!/usr/bin/env python3
"""
test_launch_preloaded.py
------------------------
Scripted smoke-test for the PumpFun TUI.

Sequence
--------
1. Boot PumpFunApp in Textual headless-pilot mode (no real terminal needed)
2. Wait for wallet-initialisation worker to finish
3. Navigate programmatically to the Pre-load pane
4. Select the first token row and click "Launch Pre-loaded"
5. Poll active workers until the launch worker finishes (or timeout)
6. Determine pass/fail from preloaded_tokens.json
7. Stream the live log file to stdout throughout, then print the full log at exit

Usage
-----
    python3 test_launch_preloaded.py
    python3 test_launch_preloaded.py --timeout 180
    python3 test_launch_preloaded.py --timeout 60 --dry-run-check

Exit codes
----------
    0  — token status is "launched" after the run
    1  — no pre-loaded tokens / launch failed / timeout
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# ── ensure project root is on sys.path ───────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _banner(title: str) -> None:
    w = 72
    print(f"\n{'═' * w}")
    print(f"  {title}")
    print(f"{'═' * w}")


def _latest_logfile() -> Path | None:
    log_dir = ROOT / "logs"
    if not log_dir.exists():
        return None
    files = sorted(log_dir.glob("pumpfun_bot_*.log"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


async def _tail_log(log_path: Path, stop: asyncio.Event) -> None:
    """
    Background coroutine — reads new bytes from the log file every 0.5 s
    and prints them to stdout with an indented prefix so they're easy to
    distinguish from the test-harness messages.
    """
    offset = 0
    while not stop.is_set():
        try:
            text = log_path.read_text(errors="replace")
            if len(text) > offset:
                chunk = text[offset:]
                for line in chunk.splitlines():
                    if line.strip():
                        print(f"  [log] {line}", flush=True)
                offset = len(text)
        except Exception:
            pass
        await asyncio.sleep(0.5)


def _read_preloaded() -> list[dict]:
    p = ROOT / "data" / "preloaded_tokens.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text()) or []
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Core test
# ─────────────────────────────────────────────────────────────────────────────

async def run_test(timeout_seconds: int) -> int:
    """
    Returns 0 on success, 1 on failure.
    """
    from src.tui import PumpFunApp, PreloadPane
    from textual.widgets import ContentSwitcher, DataTable

    # ── Step 0: snapshot which log file exists before we create a new one ────
    log_before = _latest_logfile()

    app = PumpFunApp()
    stop_tailing = asyncio.Event()
    tail_task: asyncio.Task | None = None

    async with app.run_test(size=(220, 50)) as pilot:

        # ── Step 1: wallet initialisation ────────────────────────────────────
        _banner("Step 1 — Wallet initialisation (waiting 4 s for RPC calls)")
        await pilot.pause(4.0)

        # Start tailing the log file that BotLogger just opened
        log_path = _latest_logfile()
        if log_path and log_path != log_before:
            print(f"[test] Log file: {log_path}", flush=True)
        else:
            log_path = log_before
            print(f"[test] Using existing log: {log_path}", flush=True)

        if log_path:
            tail_task = asyncio.create_task(_tail_log(log_path, stop_tailing))

        # ── Step 2: navigate to Pre-load pane ────────────────────────────────
        _banner("Step 2 — Navigate to Pre-load pane")
        app.query_one(ContentSwitcher).current = "pane-preload"
        await pilot.pause(0.5)

        # ── Step 3: verify tokens exist ───────────────────────────────────────
        _banner("Step 3 — Inspect pre-loaded token list")
        pane = app.query_one(PreloadPane)
        tbl  = pane.query_one("#pl-table", DataTable)

        if tbl.row_count == 0:
            print("[test] ERROR: No pre-loaded tokens found in data/preloaded_tokens.json",
                  file=sys.stderr, flush=True)
            stop_tailing.set()
            if tail_task:
                await asyncio.wait_for(tail_task, timeout=2.0)
            return 1

        tokens = _read_preloaded()
        first  = tokens[0] if tokens else {}
        print(f"[test] {tbl.row_count} token(s) available", flush=True)
        print(f"[test] Row 0 → name={first.get('name','?')}  "
              f"symbol={first.get('symbol','?')}  "
              f"initial_buy={first.get('initial_buy',0)} SOL", flush=True)

        initial_status = first.get("status")
        tbl.move_cursor(row=0)
        await pilot.pause(0.3)

        # ── Step 4: click "Launch Pre-loaded" ────────────────────────────────
        _banner("Step 4 — Click 'Launch Pre-loaded'")
        await pilot.click("#btn-pl-launch")
        print("[test] Button clicked — launch worker started", flush=True)

        # ── Step 5: poll until the launch worker finishes ─────────────────────
        _banner(f"Step 5 — Monitor launch (timeout {timeout_seconds} s)")
        deadline   = time.monotonic() + timeout_seconds
        t_start    = time.monotonic()
        completed  = False

        while time.monotonic() < deadline:
            await pilot.pause(3.0)

            # Check workers via WorkerManager internals
            try:
                active = [w for w in app.workers._workers if not w.is_done]
            except Exception:
                active = []

            elapsed = int(time.monotonic() - t_start)

            if not active:
                print(f"[test] All workers done after {elapsed}s", flush=True)
                completed = True
                break

            names = [getattr(w, "name", "?") for w in active]
            print(f"[test]   {elapsed}s — {len(active)} worker(s) running: {names}", flush=True)

        if not completed:
            print(f"[test] WARNING: timeout ({timeout_seconds}s) reached — "
                  "launch may still be in progress", file=sys.stderr, flush=True)

        await pilot.pause(1.0)   # let final log writes flush

    # ── clean up log tail ─────────────────────────────────────────────────────
    stop_tailing.set()
    if tail_task:
        try:
            await asyncio.wait_for(tail_task, timeout=3.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

    # ── Step 6: determine pass / fail ─────────────────────────────────────────
    _banner("Step 6 — Result")
    final_tokens = _read_preloaded()
    if not final_tokens:
        print("[test] ✗ FAILED — could not read preloaded_tokens.json", file=sys.stderr)
        return 1

    final_status = final_tokens[0].get("status")

    if final_status == "launched":
        mint = final_tokens[0].get("mint", "?")
        print(f"[test] ✓ SUCCESS", flush=True)
        print(f"[test]   Mint:  {mint}", flush=True)
        print(f"[test]   URL:   https://pump.fun/coin/{mint}", flush=True)
        return 0
    else:
        print(f"[test] ✗ FAILED — final status: {final_status!r}", file=sys.stderr)
        if initial_status == "launched":
            print("[test]   (token was already launched before this test run)", file=sys.stderr)
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scripted smoke-test: boot TUI and auto-launch the first pre-loaded token"
    )
    parser.add_argument(
        "--timeout", type=int, default=120, metavar="SECS",
        help="Seconds to wait for the launch worker to finish (default: 120)"
    )
    parser.add_argument(
        "--dry-run-check", action="store_true", default=False,
        help="Expect the token to remain in 'preloaded' state (dry-run mode check)"
    )
    args = parser.parse_args()

    _banner("PumpFun TUI — Scripted Pre-loaded Token Launch Test")
    print(f"  Timeout : {args.timeout}s")
    print(f"  Project : {ROOT}")

    exit_code = asyncio.run(run_test(args.timeout))

    # ── Always dump the full log file to stdout at the end ────────────────────
    log_path = _latest_logfile()
    if log_path:
        _banner(f"FULL LOG — {log_path.name}")
        try:
            print(log_path.read_text(errors="replace"))
        except Exception as e:
            print(f"[test] Could not read log file: {e}", file=sys.stderr)
    else:
        print("\n[test] No log file found in logs/")

    _banner("Test complete")
    print(f"  Exit code: {exit_code}  ({'PASS' if exit_code == 0 else 'FAIL'})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
