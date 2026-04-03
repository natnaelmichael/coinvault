"""
Textual TUI for pump.fun bot — src/tui.py

Arrow-key / mouse-driven interface wrapping the existing buyer, seller,
token_creator and wallet_manager modules unchanged.

Start via:  python main.py tui
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input,
    Label, ListItem, ListView, RichLog, Static,
    Switch, ContentSwitcher, Rule,
)
from rich.text import Text as RichText

from .config import config
from .wallet_manager import wallet_manager, Wallet
from .logger import logger
from .notifications import notification_manager
from .token_creator import get_token_creator, TokenMetadata
from .buyer import get_token_buyer
from .seller import get_token_seller


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

# Resolve project root from this file's location (src/tui.py → project root is one level up).
# Using __file__-relative paths means the bot works regardless of which directory
# the user runs `python3 main.py` from.
_PROJECT_ROOT       = Path(__file__).resolve().parent.parent
_CREATED_TOKENS_PATH = _PROJECT_ROOT / "data" / "created_tokens.json"
WATCHLIST_PATH       = _PROJECT_ROOT / "data" / "watchlist.json"


def _load_created_tokens() -> list:
    """
    Load all known tokens from the registry, merging two locations:
      1. <project_root>/created_tokens/*.json  — one file per token (CLI legacy)
      2. <project_root>/data/created_tokens.json — flat list (primary write target)

    Deduplicates by mint address. Entries missing a mint are skipped silently
    so a corrupt or partial file never crashes the picker.
    """
    seen: set = set()
    tokens: list = []

    def _add(entry: dict) -> None:
        if not isinstance(entry, dict):
            return
        mint = entry.get("mint", "").strip()
        if mint and mint not in seen:
            seen.add(mint)
            tokens.append(entry)

    # 1. Individual per-token files written by the CLI
    ct_dir = _PROJECT_ROOT / "created_tokens"
    if ct_dir.is_dir():
        for f in sorted(ct_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                if isinstance(data, list):
                    for entry in data:
                        _add(entry)
                elif isinstance(data, dict):
                    _add(data)
            except Exception:
                pass

    # 2. Primary flat-list file written by both CLI and TUI
    if _CREATED_TOKENS_PATH.exists():
        try:
            raw = json.loads(_CREATED_TOKENS_PATH.read_text())
            if isinstance(raw, list):
                for entry in raw:
                    _add(entry)
        except Exception:
            pass

    return tokens


def _save_token(data: dict) -> None:
    _CREATED_TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if _CREATED_TOKENS_PATH.exists():
        try:
            existing = json.loads(_CREATED_TOKENS_PATH.read_text())
        except Exception:
            pass
    existing.append(data)
    _CREATED_TOKENS_PATH.write_text(json.dumps(existing, indent=2))


def _load_watchlist() -> list:
    """Load monitor watchlist from data/watchlist.json."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text())
    except Exception:
        return []


def _save_watchlist(entries: list) -> None:
    """Persist watchlist to disk."""
    WATCHLIST_PATH.parent.mkdir(exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(entries, indent=2))


def _watchlist_add(mint: str, symbol: str = "", name: str = "") -> bool:
    """Add a token to the watchlist. Returns True if it was newly added."""
    mint = mint.strip()
    if not mint:
        return False
    entries = _load_watchlist()
    if any(e.get("mint") == mint for e in entries):
        return False          # already present
    entries.append({
        "mint":     mint,
        "symbol":   symbol.strip().upper() or "?",
        "name":     name.strip() or "",
        "added_at": datetime.now().isoformat(),
    })
    _save_watchlist(entries)
    return True


def _watchlist_remove(mint: str) -> bool:
    """Remove a token from the watchlist by mint. Returns True if it existed."""
    entries = _load_watchlist()
    new = [e for e in entries if e.get("mint") != mint]
    if len(new) == len(entries):
        return False
    _save_watchlist(new)
    return True


def _watchlist_bulk_load() -> int:
    """Merge all created_tokens into the watchlist. Returns count of new additions."""
    added = 0
    for t in _load_created_tokens():
        if _watchlist_add(t.get("mint",""), t.get("symbol",""), t.get("name","")):
            added += 1
    return added


def _fmt_price(p: Optional[float]) -> str:
    if p is None:
        return "—"
    if p < 1e-7:
        return f"{p:.12f}"
    if p < 1e-5:
        return f"{p:.10f}"
    if p < 1e-3:
        return f"{p:.8f}"
    if p < 0.1:
        return f"{p:.6f}"
    return f"{p:.4f}"


SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(prices: list, width: int = 80) -> RichText:
    txt = RichText(no_wrap=True)
    if len(prices) < 2:
        txt.append("  awaiting trades…", style="dim")
        return txt
    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else 1.0
    mid = (mn + mx) / 2.0
    for p in list(prices)[-width:]:
        idx = min(7, int((p - mn) / rng * 8))
        ch = SPARK_CHARS[idx]
        if p >= mid:
            g = int(80 + (p - mid) / (mx - mid + 1e-12) * 175)
            style = f"rgb({max(0, 255 - g // 2)},{min(255, g + 60)},80)"
        else:
            r = int(80 + (mid - p) / (mid - mn + 1e-12) * 175)
            style = f"rgb({min(255, 80 + r)},50,50)"
        txt.append(ch, style=style)
    return txt


def _price_graph(prices: list, rows: int = 12, cols: int = 72, symbol: str = "") -> RichText:
    """
    Render a 2D ASCII price chart as multi-line RichText.

    Each row represents a price band; each column a trade sample.
    Uses half-block characters (▄ ▀) for sub-row resolution and
    colours green above the session mid-price, red below.
    """
    LABEL_W = 14

    txt = RichText(no_wrap=True)

    if len(prices) < 2:
        for i in range(rows + 1):
            if i == rows // 2:
                txt.append(" " * LABEL_W + " │" + "  ⠶  awaiting trade data…\n", style="dim")
            else:
                txt.append(" " * LABEL_W + " │\n", style="dim")
        txt.append(" " * LABEL_W + " └" + "─" * cols + "\n", style="dim")
        return txt

    mn, mx = min(prices), max(prices)
    rng = mx - mn if mx != mn else (mn * 0.001 or 1e-12)
    mid = (mn + mx) / 2.0

    sampled = list(prices)[-cols:]
    n = len(sampled)
    left_pad = max(0, cols - n)

    def p2norm(p: float) -> float:
        return (p - mn) / rng

    norms = [p2norm(p) for p in sampled]

    for r in range(rows):
        row_top = 1.0 - r / rows
        row_bot = 1.0 - (r + 1) / rows

        price_at_top = mn + row_top * rng
        price_at_bot = mn + row_bot * rng
        price_at_mid_row = (price_at_top + price_at_bot) / 2.0

        if r == 0:
            lbl = _fmt_price(mx)
        elif r == rows - 1:
            lbl = _fmt_price(mn)
        elif r == rows // 2:
            lbl = _fmt_price(price_at_mid_row)
        else:
            lbl = ""

        txt.append(lbl.rjust(LABEL_W), style="dim")
        txt.append(" │", style="dim")

        txt.append(" " * left_pad)

        for ci, norm in enumerate(norms):
            p = sampled[ci]
            in_band = row_bot <= norm < row_top

            if in_band:
                col = "bold green" if p >= mid else "bold red"
                frac = (norm - row_bot) / (row_top - row_bot)
                char = "▀" if frac >= 0.5 else "▄"
                txt.append(char, style=col)
            else:
                txt.append(" ")

        txt.append("\n")

    txt.append(" " * LABEL_W + " └" + "─" * (left_pad + n) + "\n", style="dim")

    return txt


# ─────────────────────────────────────────────────────────────────────────────
# Modals
# ─────────────────────────────────────────────────────────────────────────────

class ConfirmModal(ModalScreen):
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal > Container {
        background: $surface; border: double $accent;
        padding: 2 4; width: 60; height: auto;
    }
    ConfirmModal Label { margin-bottom: 1; }
    ConfirmModal Horizontal { height: 3; align: center middle; }
    ConfirmModal Button { margin: 0 2; min-width: 10; }
    """

    def __init__(self, msg: str) -> None:
        super().__init__()
        self._msg = msg

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self._msg)
            with Horizontal():
                yield Button("Yes", variant="success", id="yes")
                yield Button("No", variant="error", id="no")

    @on(Button.Pressed, "#yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _no(self) -> None:
        self.dismiss(False)


class TokenPickerModal(ModalScreen):
    DEFAULT_CSS = """
    TokenPickerModal { align: center middle; }
    TokenPickerModal > Container {
        background: $surface; border: double $accent;
        padding: 1 2; width: 90; height: 32;
    }
    #tk-title { color: $accent; text-style: bold; margin-bottom: 1; }
    #tk-list  { height: 16; border: solid $border; margin-bottom: 1; }
    #tk-list ListItem { padding: 0 1; }
    #tk-list ListItem.--highlight { background: $accent 20%; color: $accent; }
    #tk-sep   { color: $text-muted; margin-bottom: 1; }
    #tk-manual { margin-bottom: 1; }
    TokenPickerModal Horizontal { height: 3; align: right middle; }
    TokenPickerModal Button { margin-left: 1; min-width: 10; }
    """

    def __init__(self, action: str = "select", tokens: Optional[list] = None) -> None:
        super().__init__()
        self._action = action
        self._tokens = tokens if tokens is not None else _load_created_tokens()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Select token — {self._action}", id="tk-title")
            items = []
            for t in self._tokens:
                sym  = t.get("symbol", "?")
                name = t.get("name", "?")[:16]
                mint = t.get("mint", "")
                ts   = (t.get("launched_at") or t.get("created_at") or "")[:10]
                items.append(
                    ListItem(Label(f"  {sym:<8}  {name:<18}  {mint[:26]}…  {ts}"))
                )
            if not items:
                items.append(ListItem(Label("  (no tokens in registry yet)")))
            yield ListView(*items, id="tk-list")
            yield Label("— or paste a mint address below —", id="tk-sep")
            yield Input(placeholder="Base58 mint address…", id="tk-manual")
            with Horizontal():
                yield Button("Select", variant="primary", id="tk-select")
                yield Button("Cancel", id="tk-cancel")

    @on(ListView.Selected)
    def _list_selected(self, event: ListView.Selected) -> None:
        items = list(self.query_one("#tk-list").children)
        try:
            idx = items.index(event.item)
            if 0 <= idx < len(self._tokens):
                self.dismiss(self._tokens[idx]["mint"])
        except ValueError:
            pass

    @on(Button.Pressed, "#tk-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#tk-select")
    def _select(self) -> None:
        manual = self.query_one("#tk-manual", Input).value.strip()
        if manual:
            try:
                from solders.pubkey import Pubkey
                Pubkey.from_string(manual)
                self.dismiss(manual)
            except Exception:
                self.notify("Invalid base58 mint address", severity="error")
            return
        lv = self.query_one("#tk-list", ListView)
        if lv.highlighted_child:
            items = list(lv.children)
            try:
                idx = items.index(lv.highlighted_child)
                if 0 <= idx < len(self._tokens):
                    self.dismiss(self._tokens[idx]["mint"])
                    return
            except ValueError:
                pass
        self.notify("Nothing selected", severity="warning")


class TokenListModal(ModalScreen):
    """
    Watchlist management modal — opened via Ctrl+L on the Monitor pane.

    Lets the user:
      • View and scroll the current watchlist
      • Remove any entry with the Remove button
      • Add a token manually by mint address (+ optional symbol)
      • Bulk-load every token from the created_tokens registry in one go
    """

    DEFAULT_CSS = """
    TokenListModal { align: center middle; }
    TokenListModal > Container {
        background: $surface; border: double $accent;
        padding: 1 2; width: 96; height: 38;
        layout: vertical;
    }
    #tl-title {
        color: $accent; text-style: bold;
        margin-bottom: 1; border-bottom: solid $border;
        padding-bottom: 1;
    }
    #tl-list {
        height: 12; border: solid $border; margin-bottom: 1;
    }
    #tl-list ListItem { padding: 0 1; }
    #tl-list ListItem.--highlight {
        background: $accent 20%; color: $accent; text-style: bold;
    }
    #tl-list-empty { color: $text-muted; margin: 1 0; }
    #tl-action-row { height: 3; margin-bottom: 1; }
    #tl-action-row Button { margin-right: 1; }
    #tl-sep {
        color: $text-muted; text-style: italic;
        border-top: solid $border; padding-top: 1; margin-bottom: 1;
    }
    #tl-add-grid { height: 3; layout: horizontal; align: left middle; margin-bottom: 1; }
    #tl-mint-label  { width: 18; color: $text-muted; text-align: right; padding-right: 1; }
    #tl-mint-input  { width: 1fr; }
    #tl-sym-grid  { height: 3; layout: horizontal; align: left middle; margin-bottom: 1; }
    #tl-sym-label   { width: 18; color: $text-muted; text-align: right; padding-right: 1; }
    #tl-sym-input   { width: 20; }
    #tl-bottom-row  { height: 3; align: right middle; }
    #tl-bottom-row Button { margin-left: 1; }
    #tl-status { color: $success; height: 2; margin-bottom: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._entries: list = _load_watchlist()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("📋  Manage Token Watchlist", id="tl-title")
            yield Static("", id="tl-status")
            yield self._build_list()
            with Horizontal(id="tl-action-row"):
                yield Button("Remove Selected", variant="warning", id="btn-tl-remove")
                yield Button("⬇  Load All Created Tokens", variant="primary", id="btn-tl-bulk")
            yield Label("── Add token manually ──", id="tl-sep")
            with Horizontal(id="tl-add-grid"):
                yield Label("Mint address:", id="tl-mint-label")
                yield Input(placeholder="Base58 address…", id="tl-mint-input")
            with Horizontal(id="tl-sym-grid"):
                yield Label("Symbol (opt.):", id="tl-sym-label")
                yield Input(placeholder="e.g. DOGE2", id="tl-sym-input")
            with Horizontal(id="tl-bottom-row"):
                yield Button("Add to Watchlist", variant="success", id="btn-tl-add")
                yield Button("Close", id="btn-tl-close")

    def _build_list(self) -> ListView:
        items = []
        for e in self._entries:
            sym  = e.get("symbol", "?")
            mint = e.get("mint", "")
            ts   = (e.get("added_at") or "")[:10]
            items.append(
                ListItem(Label(f"  {sym:<10}  {mint[:34]}…  [dim]{ts}[/dim]"))
            )
        lv = ListView(*items, id="tl-list") if items else ListView(
            ListItem(Label("  (watchlist is empty)", id="tl-list-empty")),
            id="tl-list",
        )
        return lv

    def _refresh_list(self) -> None:
        """Rebuild the list widget in-place after a data change."""
        old = self.query_one("#tl-list", ListView)
        new = self._build_list()
        old.remove()
        # Mount the new ListView before the action-row
        action_row = self.query_one("#tl-action-row")
        self.query_one("Container").mount(new, before=action_row)

    def _set_status(self, msg: str) -> None:
        self.query_one("#tl-status", Static).update(msg)

    # ── Remove ────────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-tl-remove")
    def on_remove(self) -> None:
        lv = self.query_one("#tl-list", ListView)
        if lv.highlighted_child is None:
            self.notify("Highlight a token in the list first", severity="warning")
            return
        items = list(lv.children)
        try:
            idx = items.index(lv.highlighted_child)
        except ValueError:
            return
        if idx < 0 or idx >= len(self._entries):
            return
        entry = self._entries[idx]
        sym   = entry.get("symbol", entry.get("mint","?")[:12])
        mint  = entry.get("mint", "")
        if _watchlist_remove(mint):
            self._entries = _load_watchlist()
            self._refresh_list()
            self._set_status(f"[green]✓ Removed {sym}[/green]")
        else:
            self._set_status(f"[red]✗ Could not remove {sym}[/red]")

    # ── Bulk load ─────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-tl-bulk")
    def on_bulk(self) -> None:
        added = _watchlist_bulk_load()
        self._entries = _load_watchlist()
        self._refresh_list()
        if added:
            self._set_status(
                f"[green]✓ Added {added} token{'s' if added != 1 else ''} from created_tokens[/green]"
            )
        else:
            self._set_status("[dim]No new tokens — all already in watchlist[/dim]")

    # ── Add manually ──────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-tl-add")
    def on_add(self) -> None:
        mint = self.query_one("#tl-mint-input", Input).value.strip()
        sym  = self.query_one("#tl-sym-input",  Input).value.strip()
        if not mint:
            self.notify("Enter a mint address first", severity="warning")
            return
        try:
            from solders.pubkey import Pubkey
            Pubkey.from_string(mint)
        except Exception:
            self.notify("Invalid base58 mint address", severity="error")
            return
        if _watchlist_add(mint, sym):
            self._entries = _load_watchlist()
            self._refresh_list()
            self.query_one("#tl-mint-input", Input).value = ""
            self.query_one("#tl-sym-input",  Input).value = ""
            self._set_status(f"[green]✓ Added {sym or mint[:16]}[/green]")
        else:
            self._set_status("[dim]Token already in watchlist[/dim]")

    # ── Close ─────────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-tl-close")
    def on_close(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
# Pane widgets
# ─────────────────────────────────────────────────────────────────────────────

class BalancesPane(Container):
    """💰 Wallet balances with auto-refresh."""

    DEFAULT_CSS = """
    BalancesPane { padding: 1 2; layout: vertical; height: 1fr; }
    BalancesPane .pane-title { color: $accent; text-style: bold; margin-bottom: 1; }
    BalancesPane DataTable  { height: 1fr; border: solid $border; }
    BalancesPane .btn-row   { height: 3; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("💰  Wallet Balances", classes="pane-title")
        yield DataTable(id="bal-table", cursor_type="row")
        with Horizontal(classes="btn-row"):
            yield Button("Refresh Balances", variant="primary", id="btn-bal-refresh")

    def on_mount(self) -> None:
        tbl = self.query_one("#bal-table", DataTable)
        tbl.add_columns("Label", "Address", "Balance (SOL)")
        self._do_refresh()

    @on(Button.Pressed, "#btn-bal-refresh")
    def on_refresh(self) -> None:
        self._do_refresh()

    @work(exclusive=True)
    async def _do_refresh(self) -> None:
        self.query_one("#btn-bal-refresh", Button).disabled = True
        await wallet_manager.update_all_balances()
        tbl = self.query_one("#bal-table", DataTable)
        tbl.clear()
        if wallet_manager.dev_wallet:
            w = wallet_manager.dev_wallet
            tbl.add_row(
                f"[bold]{w.label}[/bold]",
                str(w.public_key),
                f"[bold green]{w.balance_sol:.4f}[/bold green]",
            )
        for w in wallet_manager.fund_wallets:
            tbl.add_row(w.label, str(w.public_key), f"{w.balance_sol:.4f}")
        total = wallet_manager.get_total_balance()
        tbl.add_row(
            "[bold yellow]TOTAL[/bold yellow]",
            f"[dim]{len(wallet_manager.fund_wallets)} fund wallet(s)[/dim]",
            f"[bold yellow]{total:.4f}[/bold yellow]",
        )
        self.query_one("#btn-bal-refresh", Button).disabled = False


class DistributePane(Container):
    """📤 Distribute SOL from dev wallet to fund wallets."""

    DEFAULT_CSS = """
    DistributePane { padding: 1 2; layout: vertical; height: 1fr; }
    DistributePane .pane-title { color: $accent; text-style: bold; margin-bottom: 1; }
    DistributePane .info-bar   { color: $text-muted; margin-bottom: 1; }
    DistributePane .field-row  { height: 3; layout: horizontal; align: left middle; margin-bottom: 0; }
    DistributePane .field-label{ width: 26; text-align: right; padding-right: 1; color: $text-muted; }
    DistributePane .field-input{ width: 24; }
    DistributePane .btn-row    { height: 3; margin-top: 1; }
    DistributePane RichLog     { height: 1fr; border: solid $border; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("📤  Distribute SOL to Fund Wallets", classes="pane-title")
        yield Static(id="dist-info", classes="info-bar")
        with Horizontal(classes="field-row"):
            yield Label("SOL per fund wallet:", classes="field-label")
            yield Input(value="0.1", id="dist-amount", classes="field-input")
        with Horizontal(classes="btn-row"):
            yield Button("Distribute", variant="primary", id="btn-dist")
        yield RichLog(id="dist-log", highlight=True, markup=True)

    def on_show(self) -> None:
        self._refresh_info()

    def _refresh_info(self) -> None:
        dw = wallet_manager.dev_wallet
        nf = len(wallet_manager.fund_wallets)
        if dw:
            self.query_one("#dist-info", Static).update(
                f"Dev balance: [cyan]{dw.balance_sol:.4f} SOL[/cyan]  |  "
                f"Fund wallets: [cyan]{nf}[/cyan]"
            )
        else:
            self.query_one("#dist-info", Static).update(
                "[red]Dev wallet not configured[/red]"
            )

    @on(Button.Pressed, "#btn-dist")
    def on_distribute(self) -> None:
        if not wallet_manager.dev_wallet:
            self.notify("Dev wallet not configured", severity="error")
            return
        if not wallet_manager.fund_wallets:
            self.notify("No fund wallets configured", severity="error")
            return
        try:
            amount = float(self.query_one("#dist-amount", Input).value)
        except ValueError:
            self.notify("Enter a valid SOL amount", severity="error")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Distribute [bold]{amount:.4f} SOL[/bold] to each of "
                f"[bold]{len(wallet_manager.fund_wallets)}[/bold] fund wallets?\n"
                f"Total: {amount * len(wallet_manager.fund_wallets):.4f} SOL + fees"
            ),
            lambda ok: self._do_distribute(amount) if ok else None,
        )

    @work(exclusive=True)
    async def _do_distribute(self, amount: float) -> None:
        log = self.query_one("#dist-log", RichLog)
        log.write(f"[cyan]Distributing {amount:.4f} SOL to {len(wallet_manager.fund_wallets)} wallets…[/cyan]")
        success = await wallet_manager.distribute_sol(amount)
        if success:
            log.write("[green]✓ Distribution complete[/green]")
        else:
            log.write("[red]✗ Distribution failed — check logs[/red]")
        self._refresh_info()


class CreateTokenPane(Container):
    """🪙 Create a new token on pump.fun."""

    DEFAULT_CSS = """
    CreateTokenPane { padding: 1 2; layout: vertical; height: 1fr; }
    CreateTokenPane .pane-title  { color: $accent; text-style: bold; margin-bottom: 1; }
    CreateTokenPane .field-row   { height: 3; layout: horizontal; align: left middle; }
    CreateTokenPane .field-label { width: 22; text-align: right; padding-right: 1; color: $text-muted; }
    CreateTokenPane .field-input { width: 44; }
    CreateTokenPane .section-sep { color: $text-muted; text-style: italic; margin: 1 0; }
    CreateTokenPane .btn-row     { height: 3; margin-top: 1; }
    CreateTokenPane RichLog      { height: 1fr; border: solid $border; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("🪙  Create New Token", classes="pane-title")
        with VerticalScroll(id="create-form"):
            yield Static("Core details", classes="section-sep")
            for fid, label, ph, val in [
                ("ct-name",    "Token name:",    "e.g. My Cool Token",  ""),
                ("ct-symbol",  "Symbol:",        "e.g. MCT",            ""),
                ("ct-desc",    "Description:",   "Short description…",  ""),
                ("ct-image",   "Image path:",    "/path/to/image.png",  ""),
                ("ct-ibuy",    "Initial buy SOL:","0.0",                "0.0"),
            ]:
                with Horizontal(classes="field-row"):
                    yield Label(label, classes="field-label")
                    yield Input(value=val, placeholder=ph, id=fid, classes="field-input")
            yield Static("Social links (optional)", classes="section-sep")
            for fid, label, ph in [
                ("ct-twitter",  "Twitter URL:",  "https://x.com/…"),
                ("ct-telegram", "Telegram URL:", "https://t.me/…"),
                ("ct-website",  "Website:",      "https://…"),
            ]:
                with Horizontal(classes="field-row"):
                    yield Label(label, classes="field-label")
                    yield Input(placeholder=ph, id=fid, classes="field-input")
        with Horizontal(classes="btn-row"):
            yield Button("Create Token", variant="primary", id="btn-create")
            yield Button("Clear Form", id="btn-create-clear")
        yield RichLog(id="create-log", highlight=True, markup=True)

    def _get(self, fid: str) -> str:
        return self.query_one(f"#{fid}", Input).value.strip()

    @on(Button.Pressed, "#btn-create-clear")
    def on_clear(self) -> None:
        for fid in ("ct-name","ct-symbol","ct-desc","ct-image",
                    "ct-twitter","ct-telegram","ct-website"):
            self.query_one(f"#{fid}", Input).value = ""
        self.query_one("#ct-ibuy", Input).value = "0.0"

    @on(Button.Pressed, "#btn-create")
    def on_create(self) -> None:
        if not wallet_manager.dev_wallet:
            self.notify("Dev wallet not configured", severity="error")
            return
        name   = self._get("ct-name")
        symbol = self._get("ct-symbol")
        if not name or not symbol:
            self.notify("Name and Symbol are required", severity="error")
            return
        self.app.push_screen(
            ConfirmModal(f"Create token [bold]{symbol}[/bold] ({name})?"),
            lambda ok: self._do_create() if ok else None,
        )

    @work(exclusive=True)
    async def _do_create(self) -> None:
        log = self.query_one("#create-log", RichLog)
        self.query_one("#btn-create", Button).disabled = True
        try:
            name   = self._get("ct-name")
            symbol = self._get("ct-symbol")
            desc   = self._get("ct-desc")
            image  = self._get("ct-image") or None
            twitter  = self._get("ct-twitter") or None
            telegram = self._get("ct-telegram") or None
            website  = self._get("ct-website") or None
            try:
                ibuy = float(self._get("ct-ibuy") or "0")
            except ValueError:
                ibuy = 0.0

            log.write(f"[cyan]Creating {symbol} — uploading metadata…[/cyan]")
            meta = TokenMetadata(
                name=name, symbol=symbol, description=desc,
                image_path=image, twitter=twitter,
                telegram=telegram, website=website,
            )
            creator = get_token_creator(wallet_manager.rpc_client)
            result  = await creator.create_token(wallet_manager.dev_wallet, meta, ibuy)

            if result and result.get("success"):
                mint = result["mint"]
                sig  = result["signature"]
                log.write(f"[green]✓ Token created![/green]")
                log.write(f"  Mint:      [bold]{mint}[/bold]")
                log.write(f"  Signature: [dim]{sig}[/dim]")
                log.write(f"  pump.fun:  https://pump.fun/coin/{mint}")
                _save_token({
                    "name": name, "symbol": symbol,
                    "mint": mint, "signature": sig,
                    "metadataUri": result.get("metadataUri",""),
                    "creator": result.get("creator",""),
                    "initialBuy": ibuy,
                    "launched_at": datetime.now().isoformat(),
                })
                log.write("[dim]Token saved to registry.[/dim]")
            else:
                log.write("[red]✗ Token creation failed — check logs above[/red]")
        except Exception as exc:
            log.write(f"[red]✗ Error: {exc}[/red]")
        finally:
            self.query_one("#btn-create", Button).disabled = False


class BundleBuyPane(Container):
    """🔄 Bundle buy a token across all fund wallets."""

    DEFAULT_CSS = """
    BundleBuyPane { padding: 1 2; layout: vertical; height: 1fr; }
    BundleBuyPane .pane-title   { color: $accent; text-style: bold; margin-bottom: 1; }
    BundleBuyPane .token-banner {
        background: $accent 12%; border: solid $accent;
        padding: 0 1; height: 3; margin-bottom: 1;
        color: $accent; content-align: left middle;
    }
    BundleBuyPane .field-row    { height: 3; layout: horizontal; align: left middle; }
    BundleBuyPane .field-label  { width: 26; text-align: right; padding-right: 1; color: $text-muted; }
    BundleBuyPane .field-input  { width: 20; }
    BundleBuyPane .btn-row      { height: 3; margin-top: 1; }
    BundleBuyPane .btn-row Button { margin-right: 1; }
    BundleBuyPane RichLog       { height: 1fr; border: solid $border; margin-top: 1; }
    """

    _token_mint: reactive = reactive("")
    _token_sym:  reactive = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("🔄  Bundle Buy Token", classes="pane-title")
        yield Static("[dim]No token selected[/dim]", id="bb-banner", classes="token-banner")
        with Horizontal(classes="btn-row"):
            yield Button("Select Token", id="btn-bb-pick")
        with Horizontal(classes="field-row"):
            yield Label("SOL per wallet:", classes="field-label")
            yield Input(value="0.05", id="bb-amount", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Wallets (blank = all):", classes="field-label")
            yield Input(placeholder=f"1–{len(wallet_manager.fund_wallets)}", id="bb-count", classes="field-input")
        with Horizontal(classes="field-row"):
            yield Label("Delay between buys ms:", classes="field-label")
            yield Input(value="0", id="bb-delay", classes="field-input")
        with Horizontal(classes="btn-row"):
            yield Button("Execute Bundle Buy", variant="success", id="btn-bb-execute")
        yield RichLog(id="bb-log", highlight=True, markup=True)

    @on(Button.Pressed, "#btn-bb-pick")
    def pick_token(self) -> None:
        self.app.push_screen(
            TokenPickerModal("bundle buy"),
            self._on_token_picked,
        )

    def _on_token_picked(self, mint: Optional[str]) -> None:
        if not mint:
            return
        self._token_mint = mint
        tokens = _load_created_tokens()
        sym = next((t.get("symbol","?") for t in tokens if t.get("mint") == mint), "")
        self._token_sym = sym
        self.query_one("#bb-banner", Static).update(
            f"[bold]{sym}[/bold]  [dim]{mint[:32]}…[/dim]"
        )

    @on(Button.Pressed, "#btn-bb-execute")
    def on_execute(self) -> None:
        if not self._token_mint:
            self.notify("Select a token first", severity="warning")
            return
        if not wallet_manager.fund_wallets:
            self.notify("No fund wallets configured", severity="error")
            return
        try:
            amount = float(self.query_one("#bb-amount", Input).value)
        except ValueError:
            self.notify("Enter a valid SOL amount", severity="error")
            return

        count_raw = self.query_one("#bb-count", Input).value.strip()
        count = len(wallet_manager.fund_wallets)
        if count_raw:
            try:
                count = min(int(count_raw), len(wallet_manager.fund_wallets))
            except ValueError:
                self.notify("Wallet count must be a number", severity="error")
                return

        self.app.push_screen(
            ConfirmModal(
                f"Bundle buy [bold]{self._token_sym or self._token_mint[:16]}[/bold]\n"
                f"{count} wallets × {amount:.4f} SOL = [bold]{count * amount:.4f} SOL[/bold] total"
            ),
            lambda ok: self._do_buy(amount, count) if ok else None,
        )

    @work(exclusive=True)
    async def _do_buy(self, amount: float, count: int) -> None:
        log = self.query_one("#bb-log", RichLog)
        self.query_one("#btn-bb-execute", Button).disabled = True
        try:
            try:
                delay_ms = int(self.query_one("#bb-delay", Input).value or "0")
            except ValueError:
                delay_ms = 0

            wallets = wallet_manager.fund_wallets[:count]
            log.write(
                f"[cyan]Bundle buying {self._token_sym} with {len(wallets)} wallets "
                f"({amount:.4f} SOL each)…[/cyan]"
            )
            buyer   = get_token_buyer(wallet_manager.rpc_client)
            results = await buyer.bundle_buy(wallets, self._token_mint, amount, delay_ms=delay_ms)
            ok_count = sum(1 for r in results if r.success)
            for r in results:
                if r.success:
                    log.write(f"  [green]✓[/green] {r.wallet.label}  {(r.signature or '')[:20]}…")
                else:
                    log.write(f"  [red]✗[/red] {r.wallet.label}  {r.error}")
            col = "green" if ok_count == len(results) else "yellow"
            log.write(f"[{col}]Done: {ok_count}/{len(results)} successful[/{col}]")
        except Exception as exc:
            log.write(f"[red]✗ {exc}[/red]")
        finally:
            self.query_one("#btn-bb-execute", Button).disabled = False


class MonitorPane(Container):
    """📊 Live token monitor — PumpPortal WebSocket feed."""

    BINDINGS = [
        Binding("ctrl+l", "token_list", "Manage watchlist", show=True),
    ]

    DEFAULT_CSS = """
    MonitorPane { layout: vertical; height: 1fr; padding: 0; }
    #mon-header {
        height: 6; background: $surface; padding: 0 2;
        border-bottom: solid $border;
    }
    #mon-price  { height: 2; text-style: bold; padding-top: 1; }
    #mon-stats  { height: 2; color: $text-muted; }
    #mon-chart-box {
        height: 18; background: $background;
        border: solid cyan;
        margin: 0 1;
    }
    #mon-chart-title {
        height: 1; padding: 0 1;
        background: $surface;
        color: $text;
        border-bottom: solid $border;
    }
    #mon-chart-graph { height: auto; padding: 0 1; }
    #mon-trades { height: 1fr; }
    #mon-trades DataTable { height: 1fr; border: none; }
    #mon-pick-row {
        height: 3; background: $surface;
        border-bottom: solid $border; padding: 0 2;
        align: left middle;
    }
    #mon-pick-row Button { margin-right: 1; }
    #mon-token-label { color: $accent; text-style: bold; margin-right: 2; }
    #mon-footer {
        height: 2; background: $surface;
        border-top: solid $border; padding: 0 2;
        color: $text-muted; content-align: left middle;
    }
    """

    _token_mint: str = ""
    _token_sym:  str = ""

    def compose(self) -> ComposeResult:
        with Horizontal(id="mon-pick-row"):
            yield Static("[dim]No token selected[/dim]", id="mon-token-label")
            yield Button("Select Token", id="btn-mon-pick")
        with Container(id="mon-header"):
            yield Static("[dim]—[/dim]", id="mon-price")
            yield Static("[dim]awaiting feed…[/dim]", id="mon-stats")
        with Container(id="mon-chart-box"):
            yield Static(
                "[bold cyan]Price Chart[/bold cyan]  [dim]rolling 72 trades · auto-refresh[/dim]",
                id="mon-chart-title",
            )
            yield Static("", id="mon-chart-graph")
        with Container(id="mon-trades"):
            tbl = DataTable(id="mon-table", cursor_type="none")
            yield tbl
        yield Static(
            "[dim]Ctrl+L[/dim] manage watchlist   "
            "[dim]Ctrl+C[/dim] back to menu   "
            "[dim]●[/dim] PumpPortal WebSocket",
            id="mon-footer",
        )

    def on_mount(self) -> None:
        tbl = self.query_one("#mon-table", DataTable)
        tbl.add_columns("Time", "Side", "SOL", "Tokens", "Price (SOL)", "Wallet", "Sig")
        self.set_interval(1.0, self._tick_refresh)

    def _tick_refresh(self) -> None:
        """Called every second to keep the stats display live (e.g. 'last trade X s ago')."""
        if self._state.get("price") is not None:
            self._update_ui(graph=False)

    def on_show(self) -> None:
        if self._token_mint:
            self._ws_connect()

    def on_hide(self) -> None:
        self.workers.cancel_all()

    # ── Token selection ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-mon-pick")
    def pick_token(self) -> None:
        """Open picker reading fresh from data/created_tokens.json."""
        tokens = _load_created_tokens()
        self.app.push_screen(
            TokenPickerModal("monitor", tokens=tokens if tokens else None),
            self._on_token_picked,
        )

    # ── Watchlist management (Ctrl+L) ─────────────────────────────────────────

    def action_token_list(self) -> None:
        """Open the watchlist management modal."""
        self.app.push_screen(TokenListModal(), callback=lambda _: None)

    def _on_token_picked(self, mint: Optional[str]) -> None:
        if not mint:
            return
        self._token_mint = mint
        tokens = _load_created_tokens()
        self._token_sym = next(
            (t.get("symbol","?") for t in tokens if t.get("mint") == mint), ""
        )
        self.query_one("#mon-token-label", Static).update(
            f"[bold]{self._token_sym}[/bold]  [dim]{mint[:30]}…[/dim]"
        )
        # Reset state
        self._prices.clear()
        self._trades.clear()
        self._state.update({
            "price": None, "price_open": None, "price_prev": None,
            "mcap": None, "volume": 0.0, "buys": 0, "sells": 0,
            "start": datetime.now(), "last_trade": None,
        })
        self.query_one("#mon-table", DataTable).clear()
        self._ws_connect()

    # Internal price/trade state (shared between worker and renderer)
    _prices: deque = deque(maxlen=80)
    _trades: deque = deque(maxlen=20)
    _state:  dict  = {
        "price": None, "price_open": None, "price_prev": None,
        "mcap": None, "volume": 0.0, "buys": 0, "sells": 0,
        "start": None, "last_trade": None,
    }

    @work(exclusive=True)
    async def _ws_connect(self) -> None:
        try:
            import websockets
        except ImportError:
            self.query_one("#mon-stats", Static).update(
                "[red]✗ 'websockets' not installed — pip install websockets[/red]"
            )
            return

        import json as _json

        uri = "wss://pumpportal.fun/api/data"
        delay = 2

        while True:
            try:
                async with websockets.connect(
                    uri, ping_interval=20, ping_timeout=15, close_timeout=5
                ) as ws:
                    await ws.send(_json.dumps({
                        "method": "subscribeTokenTrade",
                        "keys": [self._token_mint],
                    }))
                    self.query_one("#mon-stats", Static).update(
                        "[green]● connected[/green]  awaiting trades…"
                    )
                    delay = 2
                    async for raw in ws:
                        try:
                            data = _json.loads(raw)
                        except Exception:
                            continue
                        if data.get("mint") != self._token_mint:
                            continue
                        self._ingest(data)
                        self._update_ui()

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.query_one("#mon-stats", Static).update(
                    f"[yellow]○ reconnecting in {delay}s — {exc}[/yellow]"
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    def _ingest(self, data: dict) -> None:
        price = data.get("newTokenPrice")
        if not price:
            vs = data.get("vSolInBondingCurve")
            vt = data.get("vTokensInBondingCurve")
            if vs and vt and float(vt) > 0:
                price = float(vs) / float(vt)
        if price and float(price) > 0:
            price = float(price)
            self._state["price_prev"] = self._state["price"]
            if self._state["price_open"] is None:
                self._state["price_open"] = price
            self._state["price"] = price
            self._prices.append(price)
        if data.get("marketCapSol"):
            self._state["mcap"] = float(data["marketCapSol"])
        sol = float(data.get("solAmount", 0))
        tok = float(data.get("tokenAmount", 0))
        is_buy = bool(data.get("isBuy", True))
        self._state["volume"] += sol
        self._state["buys" if is_buy else "sells"] += 1
        self._state["last_trade"] = datetime.now()
        self._trades.appendleft({
            "type": "BUY" if is_buy else "SELL",
            "sol":  sol, "tokens": tok,
            "price": self._state["price"],
            "user": str(data.get("user", "")),
            "sig":  str(data.get("signature", "")),
            "time": datetime.now().strftime("%H:%M:%S"),
        })

    def _update_ui(self, graph: bool = True) -> None:
        st    = self._state
        price = st["price"]
        open_ = st["price_open"]
        prev  = st["price_prev"]
        mcap  = st["mcap"]
        vol   = st["volume"]

        # Tick arrow + colour
        tick_col = "green" if (price and prev and price >= prev) else "red"
        tick     = "▲" if tick_col == "green" else "▼"

        # % change
        if price and open_ and open_ > 0:
            pct = (price - open_) / open_ * 100
            pct_s = f"  [{'green' if pct >= 0 else 'red'}]{'+' if pct>=0 else ''}{pct:.2f}%[/{'green' if pct >= 0 else 'red'}]"
        else:
            pct_s = ""

        mcap_s = f"  MCap: [cyan]{mcap:.2f} SOL[/cyan]" if mcap else ""
        price_col = "green" if (price and open_ and price >= open_) else "red"

        self.query_one("#mon-price", Static).update(
            f"[bold {price_col}]{_fmt_price(price)} SOL[/bold {price_col}]  "
            f"[{tick_col}]{tick}[/{tick_col}]{pct_s}{mcap_s}"
        )

        b, s = st["buys"], st["sells"]
        bsr  = f"{b/s:.2f}" if s > 0 else "∞"
        last_s = ""
        if st["last_trade"]:
            ago = int((datetime.now() - st["last_trade"]).total_seconds())
            last_s = f"  Last trade: [dim]{ago}s ago[/dim]"
        self.query_one("#mon-stats", Static).update(
            f"Vol: [magenta]{vol:.4f} SOL[/magenta]  "
            f"Buys: [green]{b}[/green]  Sells: [red]{s}[/red]  "
            f"B/S: [yellow]{bsr}[/yellow]{last_s}"
        )

        # 2-D price chart (redrawn on every new trade; skipped on 1s tick)
        if graph:
            pl = list(self._prices)
            sym_label = f"[bold white]{self._token_sym}[/bold white]  " if self._token_sym else ""
            n_trades = len(pl)
            self.query_one("#mon-chart-title", Static).update(
                f"[bold cyan]Price Chart[/bold cyan]  {sym_label}"
                f"[dim]rolling 72 trades  ·  {n_trades} pts  ·  auto-refresh[/dim]"
            )
            self.query_one("#mon-chart-graph", Static).update(
                _price_graph(pl, rows=12, cols=72, symbol=self._token_sym)
            )

        # Latest trade row (prepend to table)
        if self._trades:
            tr  = self._trades[0]
            tbl = self.query_one("#mon-table", DataTable)
            is_buy = tr["type"] == "BUY"
            side   = "[bold green]▲ BUY[/bold green]" if is_buy else "[bold red]▼ SELL[/bold red]"
            def _ftok(v: float) -> str:
                if v >= 1_000_000: return f"{v/1_000_000:.2f}M"
                if v >= 1_000:     return f"{v/1_000:.1f}K"
                return f"{v:.0f}"
            tbl.add_row(
                tr["time"], side,
                f"{tr['sol']:.4f}",
                _ftok(tr["tokens"]),
                _fmt_price(tr.get("price")),
                f"[dim]{tr['user'][:10]}…[/dim]",
                f"[dim]{tr['sig'][:14]}…[/dim]",
                key=f"{tr['time']}{tr['sig'][:8]}",
            )
            # Keep table trimmed to last 20 rows
            while tbl.row_count > 20:
                tbl.remove_row(tbl.rows[list(tbl.rows.keys())[0]])


class SellWithdrawPane(Container):
    """💸 Sell tokens and withdraw SOL to dev wallet."""

    DEFAULT_CSS = """
    SellWithdrawPane { padding: 1 2; layout: vertical; height: 1fr; }
    SellWithdrawPane .pane-title   { color: $accent; text-style: bold; margin-bottom: 1; }
    SellWithdrawPane .token-banner {
        background: $accent 12%; border: solid $accent;
        padding: 0 1; height: 3; margin-bottom: 1;
        color: $accent; content-align: left middle;
    }
    SellWithdrawPane .field-row   { height: 3; layout: horizontal; align: left middle; }
    SellWithdrawPane .field-label { width: 26; text-align: right; padding-right: 1; color: $text-muted; }
    SellWithdrawPane .field-input { width: 20; }
    SellWithdrawPane .mode-btns   { height: 3; layout: horizontal; margin-bottom: 1; }
    SellWithdrawPane .mode-btns Button { margin-right: 1; }
    SellWithdrawPane .btn-row     { height: 3; margin-top: 1; }
    SellWithdrawPane .toggle-row  { height: 3; layout: horizontal; align: left middle; margin-top: 1; }
    SellWithdrawPane RichLog      { height: 1fr; border: solid $border; margin-top: 1; }
    SellWithdrawPane #sw-pct-row  { display: none; }
    SellWithdrawPane #sw-amt-row  { display: none; }
    """

    _token_mint: str = ""
    _token_sym:  str = ""
    _sell_mode:  str = "all"   # "all" | "pct" | "amount"

    def compose(self) -> ComposeResult:
        yield Static("💸  Sell & Withdraw All", classes="pane-title")
        yield Static("[dim]No token selected[/dim]", id="sw-banner", classes="token-banner")
        with Horizontal(classes="mode-btns"):
            yield Button("Select Token", id="btn-sw-pick")
        yield Static("[dim]Sell mode:[/dim]")
        with Horizontal(classes="mode-btns"):
            yield Button("Sell All",    variant="success", id="btn-mode-all")
            yield Button("By %",        id="btn-mode-pct")
            yield Button("By Amount",   id="btn-mode-amt")
        with Horizontal(classes="field-row", id="sw-pct-row"):
            yield Label("Percentage (1-100):", classes="field-label")
            yield Input(value="100", id="sw-pct", classes="field-input")
        with Horizontal(classes="field-row", id="sw-amt-row"):
            yield Label("Token amount:", classes="field-label")
            yield Input(placeholder="0.0", id="sw-amt", classes="field-input")
        with Horizontal(classes="toggle-row"):
            yield Label("Withdraw SOL after sell:", classes="field-label")
            yield Switch(value=True, id="sw-withdraw")
        with Horizontal(classes="btn-row"):
            yield Button("Execute Sell & Withdraw", variant="error", id="btn-sw-exec")
        yield RichLog(id="sw-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._set_mode("all")

    def _set_mode(self, mode: str) -> None:
        self._sell_mode = mode
        self.query_one("#sw-pct-row").display = (mode == "pct")
        self.query_one("#sw-amt-row").display = (mode == "amount")

    @on(Button.Pressed, "#btn-sw-pick")
    def pick_token(self) -> None:
        self.app.push_screen(
            TokenPickerModal("sell"),
            self._on_token_picked,
        )

    def _on_token_picked(self, mint: Optional[str]) -> None:
        if not mint:
            return
        self._token_mint = mint
        tokens = _load_created_tokens()
        self._token_sym = next(
            (t.get("symbol","?") for t in tokens if t.get("mint") == mint), ""
        )
        self.query_one("#sw-banner", Static).update(
            f"[bold]{self._token_sym}[/bold]  [dim]{mint[:32]}…[/dim]"
        )

    @on(Button.Pressed, "#btn-mode-all")
    def mode_all(self) -> None: self._set_mode("all")

    @on(Button.Pressed, "#btn-mode-pct")
    def mode_pct(self) -> None: self._set_mode("pct")

    @on(Button.Pressed, "#btn-mode-amt")
    def mode_amt(self) -> None: self._set_mode("amount")

    @on(Button.Pressed, "#btn-sw-exec")
    def on_execute(self) -> None:
        if not self._token_mint:
            self.notify("Select a token first", severity="warning")
            return
        if not wallet_manager.fund_wallets:
            self.notify("No fund wallets configured", severity="error")
            return
        self.app.push_screen(
            ConfirmModal(
                f"Sell [bold]{self._sell_mode}[/bold] of [bold]{self._token_sym}[/bold]\n"
                f"from {len(wallet_manager.fund_wallets)} wallets?"
            ),
            lambda ok: self._do_sell() if ok else None,
        )

    @work(exclusive=True)
    async def _do_sell(self) -> None:
        log = self.query_one("#sw-log", RichLog)
        self.query_one("#btn-sw-exec", Button).disabled = True
        try:
            amount_tokens = None
            percentage    = None
            if self._sell_mode == "pct":
                try:
                    percentage = int(self.query_one("#sw-pct", Input).value)
                except ValueError:
                    percentage = 100
            elif self._sell_mode == "amount":
                try:
                    amount_tokens = float(self.query_one("#sw-amt", Input).value)
                except ValueError:
                    amount_tokens = None

            withdraw = self.query_one("#sw-withdraw", Switch).value

            log.write(f"[cyan]Selling {self._token_sym} from {len(wallet_manager.fund_wallets)} wallets…[/cyan]")
            seller  = get_token_seller(wallet_manager.rpc_client)
            results = await seller.bundle_sell(
                wallet_manager.fund_wallets,
                self._token_mint,
                amount_tokens,
                percentage,
            )
            ok_count = 0
            for r in results:
                if r.success:
                    ok_count += 1
                    log.write(f"  [green]✓[/green] {r.wallet.label}  {(r.signature or '')[:20]}…")
                else:
                    log.write(f"  [red]✗[/red] {r.wallet.label}  {r.error}")
            col = "green" if ok_count == len(results) else "yellow"
            log.write(f"[{col}]Sell done: {ok_count}/{len(results)}[/{col}]")

            if withdraw and wallet_manager.dev_wallet:
                log.write("[cyan]Withdrawing SOL to dev wallet…[/cyan]")
                wr = await seller.withdraw_all_sol(
                    wallet_manager.fund_wallets, wallet_manager.dev_wallet
                )
                if wr.get("success"):
                    total = wr.get("total_withdrawn", 0)
                    dry   = " [dim](dry run)[/dim]" if wr.get("dry_run") else ""
                    log.write(f"[green]✓ Withdrew {total:.4f} SOL{dry}[/green]")
                    for r in wr.get("results", []):
                        if r.get("success"):
                            log.write(
                                f"  [green]✓[/green] {r['wallet']}  "
                                f"{r['amount_sol']:.6f} SOL  {r['signature'][:16]}…"
                            )
                        else:
                            log.write(f"  [red]✗[/red] {r['wallet']}  {r.get('error','?')}")
                else:
                    log.write("[red]✗ Withdrawal failed[/red]")
        except Exception as exc:
            log.write(f"[red]✗ {exc}[/red]")
        finally:
            self.query_one("#btn-sw-exec", Button).disabled = False


class PreloadPane(Container):
    """💾 Pre-load token metadata for later launch."""

    DEFAULT_CSS = """
    PreloadPane { padding: 1 2; layout: vertical; height: 1fr; }
    PreloadPane .pane-title  { color: $accent; text-style: bold; margin-bottom: 1; }
    PreloadPane .field-row   { height: 3; layout: horizontal; align: left middle; }
    PreloadPane .field-label { width: 22; text-align: right; padding-right: 1; color: $text-muted; }
    PreloadPane .field-input { width: 44; }
    PreloadPane .btn-row     { height: 3; margin-top: 1; }
    PreloadPane .btn-row Button { margin-right: 1; }
    PreloadPane DataTable    { height: 1fr; border: solid $border; margin-top: 1; }
    PreloadPane RichLog      { height: 8; border: solid $border; margin-top: 1; }
    PreloadPane #pl-form     { display: none; }
    """

    _view: str = "list"   # "list" | "form"

    def compose(self) -> ComposeResult:
        yield Static("💾  Pre-load Token & Launch Later", classes="pane-title")
        with Horizontal(classes="btn-row"):
            yield Button("Pre-load New", id="btn-pl-new")
            yield Button("Launch Pre-loaded", variant="primary", id="btn-pl-launch")
            yield Button("Refresh List", id="btn-pl-refresh")
        yield DataTable(id="pl-table", cursor_type="row")
        with Container(id="pl-form"):
            for fid, label, ph in [
                ("pl-name",    "Token Name:",   "My Token"),
                ("pl-symbol",  "Symbol:",       "MTK"),
                ("pl-desc",    "Description:",  "…"),
                ("pl-image",   "Image path:",   "/path/image.png"),
                ("pl-ibuy",    "Initial buy SOL:","0.0"),
            ]:
                with Horizontal(classes="field-row"):
                    yield Label(label, classes="field-label")
                    yield Input(placeholder=ph, id=fid, classes="field-input")
            with Horizontal(classes="btn-row"):
                yield Button("Save Pre-load", variant="success", id="btn-pl-save")
                yield Button("Cancel", id="btn-pl-cancel")
        yield RichLog(id="pl-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        tbl = self.query_one("#pl-table", DataTable)
        tbl.add_columns("#", "Name", "Symbol", "Status", "Initial Buy")
        self._refresh_list()

    def on_show(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        tbl = self.query_one("#pl-table", DataTable)
        tbl.clear()
        p = _PROJECT_ROOT / "data" / "preloaded_tokens.json"
        if not p.exists():
            return
        try:
            tokens = json.loads(p.read_text())
        except Exception:
            return
        for i, t in enumerate(tokens, 1):
            status = "✓ Launched" if t.get("status") == "launched" else "⏳ Pre-loaded"
            tbl.add_row(
                str(i),
                t.get("name","?"),
                t.get("symbol","?"),
                status,
                f"{t.get('initial_buy',0)} SOL",
            )

    @on(Button.Pressed, "#btn-pl-refresh")
    def on_refresh(self) -> None:
        self._refresh_list()

    @on(Button.Pressed, "#btn-pl-new")
    def on_new(self) -> None:
        self.query_one("#pl-form").display  = True
        self.query_one("#pl-table").display = False

    @on(Button.Pressed, "#btn-pl-cancel")
    def on_cancel(self) -> None:
        self.query_one("#pl-form").display  = False
        self.query_one("#pl-table").display = True

    @on(Button.Pressed, "#btn-pl-save")
    def on_save(self) -> None:
        def _get(fid: str) -> str:
            return self.query_one(f"#{fid}", Input).value.strip()
        name   = _get("pl-name")
        symbol = _get("pl-symbol")
        if not name or not symbol:
            self.notify("Name and Symbol required", severity="error")
            return
        try:
            ibuy = float(_get("pl-ibuy") or "0")
        except ValueError:
            ibuy = 0.0
        p = _PROJECT_ROOT / "data" / "preloaded_tokens.json"
        p.parent.mkdir(exist_ok=True)
        tokens = []
        if p.exists():
            try:
                tokens = json.loads(p.read_text())
            except Exception:
                pass
        tokens.append({
            "name": name, "symbol": symbol,
            "description": _get("pl-desc"),
            "image_path":  _get("pl-image") or None,
            "initial_buy": ibuy,
            "created_at":  datetime.now().isoformat(),
            "status":      "preloaded",
        })
        p.write_text(json.dumps(tokens, indent=2))
        self.notify(f"Pre-loaded {symbol}", severity="information")
        self.on_cancel()
        self._refresh_list()

    @on(Button.Pressed, "#btn-pl-launch")
    def on_launch(self) -> None:
        tbl = self.query_one("#pl-table", DataTable)
        if tbl.cursor_row is None:
            self.notify("Select a token row first", severity="warning")
            return
        self._do_launch(tbl.cursor_row)

    @work(exclusive=True)
    async def _do_launch(self, row_idx: int) -> None:
        log = self.query_one("#pl-log", RichLog)
        p   = _PROJECT_ROOT / "data" / "preloaded_tokens.json"
        if not p.exists():
            return
        try:
            tokens = json.loads(p.read_text())
        except Exception:
            return
        if row_idx >= len(tokens):
            return
        t = tokens[row_idx]
        if not wallet_manager.dev_wallet:
            log.write("[red]✗ Dev wallet not configured[/red]")
            return
        log.write(f"[cyan]Launching {t.get('symbol')}…[/cyan]")
        meta = TokenMetadata(
            name=t.get("name",""), symbol=t.get("symbol",""),
            description=t.get("description",""),
            image_path=t.get("image_path"),
        )
        creator = get_token_creator(wallet_manager.rpc_client)
        result  = await creator.create_token(
            wallet_manager.dev_wallet, meta, t.get("initial_buy", 0)
        )
        if result and result.get("success"):
            mint = result["mint"]
            t["status"] = "launched"
            t["mint"]   = mint
            t["launched_at"] = datetime.now().isoformat()
            p.write_text(json.dumps(tokens, indent=2))
            _save_token({
                "name": t["name"], "symbol": t["symbol"],
                "mint": mint, "signature": result["signature"],
                "metadataUri": result.get("metadataUri",""),
                "launched_at": t["launched_at"],
            })
            log.write(f"[green]✓ Launched!  Mint: {mint}[/green]")
            log.write(f"  https://pump.fun/coin/{mint}")
            self._refresh_list()
        else:
            log.write("[red]✗ Launch failed[/red]")


class ManageWalletsPane(Container):
    """⚙️ Add, remove and view wallets."""

    DEFAULT_CSS = """
    ManageWalletsPane { padding: 1 2; layout: vertical; height: 1fr; }
    ManageWalletsPane .pane-title { color: $accent; text-style: bold; margin-bottom: 1; }
    ManageWalletsPane .btn-row    { height: 3; margin-bottom: 1; }
    ManageWalletsPane .btn-row Button { margin-right: 1; }
    ManageWalletsPane DataTable   { height: 1fr; border: solid $border; }
    ManageWalletsPane RichLog     { height: 8; border: solid $border; margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("⚙️   Manage Wallets", classes="pane-title")
        with Horizontal(classes="btn-row"):
            yield Button("Refresh",       variant="primary", id="btn-wm-refresh")
            yield Button("Add Wallet",    id="btn-wm-add")
            yield Button("Remove Selected", variant="warning", id="btn-wm-remove")
            yield Button("Export Keys",   id="btn-wm-export")
        yield DataTable(id="wm-table", cursor_type="row")
        yield RichLog(id="wm-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        tbl = self.query_one("#wm-table", DataTable)
        tbl.add_columns("Label", "Address", "Balance (SOL)", "Type")
        self._refresh()

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        tbl = self.query_one("#wm-table", DataTable)
        tbl.clear()
        if wallet_manager.dev_wallet:
            w = wallet_manager.dev_wallet
            tbl.add_row(
                f"[bold]{w.label}[/bold]",
                str(w.public_key),
                f"[bold]{w.balance_sol:.4f}[/bold]",
                "[cyan]Dev[/cyan]",
            )
        for w in wallet_manager.fund_wallets:
            tbl.add_row(
                w.label, str(w.public_key),
                f"{w.balance_sol:.4f}", "[dim]Fund[/dim]",
            )

    @on(Button.Pressed, "#btn-wm-refresh")
    def on_refresh(self) -> None:
        self._do_refresh()

    @work(exclusive=True)
    async def _do_refresh(self) -> None:
        await wallet_manager.update_all_balances()
        self._refresh()

    @on(Button.Pressed, "#btn-wm-add")
    def on_add(self) -> None:
        log = self.query_one("#wm-log", RichLog)
        w   = wallet_manager.add_fund_wallet()
        log.write(f"[green]✓ Added {w.label}  {w.public_key}[/green]")
        log.write(f"[bold red]⚠ Save this key:[/bold red] [yellow]{w.get_private_key_base58()}[/yellow]")
        self._refresh()

    @on(Button.Pressed, "#btn-wm-remove")
    def on_remove(self) -> None:
        tbl = self.query_one("#wm-table", DataTable)
        if tbl.cursor_row is None:
            self.notify("Select a wallet row first", severity="warning")
            return
        # Offset: dev wallet is row 0 — fund wallets start at row 1
        fund_idx = tbl.cursor_row - (1 if wallet_manager.dev_wallet else 0)
        if fund_idx < 0:
            self.notify("Cannot remove the dev wallet", severity="error")
            return
        removed = wallet_manager.remove_fund_wallet(fund_idx)
        if removed:
            self.query_one("#wm-log", RichLog).write("[yellow]Wallet removed[/yellow]")
            self._refresh()

    @on(Button.Pressed, "#btn-wm-export")
    def on_export(self) -> None:
        log = self.query_one("#wm-log", RichLog)
        log.write("[bold yellow]⚠ Exporting private keys — keep this safe![/bold yellow]")
        if wallet_manager.dev_wallet:
            w = wallet_manager.dev_wallet
            log.write(f"[bold]{w.label}[/bold]: {w.get_private_key_base58()}")
        for w in wallet_manager.fund_wallets:
            log.write(f"[bold]{w.label}[/bold]: {w.get_private_key_base58()}")


class SettingsPane(Container):
    """🔧 Toggle bot settings with live persistence."""

    DEFAULT_CSS = """
    SettingsPane { padding: 1 2; layout: vertical; height: 1fr; }
    SettingsPane .pane-title   { color: $accent; text-style: bold; margin-bottom: 1; }
    SettingsPane .setting-row  {
        height: 5; layout: horizontal; align: left middle;
        border-bottom: solid $border; padding: 1 0;
    }
    SettingsPane .setting-info { width: 1fr; layout: vertical; }
    SettingsPane .setting-name { text-style: bold; }
    SettingsPane .setting-desc { color: $text-muted; }
    SettingsPane Switch        { margin-left: 2; }
    SettingsPane .save-note    { color: $text-muted; margin-top: 1; }
    """

    SETTINGS = [
        ("dry_run_mode",            "DRY_RUN_MODE",
         "Dry Run Mode",
         "Simulate transactions without sending to the blockchain"),
        ("require_confirmation",    "REQUIRE_CONFIRMATION",
         "Require Confirmations",
         "Ask yes/no before executing trades"),
        ("enable_desktop_notifications", "ENABLE_DESKTOP_NOTIFICATIONS",
         "Desktop Notifications",
         "Show OS notifications for alerts and trade results"),
        ("enable_sound_alerts",     "ENABLE_SOUND_ALERTS",
         "Sound Alerts",
         "Play a sound on price alerts and completions"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("🔧  Settings", classes="pane-title")
        for attr, env_key, name, desc in self.SETTINGS:
            with Horizontal(classes="setting-row"):
                with Vertical(classes="setting-info"):
                    yield Static(name, classes="setting-name")
                    yield Static(desc, classes="setting-desc")
                yield Switch(
                    value=getattr(config, attr, False),
                    id=f"sw-{attr}",
                )
        yield Static(
            "[dim]Changes are persisted to your .env file automatically.[/dim]",
            classes="save-note",
        )

    @on(Switch.Changed)
    def on_switch(self, event: Switch.Changed) -> None:
        sid = event.switch.id or ""
        if not sid.startswith("sw-"):
            return
        attr = sid[3:]
        match = next(((a, k, n, _) for a, k, n, _ in self.SETTINGS if a == attr), None)
        if not match:
            return
        _, env_key, name, _ = match
        new_val = event.value
        setattr(config, attr, new_val)
        saved = config.set(env_key, new_val)
        status = "ON" if new_val else "OFF"
        suffix = "" if saved else " (no .env found)"
        self.notify(f"{name}: {status}{suffix}", severity="information")
        # Reinit subsystems if needed
        if attr == "enable_desktop_notifications":
            notification_manager._init_desktop_notifications()
        elif attr == "enable_sound_alerts":
            notification_manager._init_sound_system()
        # Update mode badge in parent app
        try:
            badge = self.app.query_one("#mode-badge", Static)
            if config.dry_run_mode:
                badge.update("  🔴 DRY RUN")
                badge.set_class(True,  "mode-dry")
                badge.set_class(False, "mode-live")
            else:
                badge.update("  🟢 LIVE")
                badge.set_class(False, "mode-dry")
                badge.set_class(True,  "mode-live")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Main application
# ─────────────────────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("balances",  "💰  Balances"),
    ("distribute","📤  Distribute SOL"),
    ("create",    "🪙  Create Token"),
    ("bundle",    "🔄  Bundle Buy"),
    ("monitor",   "📊  Monitor Token"),
    ("sell",      "💸  Sell & Withdraw"),
    ("preload",   "💾  Pre-load Token"),
    ("wallets",   "⚙️   Manage Wallets"),
    ("settings",  "🔧  Settings"),
]

PANE_IDS = {key: f"pane-{key}" for key, _ in NAV_ITEMS}


class PumpFunApp(App):
    TITLE = "pump.fun bot"
    SUB_TITLE = "v1.0.0"

    BINDINGS = [
        Binding("q",      "quit",          "Quit"),
        Binding("r",      "refresh",       "Refresh"),
        Binding("escape", "focus_nav",     "Menu"),
        Binding("ctrl+b", "toggle_sidebar","Sidebar"),
    ]

    CSS = """
    /* ── Root layout ────────────────────────────────────── */
    Screen { layout: vertical; }

    #body { layout: horizontal; height: 1fr; }

    /* ── Sidebar ────────────────────────────────────────── */
    #sidebar {
        width: 28;
        background: $surface;
        border-right: solid $accent;
        layout: vertical;
        padding: 1 0;
    }
    #sidebar-title {
        text-align: center;
        color: $accent;
        text-style: bold;
        padding: 0 1 1 1;
        border-bottom: solid $border;
        margin-bottom: 1;
    }
    #mode-badge {
        text-align: center;
        padding: 0 1;
        margin: 0 1 1 1;
        border: solid $border;
    }
    .mode-dry  { color: $warning; border: solid $warning; background: $warning 10%; }
    .mode-live { color: $success; border: solid $success; background: $success 10%; }
    #nav-list  { background: transparent; border: none; }
    #nav-list ListItem {
        padding: 0 2;
        color: $text-muted;
    }
    #nav-list ListItem.--highlight {
        background: $accent 20%;
        color: $accent;
        text-style: bold;
    }
    #nav-list ListItem:hover {
        background: $accent 10%;
    }

    /* ── Content ────────────────────────────────────────── */
    #content   { width: 1fr; height: 1fr; }
    ContentSwitcher { width: 1fr; height: 1fr; }

    /* ── Shared pane styles ─────────────────────────────── */
    .pane-title {
        color: $accent;
        text-style: bold;
        border-bottom: solid $border;
        padding-bottom: 1;
        margin-bottom: 1;
    }
    .token-banner {
        background: $accent 12%;
        border: solid $accent;
        color: $accent;
        padding: 0 1;
        height: 3;
        margin-bottom: 1;
        content-align: left middle;
    }
    .btn-row Button { margin-right: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Container(id="sidebar"):
                yield Static("⚡ PUMP.FUN BOT", id="sidebar-title")
                yield Static(
                    "  🔴 DRY RUN" if config.dry_run_mode else "  🟢 LIVE",
                    id="mode-badge",
                    classes="mode-dry" if config.dry_run_mode else "mode-live",
                )
                yield ListView(
                    *[ListItem(Label(label), id=f"nav-{key}") for key, label in NAV_ITEMS],
                    id="nav-list",
                )
            with Container(id="content"):
                with ContentSwitcher(initial="pane-balances"):
                    yield BalancesPane(id="pane-balances")
                    yield DistributePane(id="pane-distribute")
                    yield CreateTokenPane(id="pane-create")
                    yield BundleBuyPane(id="pane-bundle")
                    yield MonitorPane(id="pane-monitor")
                    yield SellWithdrawPane(id="pane-sell")
                    yield PreloadPane(id="pane-preload")
                    yield ManageWalletsPane(id="pane-wallets")
                    yield SettingsPane(id="pane-settings")
        yield Footer()

    async def on_mount(self) -> None:
        self._init_wallets()

    @work(exclusive=True)
    async def _init_wallets(self) -> None:
        self.notify("Initialising wallets…", severity="information", timeout=3)
        await wallet_manager.initialize()
        self.notify(
            f"Ready — {len(wallet_manager.fund_wallets)} fund wallets loaded",
            severity="information",
            timeout=4,
        )
        # Trigger balances pane refresh after init
        try:
            self.query_one(BalancesPane)._do_refresh()
        except Exception:
            pass

    @on(ListView.Selected, "#nav-list")
    def nav_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("nav-"):
            key    = item_id[4:]
            pane_id = f"pane-{key}"
            self.query_one(ContentSwitcher).current = pane_id

    def action_refresh(self) -> None:
        current = self.query_one(ContentSwitcher).current
        if current == "pane-balances":
            self.query_one(BalancesPane)._do_refresh()
        elif current == "pane-wallets":
            self.query_one(ManageWalletsPane)._do_refresh()

    def action_focus_nav(self) -> None:
        self.query_one("#nav-list", ListView).focus()

    def action_toggle_sidebar(self) -> None:
        sb = self.query_one("#sidebar")
        sb.display = not sb.display


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_tui() -> None:
    """Launch the Textual TUI. Call from main.py or directly."""
    app = PumpFunApp()
    app.run()
