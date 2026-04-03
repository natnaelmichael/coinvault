"""
Main CLI Interface
Command-line interface for the pump.fun bot
"""

import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint
from solders.pubkey import Pubkey
import pyfiglet

from .config import config
from .wallet_manager import wallet_manager, Wallet
from .logger import logger
from .notifications import notification_manager
from .token_creator import get_token_creator, TokenMetadata
from .buyer import get_token_buyer
from .seller import get_token_seller


console = Console()


def print_banner():
    """Print application banner"""
    banner = pyfiglet.figlet_format("PUMP.FUN BOT", font="slant")
    console.print(f"[bold cyan]{banner}[/bold cyan]")
    console.print("[dim]Open-source Solana pump.fun trading bot[/dim]\n")


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Pump.fun Bot - Automated Solana token trading"""
    pass


@cli.command()
def start():
    """Start the bot in interactive mode"""
    print_banner()

    # Validate configuration
    is_valid, errors = config.validate()
    if not is_valid:
        console.print("[red]❌ Configuration errors found:[/red]")
        for error in errors:
            console.print(f"  • {error}")
        console.print("\n[yellow]Please check your .env file[/yellow]")
        return

    # Display configuration
    console.print(config.display_summary())

    # Confirm if in live mode
    if not config.dry_run_mode:
        console.print("\n[bold red]⚠️  WARNING: DRY RUN MODE IS DISABLED[/bold red]")
        console.print("[yellow]This will execute REAL transactions with REAL funds![/yellow]")

        if not click.confirm("Do you want to continue?", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return

    # Initialize and run
    asyncio.run(run_bot())


async def run_bot():
    """Main bot execution loop"""
    try:
        # Initialize wallet manager
        await wallet_manager.initialize()

        # Display initial balances
        console.print()
        wallet_manager.display_balances()

        # Start interactive menu
        await interactive_menu()

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        console.print(f"[red]Fatal error: {e}[/red]")
    finally:
        await wallet_manager.close()


async def interactive_menu():
    """Interactive menu for bot operations"""
    while True:
        console.print("\n" + "="*60)
        console.print("[bold cyan]MAIN MENU[/bold cyan]")
        console.print("="*60)
        console.print("1. 💰 View Wallet Balances")
        console.print("2. 📤 Distribute SOL to Fund Wallets")
        console.print("3. 🪙 Create New Token")
        console.print("4. 🔄 Bundle Buy Token")
        console.print("5. 📊 Monitor Token")
        console.print("6. 💸 Sell & Withdraw All")
        console.print("7. 💾 Pre-load Token & Launch Later")
        console.print("8. ⚙️  Manage Wallets")
        console.print("9. 🔧 Settings")
        console.print("10. 🚪 Exit")
        console.print("="*60)

        choice = await asyncio.to_thread(
            click.prompt,
            "\nSelect an option",
            type=int,
            default=1
        )

        if choice == 1:
            await view_balances()
        elif choice == 2:
            await distribute_sol_menu()
        elif choice == 3:
            await create_token_menu()
        elif choice == 4:
            await bundle_buy_menu()
        elif choice == 5:
            await monitor_token_menu()
        elif choice == 6:
            await sell_withdraw_menu()
        elif choice == 7:
            await preload_token_menu()
        elif choice == 8:
            await manage_wallets_menu()
        elif choice == 9:
            await settings_menu()
        elif choice == 10:
            console.print("[yellow]Goodbye! 👋[/yellow]")
            break
        else:
            console.print("[red]Invalid option. Please try again.[/red]")


def _load_created_tokens() -> list:
    """
    Load all known tokens from the registry.

    Checks two locations and merges the results, deduplicating by mint address:
      1. created_tokens/*.json  — one file per token (preferred going-forward)
      2. data/created_tokens.json — legacy flat list written by create_token_menu

    Each entry is expected to have at least a 'mint' key.  Entries missing a
    mint are silently skipped so a half-written file can't crash the picker.
    """
    import json
    from pathlib import Path

    seen: set = set()
    tokens: list = []

    def _add(entry: dict):
        mint = entry.get("mint", "").strip()
        if mint and mint not in seen:
            seen.add(mint)
            tokens.append(entry)

    # 1. Individual files in created_tokens/
    ct_dir = Path("created_tokens")
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
                pass  # Corrupt file — skip silently

    # 2. Legacy flat-list file
    legacy = Path("data/created_tokens.json")
    if legacy.exists():
        try:
            for entry in json.loads(legacy.read_text()):
                _add(entry)
        except Exception:
            pass

    return tokens


async def _select_token_from_registry(action_label: str = "action") -> "str | None":
    """
    Interactive token picker backed by the created_tokens registry.

    Displays a numbered list of known tokens with symbol, truncated mint, and
    launch timestamp when available.  The user can pick by number or choose to
    enter a mint address manually.

    Args:
        action_label: Short verb shown in the header, e.g. "bundle buy" or "sell".

    Returns:
        A validated mint address string, or None if the user cancels.
    """
    from rich.table import Table
    from rich.rule import Rule

    tokens = _load_created_tokens()

    console.print()
    console.print(Rule(f"[bold cyan]SELECT TOKEN — {action_label.upper()}[/bold cyan]"))

    if tokens:
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("#", style="cyan", width=4, justify="right")
        table.add_column("Symbol", style="yellow", width=10)
        table.add_column("Name", style="white", width=18)
        table.add_column("Mint Address", style="dim", width=46)
        table.add_column("Launched", style="green", width=20)

        for i, t in enumerate(tokens, 1):
            launched = t.get("launched_at") or t.get("created_at") or "—"
            # Trim ISO timestamp to date + time without microseconds
            if "T" in launched:
                launched = launched[:16].replace("T", "  ")
            table.add_row(
                str(i),
                t.get("symbol", "?"),
                t.get("name", "?"),
                t.get("mint", ""),
                launched,
            )

        console.print(table)
        console.print(f"[dim]  {len(tokens)} token(s) in registry[/dim]")
        console.print()
        console.print("  [bold]m[/bold]  Enter mint address manually")
        console.print("  [bold]0[/bold]  Cancel")
        console.print()

        while True:
            raw = await asyncio.to_thread(
                click.prompt, "Select a token (number, m, or 0)", type=str, default="1"
            )
            raw = raw.strip().lower()

            if raw == "0":
                console.print("[yellow]Cancelled.[/yellow]")
                return None

            if raw == "m":
                break  # Fall through to manual entry below

            if raw.isdigit():
                idx = int(raw)
                if 1 <= idx <= len(tokens):
                    mint = tokens[idx - 1]["mint"]
                    sym  = tokens[idx - 1].get("symbol", "")
                    console.print(f"[green]✓[/green] Selected: [bold]{sym}[/bold]  [dim]{mint}[/dim]")
                    return mint

            console.print("[red]Invalid selection — enter a number, 'm', or '0'.[/red]")

    else:
        console.print("[yellow]No tokens found in registry.[/yellow]")
        console.print("[dim]  Checked: created_tokens/*.json  and  data/created_tokens.json[/dim]")
        console.print()
        console.print("  [bold]m[/bold]  Enter mint address manually")
        console.print("  [bold]0[/bold]  Cancel")
        console.print()

        raw = await asyncio.to_thread(
            click.prompt, "Select an option (m or 0)", type=str, default="m"
        )
        if raw.strip().lower() == "0":
            console.print("[yellow]Cancelled.[/yellow]")
            return None

    # Manual entry path
    console.print()
    while True:
        mint = await asyncio.to_thread(click.prompt, "Enter mint address", type=str)
        mint = mint.strip()
        try:
            from solders.pubkey import Pubkey
            Pubkey.from_string(mint)
            console.print(f"[green]✓[/green] Mint accepted: [dim]{mint}[/dim]")
            return mint
        except Exception:
            console.print("[red]❌ Invalid mint address — must be a base58 Solana public key. Try again.[/red]")


async def view_balances():
    """View current wallet balances"""
    from rich.table import Table
    from rich.rule import Rule

    console.print("\n[cyan]Updating balances...[/cyan]")
    await wallet_manager.update_all_balances()

    console.print()
    console.print(Rule("[bold magenta]💰 Wallet Balances[/bold magenta]"))

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Label", style="cyan", width=20)
    table.add_column("Address", style="white")
    table.add_column("Balance (SOL)", justify="right", style="green", width=16)

    # Dev wallet
    if wallet_manager.dev_wallet:
        w = wallet_manager.dev_wallet
        table.add_row(
            f"[bold]{w.label}[/bold]",
            str(w.public_key),
            f"[bold]{w.balance_sol:.4f}[/bold]"
        )
    else:
        table.add_row("[yellow]Dev Wallet[/yellow]", "[dim]Not configured[/dim]", "[dim]—[/dim]")

    # Separator between dev and fund wallets
    if wallet_manager.fund_wallets:
        table.add_section()

    # Fund wallets
    if not wallet_manager.fund_wallets:
        table.add_row("[yellow]Fund Wallets[/yellow]", "[dim]None loaded — check FUND_WALLET_PRIVATE_KEYS in .env[/dim]", "[dim]—[/dim]")
    else:
        for w in wallet_manager.fund_wallets:
            table.add_row(
                w.label,
                str(w.public_key),
                f"{w.balance_sol:.4f}"
            )

    # Total row
    table.add_section()
    table.add_row(
        "[bold yellow]TOTAL[/bold yellow]",
        f"[dim]{len(wallet_manager.fund_wallets)} fund wallet(s)[/dim]",
        f"[bold yellow]{wallet_manager.get_total_balance():.4f}[/bold yellow]"
    )

    console.print(table)
    console.print(Rule())


async def distribute_sol_menu():
    """Menu for distributing SOL to fund wallets"""
    console.print("\n[bold cyan]📤 DISTRIBUTE SOL[/bold cyan]")

    if not wallet_manager.dev_wallet:
        console.print("[red]❌ Dev wallet not configured[/red]")
        return

    if not wallet_manager.fund_wallets:
        console.print("[red]❌ No fund wallets configured[/red]")
        return

    # Show current balances
    console.print(f"\n[dim]Dev Wallet Balance: {wallet_manager.dev_wallet.balance_sol:.4f} SOL[/dim]")
    console.print(f"[dim]Number of Fund Wallets: {len(wallet_manager.fund_wallets)}[/dim]\n")

    amount = await asyncio.to_thread(
        click.prompt,
        "Amount of SOL per fund wallet",
        type=float,
        default=0.1
    )

    total_needed = amount * len(wallet_manager.fund_wallets)
    console.print(f"\n[yellow]Total SOL needed: {total_needed:.4f} SOL (+fees)[/yellow]")

    if config.require_confirmation:
        if not await asyncio.to_thread(click.confirm, "Proceed with distribution?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    success = await wallet_manager.distribute_sol(amount)

    if success:
        console.print("[green]✓ Distribution complete![/green]")
        await asyncio.sleep(1)
        await view_balances()


async def create_token_menu():
    """Menu for creating a new token"""
    console.print("[bold cyan]🪙 CREATE NEW TOKEN[/bold cyan]")

    if not wallet_manager.dev_wallet:
        console.print("[red]❌ Dev wallet not configured[/red]")
        return

    # Get token metadata
    console.print("[dim]Enter token details:[/dim]")

    name = await asyncio.to_thread(click.prompt, "Token Name", type=str)
    symbol = await asyncio.to_thread(click.prompt, "Token Symbol", type=str)
    description = await asyncio.to_thread(click.prompt, "Description", type=str, default="")

    # Optional fields
    has_image = await asyncio.to_thread(click.confirm, "Do you have an image file?", default=False)
    image_path = None
    if has_image:
        image_path = await asyncio.to_thread(click.prompt, "Image file path", type=str)

    has_socials = await asyncio.to_thread(click.confirm, "Add social links?", default=False)
    twitter, telegram, website = None, None, None

    if has_socials:
        twitter = await asyncio.to_thread(click.prompt, "Twitter/X URL (optional)", type=str, default="") or None
        telegram = await asyncio.to_thread(click.prompt, "Telegram URL (optional)", type=str, default="") or None
        website = await asyncio.to_thread(click.prompt, "Website URL (optional)", type=str, default="") or None

    # Initial buy amount
    initial_buy = await asyncio.to_thread(click.prompt, "Initial buy amount in SOL (0 for none)", type=float, default=0.0)

    # Create metadata object
    metadata = TokenMetadata(name=name, symbol=symbol, description=description, image_path=image_path,
                            twitter=twitter, telegram=telegram, website=website)

    # Show summary
    console.print("[yellow]Token Summary:[/yellow]")
    console.print(f"  Name: {name}")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Description: {description or 'None'}")
    console.print(f"  Image: {image_path or 'None'}")
    console.print(f"  Initial Buy: {initial_buy} SOL")

    if config.require_confirmation:
        if not await asyncio.to_thread(click.confirm, "Proceed with token creation?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Create token
    console.print("[cyan]Creating token...[/cyan]")
    creator = get_token_creator(wallet_manager.rpc_client)
    result = await creator.create_token(wallet_manager.dev_wallet, metadata, initial_buy)

    if result and result.get('success'):
        console.print("[green]✓ Token created successfully![/green]")
        mint = result['mint']
        sig  = result['signature']

        console.print(f"  Mint Address:  {mint}")
        console.print(f"  Signature:     {sig}")
        console.print(f"  Metadata URI:  {result['metadataUri']}")
        console.print()
        console.print(Panel(
            f"[bold green]🌐 pump.fun[/bold green]  [link=https://pump.fun/coin/{mint}]https://pump.fun/coin/{mint}[/link]\n"
            f"[bold cyan]🔍 Solscan[/bold cyan]   [link=https://solscan.io/tx/{sig}]https://solscan.io/tx/{sig}[/link]",
            title="[bold]Token Links[/bold]",
            border_style="green",
            expand=False
        ))

        # Save token info
        import json
        from pathlib import Path
        token_file = Path("data/created_tokens.json")
        token_file.parent.mkdir(exist_ok=True)
        tokens = []
        if token_file.exists():
            tokens = json.loads(token_file.read_text())
        tokens.append({'name': name, 'symbol': symbol, 'mint': result['mint'],
                      'signature': result['signature'], 'metadataUri': result['metadataUri'],
                      'creator': result['creator'], 'initialBuy': result.get('initialBuy', 0)})
        token_file.write_text(json.dumps(tokens, indent=2))
        console.print(f"[dim]Token info saved to {token_file}[/dim]")

        # ── Auto bundle buy after creation ────────────────────────────────
        if wallet_manager.fund_wallets:
            console.print()
            console.print(Panel(
                f"[bold]Token is live![/bold] Ready to bundle buy with {len(wallet_manager.fund_wallets)} fund wallet(s).\n"
                f"[dim]Mint: {result['mint']}[/dim]",
                title="🚀 Bundle Buy Opportunity",
                border_style="cyan"
            ))

            do_bundle = await asyncio.to_thread(
                click.confirm,
                "Execute bundle buy now with fund wallets?",
                default=True
            )

            if do_bundle:
                await _execute_bundle_buy_for_mint(result['mint'])
        else:
            console.print("[yellow]⚠ No fund wallets configured — skipping bundle buy.[/yellow]")
            console.print("[dim]Add fund wallets via 'Manage Wallets' and use 'Bundle Buy Token' from the main menu.[/dim]")

    else:
        console.print("[red]✗ Token creation failed[/red]")

    await asyncio.to_thread(click.pause, "Press any key to continue")


async def _execute_bundle_buy_for_mint(token_mint: str):
    """
    Shared helper: prompt buy parameters and execute a bundle buy for a known mint.
    Called both from bundle_buy_menu (manual) and create_token_menu (auto after launch).
    """
    await view_balances()

    amount_per_wallet = await asyncio.to_thread(
        click.prompt, "Amount of SOL per wallet", type=float, default=0.01
    )

    use_all = await asyncio.to_thread(click.confirm, "Use all fund wallets?", default=True)
    wallets_to_use = wallet_manager.fund_wallets
    if not use_all:
        count = await asyncio.to_thread(
            click.prompt,
            f"How many wallets to use (1-{len(wallet_manager.fund_wallets)})",
            type=int,
            default=len(wallet_manager.fund_wallets)
        )
        wallets_to_use = wallet_manager.fund_wallets[:count]

    add_delay = await asyncio.to_thread(click.confirm, "Add delay between buys?", default=False)
    delay_ms = 0
    if add_delay:
        delay_ms = await asyncio.to_thread(click.prompt, "Delay in milliseconds", type=int, default=100)

    console.print("[yellow]Bundle Buy Summary:[/yellow]")
    console.print(f"  Token:            {token_mint[:16]}...")
    console.print(f"  Wallets:          {len(wallets_to_use)}")
    console.print(f"  Per wallet:       {amount_per_wallet} SOL")
    console.print(f"  Total:            {amount_per_wallet * len(wallets_to_use):.4f} SOL")
    if delay_ms:
        console.print(f"  Delay:            {delay_ms} ms between buys")

    if config.require_confirmation:
        if not await asyncio.to_thread(click.confirm, "Execute bundle buy?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    console.print("[cyan]Executing bundle buy...[/cyan]")
    buyer = get_token_buyer(wallet_manager.rpc_client)
    results = await buyer.bundle_buy(wallets_to_use, token_mint, amount_per_wallet, delay_ms=delay_ms)

    console.print("[bold]Results:[/bold]")
    successful = 0
    for result in results:
        if result.success:
            successful += 1
            console.print(f"  [green]✓[/green] {result.wallet.label}: {result.signature[:16]}...")
        else:
            console.print(f"  [red]✗[/red] {result.wallet.label}: {result.error}")

    console.print(f"\n[bold]{'[green]' if successful == len(results) else '[yellow]'}{successful}/{len(results)} buys succeeded[/bold]")


async def bundle_buy_menu():
    """Menu for bundle buying a token"""
    console.print("[bold cyan]🔄 BUNDLE BUY TOKEN[/bold cyan]")

    if not wallet_manager.fund_wallets:
        console.print("[red]❌ No fund wallets configured[/red]")
        return

    console.print(f"[dim]Available fund wallets: {len(wallet_manager.fund_wallets)}[/dim]")

    token_mint = await _select_token_from_registry("bundle buy")
    if not token_mint:
        return

    await _execute_bundle_buy_for_mint(token_mint)
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def monitor_token_menu():
    """Menu for monitoring a token — live PumpPortal WebSocket feed"""
    console.print("\n[bold cyan]📊 MONITOR TOKEN[/bold cyan]")

    token_mint = await _select_token_from_registry("monitor")
    if not token_mint:
        return

    # Pull symbol from registry for the display header
    tokens = _load_created_tokens()
    symbol = next(
        (t.get("symbol", "") for t in tokens if t.get("mint") == token_mint), ""
    )

    console.print(f"\n[cyan]Connecting to PumpPortal live feed...[/cyan]")
    console.print("[dim]Press Ctrl+C to return to main menu[/dim]\n")

    await _monitor_token_live(token_mint, symbol)


async def _monitor_token_live(token_mint: str, symbol: str = ""):
    """
    Full-screen live monitor driven by the PumpPortal WebSocket API.

    Subscribes to token trade events for the given mint and renders a
    Rich Live display containing:
      • Header panel  — price, % change, market cap, volume, buy/sell counts
      • Chart panel   — Unicode sparkline of the last 60 trade prices
      • Trades panel  — scrolling table of the most recent 20 trades
    Updates at 4 Hz.  Press Ctrl+C to exit.
    """
    try:
        import websockets
    except ImportError:
        console.print("[red]❌ 'websockets' package not installed.[/red]")
        console.print("[dim]  pip install websockets[/dim]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return

    import json
    from collections import deque
    from datetime import datetime
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.console import Group
    from rich.columns import Columns
    from rich.rule import Rule

    SPARK_CHARS = "▁▂▃▄▅▆▇█"
    CHART_POINTS = 60   # rolling window of trade prices shown in sparkline
    MAX_TRADES   = 20   # rows in the trade feed

    # ── Shared mutable state (WebSocket task writes, renderer reads) ─────────
    prices: deque = deque(maxlen=CHART_POINTS)
    trades: deque = deque(maxlen=MAX_TRADES)
    st = {
        "price":       None,   # latest trade price (SOL per token)
        "price_open":  None,   # first price seen this session (baseline for Δ%)
        "price_prev":  None,   # previous trade price (for tick direction)
        "mcap_sol":    None,
        "volume_sol":  0.0,
        "buys":        0,
        "sells":       0,
        "connected":   False,
        "error":       None,
        "start_time":  datetime.now(),
        "last_trade":  None,
    }

    # ── Formatting helpers ───────────────────────────────────────────────────

    def _fmt_price(p: "float | None") -> str:
        if p is None:
            return "—"
        if p < 0.0000001:
            return f"{p:.12f}"
        if p < 0.00001:
            return f"{p:.10f}"
        if p < 0.001:
            return f"{p:.8f}"
        if p < 0.1:
            return f"{p:.6f}"
        return f"{p:.4f}"

    def _fmt_sol(v: float) -> str:
        return f"{v:.4f} SOL"

    def _fmt_tokens(v: float) -> str:
        if v >= 1_000_000_000:
            return f"{v / 1_000_000_000:.2f}B"
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if v >= 1_000:
            return f"{v / 1_000:.1f}K"
        return f"{v:.0f}"

    def _pct(now: "float | None", ref: "float | None") -> str:
        if now is None or ref is None or ref == 0:
            return ""
        c = (now - ref) / ref * 100
        s = "+" if c >= 0 else ""
        col = "green" if c >= 0 else "red"
        return f"[{col}]{s}{c:.2f}%[/{col}]"

    def _uptime() -> str:
        s = int((datetime.now() - st["start_time"]).total_seconds())
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    # ── Sparkline builder ────────────────────────────────────────────────────

    def _sparkline(price_list: list) -> Text:
        txt = Text(no_wrap=True, overflow="fold")
        if len(price_list) < 2:
            txt.append("  awaiting trades…", style="dim")
            return txt

        mn, mx = min(price_list), max(price_list)
        rng = mx - mn if mx != mn else 1.0
        midpoint = (mn + mx) / 2

        for p in price_list:
            idx  = min(7, int((p - mn) / rng * 8))
            char = SPARK_CHARS[idx]
            if p >= midpoint:
                # Gradient: bright green at top, dim green near mid
                intensity = int(50 + (p - midpoint) / (mx - midpoint + 1e-12) * 155)
                style = f"rgb({max(0,255-intensity//2)},{min(255,intensity+100)},80)"
            else:
                # Red zone below midpoint
                intensity = int((midpoint - p) / (midpoint - mn + 1e-12) * 200)
                style = f"rgb({min(255,150+intensity)},60,60)"
            txt.append(char, style=style)

        return txt

    # ── Layout renderer — called 4× per second ───────────────────────────────

    def _render() -> Group:
        price      = st["price"]
        price_open = st["price_open"]
        price_prev = st["price_prev"]
        mcap       = st["mcap_sol"]
        vol        = st["volume_sol"]
        buys, sells = st["buys"], st["sells"]
        bsr   = f"{buys / sells:.2f}" if sells > 0 else "∞"
        price_list = list(prices)

        # Connection status badge
        if st["error"]:
            conn = Text("✗ ERROR", style="bold red")
        elif st["connected"]:
            conn = Text("● LIVE", style="bold green")
        else:
            conn = Text("○ CONNECTING…", style="bold yellow")

        # Tick direction arrow
        tick = ""
        if price is not None and price_prev is not None:
            tick = " [green]▲[/green]" if price >= price_prev else " [red]▼[/red]"

        # Price colour
        if price and price_open:
            pc = "bold green" if price >= price_open else "bold red"
        else:
            pc = "bold white"

        # ── Header panel ─────────────────────────────────────────────────────
        sym_part  = f"[bold white]{symbol}[/bold white]  " if symbol else ""
        mint_part = f"[dim]{token_mint[:8]}…{token_mint[-6:]}[/dim]"

        title_text = Text.from_markup(f"  {sym_part}{mint_part}   ")
        title_text.append_text(conn)
        title_text.append(f"   [dim]⏱ {_uptime()}[/dim]")

        price_text = Text.from_markup(
            f"  [{pc}]{_fmt_price(price)} SOL[/{pc}]{tick}   "
        )
        price_text.append_text(Text.from_markup(_pct(price, price_open)))
        price_text.append(f"    MCap: ")
        if mcap:
            price_text.append(_fmt_sol(mcap), style="cyan")
        else:
            price_text.append("—", style="dim")

        stats_text = Text.from_markup(
            f"  Vol: [magenta]{_fmt_sol(vol)}[/magenta]    "
            f"Buys: [green]{buys}[/green]    "
            f"Sells: [red]{sells}[/red]    "
            f"B/S: [yellow]{bsr}[/yellow]"
        )
        if st["last_trade"]:
            ago = int((datetime.now() - st["last_trade"]).total_seconds())
            stats_text.append(f"    Last trade: [dim]{ago}s ago[/dim]")

        header_panel = Panel(
            Group(price_text, Text(""), stats_text),
            title=title_text,
            border_style="cyan",
            padding=(0, 1),
        )

        # ── Chart panel ───────────────────────────────────────────────────────
        spark = _sparkline(price_list)
        chart_body = Text("  ")
        chart_body.append_text(spark)

        if len(price_list) >= 2:
            mn_p, mx_p = min(price_list), max(price_list)
            pad_spaces = max(
                1,
                CHART_POINTS - len(_fmt_price(mn_p)) - len(_fmt_price(mx_p)) - 4,
            )
            axis = Text.from_markup(
                f"  [dim]{_fmt_price(mn_p)}[/dim]"
                + " " * pad_spaces
                + f"[dim]{_fmt_price(mx_p)}[/dim]"
            )
        else:
            axis = Text("  no data yet", style="dim")

        chart_panel = Panel(
            Group(Text(""), chart_body, Text(""), axis),
            title=f"[bold]Price Chart[/bold]  [dim]rolling {CHART_POINTS} trades[/dim]",
            border_style="blue",
            padding=(0, 1),
        )

        # ── Trades panel ──────────────────────────────────────────────────────
        t_table = Table(
            show_header=True,
            header_style="bold dim",
            box=None,
            padding=(0, 2),
            expand=True,
            show_edge=False,
        )
        t_table.add_column("Time",    style="dim",    width=10, no_wrap=True)
        t_table.add_column("Side",                    width=6,  no_wrap=True)
        t_table.add_column("SOL",    justify="right", width=12, no_wrap=True)
        t_table.add_column("Tokens", justify="right", width=10, no_wrap=True)
        t_table.add_column("Price",  justify="right", width=16, no_wrap=True)
        t_table.add_column("Wallet",                  width=14, no_wrap=True)
        t_table.add_column("Sig",    style="dim",     width=16, no_wrap=True)

        for tr in list(trades):
            is_buy = tr["type"] == "BUY"
            side   = "[bold green]▲ BUY[/bold green]" if is_buy else "[bold red]▼ SELL[/bold red]"
            t_table.add_row(
                tr["time"],
                side,
                _fmt_sol(tr["sol"]),
                _fmt_tokens(tr["tokens"]),
                _fmt_price(tr.get("price")),
                f"[dim]{tr['user'][:10]}…[/dim]",
                f"[dim]{tr['sig'][:14]}…[/dim]",
            )

        if not trades:
            t_table.add_row(
                "—", "[dim]waiting…[/dim]", "—", "—", "—", "—", "—"
            )

        trades_panel = Panel(
            t_table,
            title="[bold]Recent Trades[/bold]",
            border_style="magenta",
            padding=(0, 0),
        )

        footer = Text.from_markup(
            "  [dim]Ctrl+C[/dim]  return to menu   "
            "[dim]●[/dim]  PumpPortal WebSocket feed   "
            f"[dim]pump.fun/coin/{token_mint[:8]}…[/dim]"
        )

        return Group(header_panel, chart_panel, trades_panel, footer)

    # ── WebSocket feed coroutine ──────────────────────────────────────────────

    async def _ws_feed():
        uri = "wss://pumpportal.fun/api/data"
        reconnect_delay = 2
        while True:
            try:
                async with websockets.connect(
                    uri,
                    ping_interval=20,
                    ping_timeout=15,
                    close_timeout=5,
                ) as ws:
                    st["connected"] = True
                    st["error"] = None
                    reconnect_delay = 2  # reset on successful connect

                    await ws.send(json.dumps({
                        "method": "subscribeTokenTrade",
                        "keys": [token_mint],
                    }))

                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        if data.get("mint") != token_mint:
                            continue

                        # Derive price — prefer explicit field, fall back to curve
                        price = data.get("newTokenPrice")
                        if not price:
                            v_sol = data.get("vSolInBondingCurve")
                            v_tok = data.get("vTokensInBondingCurve")
                            if v_sol and v_tok and v_tok > 0:
                                price = float(v_sol) / float(v_tok)

                        if price and float(price) > 0:
                            price = float(price)
                            st["price_prev"] = st["price"]
                            if st["price_open"] is None:
                                st["price_open"] = price
                            st["price"] = price
                            prices.append(price)

                        if data.get("marketCapSol"):
                            st["mcap_sol"] = float(data["marketCapSol"])

                        sol_amt = float(data.get("solAmount",   0))
                        tok_amt = float(data.get("tokenAmount", 0))
                        is_buy  = bool(data.get("isBuy", True))
                        user    = str(data.get("user",      ""))
                        sig     = str(data.get("signature", ""))

                        st["volume_sol"] += sol_amt
                        if is_buy:
                            st["buys"] += 1
                        else:
                            st["sells"] += 1
                        st["last_trade"] = datetime.now()

                        trades.appendleft({
                            "type":   "BUY" if is_buy else "SELL",
                            "sol":    sol_amt,
                            "tokens": tok_amt,
                            "price":  price,
                            "user":   user,
                            "sig":    sig,
                            "time":   datetime.now().strftime("%H:%M:%S"),
                        })

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                st["connected"] = False
                st["error"] = str(exc)
                # Back off and retry automatically
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30)

    # ── Main render loop ─────────────────────────────────────────────────────
    ws_task = asyncio.create_task(_ws_feed())

    try:
        with Live(
            _render(),
            refresh_per_second=4,
            screen=True,
            console=console,
        ) as live:
            while True:
                live.update(_render())
                await asyncio.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

    console.print("\n[yellow]Monitor stopped.[/yellow]")
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def sell_withdraw_menu():
    """Menu for selling and withdrawing funds"""
    console.print("[bold cyan]💸 SELL & WITHDRAW ALL[/bold cyan]")

    if not wallet_manager.fund_wallets:
        console.print("[red]❌ No fund wallets configured[/red]")
        return

    console.print()
    await view_balances()

    token_mint = await _select_token_from_registry("sell & withdraw")
    if not token_mint:
        return

    console.print("[bold]Sell Options:[/bold]")
    console.print("1. Sell all tokens")
    console.print("2. Sell specific percentage")
    console.print("3. Sell specific amount")

    sell_option = await asyncio.to_thread(click.prompt, "Select option", type=int, default=1)
    amount_tokens, percentage = None, None

    if sell_option == 2:
        percentage = await asyncio.to_thread(click.prompt, "Percentage to sell (1-100)", type=int, default=100)
    elif sell_option == 3:
        amount_tokens = await asyncio.to_thread(click.prompt, "Amount of tokens to sell", type=float)

    withdraw_sol = await asyncio.to_thread(click.confirm, "Withdraw remaining SOL to dev wallet after selling?", default=True)

    sell_desc = "all tokens"
    if percentage: sell_desc = f"{percentage}% of tokens"
    elif amount_tokens: sell_desc = f"{amount_tokens} tokens"

    console.print("[yellow]Summary:[/yellow]")
    console.print(f"  Token: {token_mint[:16]}...")
    console.print(f"  Wallets: {len(wallet_manager.fund_wallets)}")
    console.print(f"  Sell: {sell_desc}")
    console.print(f"  Withdraw SOL: {'Yes' if withdraw_sol else 'No'}")

    if config.require_confirmation:
        if not await asyncio.to_thread(click.confirm, "Execute sell & withdraw?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    console.print("[cyan]Selling tokens from all wallets...[/cyan]")
    seller = get_token_seller(wallet_manager.rpc_client)
    results = await seller.bundle_sell(wallet_manager.fund_wallets, token_mint, amount_tokens, percentage)

    console.print("[bold]Sell Results:[/bold]")
    for result in results:
        if result.success:
            console.print(f"  [green]✓[/green] {result.wallet.label}: {result.signature[:16]}...")
        else:
            console.print(f"  [red]✗[/red] {result.wallet.label}: {result.error}")

    if withdraw_sol and wallet_manager.dev_wallet:
        console.print("[cyan]Withdrawing SOL to dev wallet...[/cyan]")
        withdraw_result = await seller.withdraw_all_sol(wallet_manager.fund_wallets, wallet_manager.dev_wallet)
        if withdraw_result.get('success'):
            total = withdraw_result.get('total_withdrawn', 0)
            label = "[dim](dry run)[/dim]" if withdraw_result.get('dry_run') else ""
            console.print(f"[green]✓ Withdrew {total:.4f} SOL {label}[/green]")
            # Per-wallet breakdown
            for r in withdraw_result.get('results', []):
                if r.get('success'):
                    console.print(f"  [green]✓[/green] {r['wallet']}: {r['amount_sol']:.6f} SOL — {r['signature'][:16]}...")
                else:
                    console.print(f"  [red]✗[/red] {r['wallet']}: {r.get('error', 'Unknown error')}")
        else:
            console.print(f"[red]✗ Withdrawal failed[/red]")
            for r in withdraw_result.get('results', []):
                if not r.get('success'):
                    console.print(f"  [red]✗[/red] {r['wallet']}: {r.get('error', 'Unknown error')}")
    elif withdraw_sol and not wallet_manager.dev_wallet:
        console.print("[yellow]⚠ No dev wallet configured — skipping SOL withdrawal[/yellow]")

    await asyncio.to_thread(click.pause, "Press any key to continue")


async def preload_token_menu():
    """Menu for pre-loading token information and launching later"""
    console.print("\n[bold cyan]💾 PRE-LOAD TOKEN & LAUNCH LATER[/bold cyan]")
    console.print("1. Pre-load new token information")
    console.print("2. Launch pre-loaded token")
    console.print("3. View pre-loaded tokens")
    console.print("4. Delete pre-loaded token")
    console.print("5. Back to main menu")

    choice = await asyncio.to_thread(
        click.prompt,
        "Select an option",
        type=int,
        default=5
    )

    if choice == 1:
        await _preload_token_info()
    elif choice == 2:
        await _launch_preloaded_token()
    elif choice == 3:
        await _view_preloaded_tokens()
    elif choice == 4:
        await _delete_preloaded_token()


async def _preload_token_info():
    """Pre-load token information for later launch"""
    console.print("\n[bold cyan]Pre-load Token Information[/bold cyan]")
    console.print("[dim]Enter token details (token will be created when you launch it):[/dim]\n")

    # Get token metadata
    name = await asyncio.to_thread(click.prompt, "Token Name", type=str)
    symbol = await asyncio.to_thread(click.prompt, "Token Symbol", type=str)
    description = await asyncio.to_thread(click.prompt, "Description", type=str, default="")

    # Optional fields
    has_image = await asyncio.to_thread(click.confirm, "Do you have an image file?", default=False)
    image_path = None
    if has_image:
        image_path = await asyncio.to_thread(click.prompt, "Image file path", type=str)

    has_socials = await asyncio.to_thread(click.confirm, "Add social links?", default=False)
    twitter, telegram, website = None, None, None

    if has_socials:
        twitter = await asyncio.to_thread(click.prompt, "Twitter/X URL (optional)", type=str, default="") or None
        telegram = await asyncio.to_thread(click.prompt, "Telegram URL (optional)", type=str, default="") or None
        website = await asyncio.to_thread(click.prompt, "Website URL (optional)", type=str, default="") or None

    # Initial buy amount
    initial_buy = await asyncio.to_thread(click.prompt, "Initial buy amount in SOL (0 for none)", type=float, default=0.0)

    # Create preload entry
    import json
    from pathlib import Path
    from datetime import datetime
    
    preload_file = Path("data/preloaded_tokens.json")
    preload_file.parent.mkdir(exist_ok=True)
    
    preloaded_tokens = []
    if preload_file.exists():
        preloaded_tokens = json.loads(preload_file.read_text())
    
    token_entry = {
        'name': name,
        'symbol': symbol,
        'description': description,
        'image_path': image_path,
        'twitter': twitter,
        'telegram': telegram,
        'website': website,
        'initial_buy': initial_buy,
        'created_at': datetime.now().isoformat(),
        'status': 'preloaded'
    }
    
    preloaded_tokens.append(token_entry)
    preload_file.write_text(json.dumps(preloaded_tokens, indent=2))
    
    console.print("\n[green]✓ Token information pre-loaded successfully![/green]")
    console.print(f"[dim]Saved to: {preload_file}[/dim]")
    console.print("\n[yellow]Token Summary:[/yellow]")
    console.print(f"  Name: {name}")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Description: {description or 'None'}")
    console.print(f"  Image: {image_path or 'None'}")
    console.print(f"  Initial Buy: {initial_buy} SOL")
    console.print("\n[cyan]You can launch this token later using option 2.[/cyan]")
    
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def _launch_preloaded_token():
    """Launch a pre-loaded token"""
    import json
    from pathlib import Path
    from datetime import datetime
    
    preload_file = Path("data/preloaded_tokens.json")
    
    if not preload_file.exists():
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    preloaded_tokens = json.loads(preload_file.read_text())
    
    if not preloaded_tokens:
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    # Display list of pre-loaded tokens
    console.print("\n[bold cyan]Pre-loaded Tokens:[/bold cyan]\n")
    for i, token in enumerate(preloaded_tokens, 1):
        status_icon = "✓" if token.get('status') == 'launched' else "⏳"
        console.print(f"{i}. {status_icon} {token['name']} ({token['symbol']})")
        console.print(f"   Description: {token.get('description', 'None')[:50]}...")
        console.print(f"   Initial Buy: {token.get('initial_buy', 0)} SOL")
        if token.get('status') == 'launched':
            console.print(f"   [dim]Status: Launched (Mint: {token.get('mint', 'N/A')[:16]}...)[/dim]")
        console.print()
    
    token_index = await asyncio.to_thread(
        click.prompt,
        f"Select token to launch (1-{len(preloaded_tokens)})",
        type=int
    )
    
    if token_index < 1 or token_index > len(preloaded_tokens):
        console.print("[red]Invalid selection.[/red]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    selected_token = preloaded_tokens[token_index - 1]
    
    if selected_token.get('status') == 'launched':
        console.print("[yellow]⚠ This token has already been launched.[/yellow]")
        if not await asyncio.to_thread(click.confirm, "Do you want to launch it again?", default=False):
            await asyncio.to_thread(click.pause, "Press any key to continue")
            return
    
    # Show summary
    console.print("\n[yellow]Token Summary:[/yellow]")
    console.print(f"  Name: {selected_token['name']}")
    console.print(f"  Symbol: {selected_token['symbol']}")
    console.print(f"  Description: {selected_token.get('description', 'None')}")
    console.print(f"  Image: {selected_token.get('image_path', 'None')}")
    console.print(f"  Initial Buy: {selected_token.get('initial_buy', 0)} SOL")
    
    if not wallet_manager.dev_wallet:
        console.print("[red]❌ Dev wallet not configured[/red]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    if config.require_confirmation:
        if not await asyncio.to_thread(click.confirm, "Proceed with token creation?", default=True):
            console.print("[yellow]Cancelled.[/yellow]")
            await asyncio.to_thread(click.pause, "Press any key to continue")
            return
    
    # Create metadata object
    metadata = TokenMetadata(
        name=selected_token['name'],
        symbol=selected_token['symbol'],
        description=selected_token.get('description', ''),
        image_path=selected_token.get('image_path'),
        twitter=selected_token.get('twitter'),
        telegram=selected_token.get('telegram'),
        website=selected_token.get('website')
    )
    
    # Create token
    console.print("\n[cyan]Creating token...[/cyan]")
    creator = get_token_creator(wallet_manager.rpc_client)
    result = await creator.create_token(
        wallet_manager.dev_wallet,
        metadata,
        selected_token.get('initial_buy', 0)
    )
    
    if result and result.get('success'):
        console.print("[green]✓ Token created successfully![/green]")
        mint = result['mint']
        sig = result['signature']
        
        console.print(f"  Mint Address:  {mint}")
        console.print(f"  Signature:     {sig}")
        console.print(f"  Metadata URI:  {result['metadataUri']}")
        console.print()
        console.print(Panel(
            f"[bold green]🌐 pump.fun[/bold green]  [link=https://pump.fun/coin/{mint}]https://pump.fun/coin/{mint}[/link]\n"
            f"[bold cyan]🔍 Solscan[/bold cyan]   [link=https://solscan.io/tx/{sig}]https://solscan.io/tx/{sig}[/link]",
            title="[bold]Token Links[/bold]",
            border_style="green",
            expand=False
        ))
        
        # Update preloaded token status
        selected_token['status'] = 'launched'
        selected_token['mint'] = mint
        selected_token['signature'] = sig
        selected_token['metadataUri'] = result['metadataUri']
        selected_token['launched_at'] = datetime.now().isoformat()
        
        preload_file.write_text(json.dumps(preloaded_tokens, indent=2))
        
        # Save to created tokens as well
        token_file = Path("data/created_tokens.json")
        token_file.parent.mkdir(exist_ok=True)
        created_tokens = []
        if token_file.exists():
            created_tokens = json.loads(token_file.read_text())
        created_tokens.append({
            'name': selected_token['name'],
            'symbol': selected_token['symbol'],
            'mint': mint,
            'signature': sig,
            'metadataUri': result['metadataUri'],
            'creator': result['creator'],
            'initialBuy': result.get('initialBuy', 0)
        })
        token_file.write_text(json.dumps(created_tokens, indent=2))
        
        console.print(f"[dim]Token info saved to {token_file}[/dim]")
        
        # Auto bundle buy after creation
        if wallet_manager.fund_wallets:
            console.print()
            console.print(Panel(
                f"[bold]Token is live![/bold] Ready to bundle buy with {len(wallet_manager.fund_wallets)} fund wallet(s).\n"
                f"[dim]Mint: {mint}[/dim]",
                title="🚀 Bundle Buy Opportunity",
                border_style="cyan"
            ))
            
            do_bundle = await asyncio.to_thread(
                click.confirm,
                "Execute bundle buy now with fund wallets?",
                default=True
            )
            
            if do_bundle:
                await _execute_bundle_buy_for_mint(mint)
        else:
            console.print("[yellow]⚠ No fund wallets configured — skipping bundle buy.[/yellow]")
    else:
        console.print("[red]✗ Token creation failed[/red]")
    
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def _view_preloaded_tokens():
    """View all pre-loaded tokens"""
    import json
    from pathlib import Path
    
    preload_file = Path("data/preloaded_tokens.json")
    
    if not preload_file.exists():
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    preloaded_tokens = json.loads(preload_file.read_text())
    
    if not preloaded_tokens:
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    from rich.table import Table
    
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("Name", style="white", width=20)
    table.add_column("Symbol", style="yellow", width=10)
    table.add_column("Status", style="green", width=12)
    table.add_column("Initial Buy", justify="right", style="magenta", width=12)
    
    for i, token in enumerate(preloaded_tokens, 1):
        status = "✓ Launched" if token.get('status') == 'launched' else "⏳ Pre-loaded"
        table.add_row(
            str(i),
            token['name'],
            token['symbol'],
            status,
            f"{token.get('initial_buy', 0)} SOL"
        )
    
    console.print()
    console.print(table)
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def _delete_preloaded_token():
    """Delete a pre-loaded token"""
    import json
    from pathlib import Path
    
    preload_file = Path("data/preloaded_tokens.json")
    
    if not preload_file.exists():
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    preloaded_tokens = json.loads(preload_file.read_text())
    
    if not preloaded_tokens:
        console.print("[yellow]No pre-loaded tokens found.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    # Display list
    console.print("\n[bold cyan]Pre-loaded Tokens:[/bold cyan]\n")
    for i, token in enumerate(preloaded_tokens, 1):
        status_icon = "✓" if token.get('status') == 'launched' else "⏳"
        console.print(f"{i}. {status_icon} {token['name']} ({token['symbol']})")
    
    token_index = await asyncio.to_thread(
        click.prompt,
        f"Select token to delete (1-{len(preloaded_tokens)})",
        type=int
    )
    
    if token_index < 1 or token_index > len(preloaded_tokens):
        console.print("[red]Invalid selection.[/red]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    selected_token = preloaded_tokens[token_index - 1]
    
    if not await asyncio.to_thread(
        click.confirm,
        f"Delete {selected_token['name']} ({selected_token['symbol']})?",
        default=False
    ):
        console.print("[yellow]Cancelled.[/yellow]")
        await asyncio.to_thread(click.pause, "Press any key to continue")
        return
    
    preloaded_tokens.pop(token_index - 1)
    preload_file.write_text(json.dumps(preloaded_tokens, indent=2))
    
    console.print("[green]✓ Token deleted successfully![/green]")
    await asyncio.to_thread(click.pause, "Press any key to continue")


async def manage_wallets_menu():
    """Menu for managing wallets"""
    console.print("\n[bold cyan]⚙️  MANAGE WALLETS[/bold cyan]")
    console.print("1. Add new fund wallet")
    console.print("2. Remove fund wallet")
    console.print("3. Export wallet keys")
    console.print("4. Back to main menu")

    choice = await asyncio.to_thread(
        click.prompt,
        "Select an option",
        type=int,
        default=4
    )

    if choice == 1:
        # Add new wallet
        has_key = await asyncio.to_thread(
            click.confirm,
            "Do you have an existing private key to import?",
            default=False
        )

        if has_key:
            private_key = await asyncio.to_thread(
                click.prompt,
                "Enter private key (base58)",
                type=str,
                hide_input=True
            )
            wallet_manager.add_fund_wallet(private_key)
        else:
            wallet = wallet_manager.add_fund_wallet()
            console.print("\n[bold red]⚠️  IMPORTANT: Save this private key securely![/bold red]")
            console.print(f"[yellow]{wallet.get_private_key_base58()}[/yellow]\n")
            await asyncio.to_thread(click.pause, "Press any key after saving")

    elif choice == 2:
        # Remove wallet
        wallet_manager.display_balances()
        index = await asyncio.to_thread(
            click.prompt,
            "Enter wallet index to remove (0-based)",
            type=int
        )
        wallet_manager.remove_fund_wallet(index)

    elif choice == 3:
        # Export keys
        console.print("[yellow]Exporting wallet keys...[/yellow]")
        console.print("[yellow]This feature will be implemented soon[/yellow]")


async def settings_menu():
    """Menu for changing settings"""
    console.print("\n[bold cyan]🔧 SETTINGS[/bold cyan]")
    console.print(f"1. Toggle Dry Run Mode (Currently: {'ON' if config.dry_run_mode else 'OFF'})")
    console.print(f"2. Toggle Confirmations (Currently: {'ON' if config.require_confirmation else 'OFF'})")
    console.print(f"3. Toggle Desktop Notifications (Currently: {'ON' if config.enable_desktop_notifications else 'OFF'})")
    console.print(f"4. Toggle Sound Alerts (Currently: {'ON' if config.enable_sound_alerts else 'OFF'})")
    console.print("5. Back to main menu")

    choice = await asyncio.to_thread(
        click.prompt,
        "Select an option",
        type=int,
        default=5
    )

    def _toggle(attr: str, env_key: str, label: str):
        """Flip a boolean config value and persist it."""
        new_val = not getattr(config, attr)
        setattr(config, attr, new_val)
        saved = config.set(env_key, new_val)
        status = "ON" if new_val else "OFF"
        suffix = "" if saved else " [yellow](not saved — no .env file found)[/yellow]"
        console.print(f"[green]{label}: {status}[/green]{suffix}")

    if choice == 1:
        _toggle("dry_run_mode", "DRY_RUN_MODE", "Dry run mode")
    elif choice == 2:
        _toggle("require_confirmation", "REQUIRE_CONFIRMATION", "Confirmations")
    elif choice == 3:
        _toggle("enable_desktop_notifications", "ENABLE_DESKTOP_NOTIFICATIONS", "Desktop notifications")
        notification_manager._init_desktop_notifications()
    elif choice == 4:
        _toggle("enable_sound_alerts", "ENABLE_SOUND_ALERTS", "Sound alerts")
        notification_manager._init_sound_system()


@cli.command()
def config_check():
    """Validate configuration without starting the bot"""
    print_banner()

    is_valid, errors = config.validate()

    if is_valid:
        console.print("[green]✓ Configuration is valid![/green]")
        console.print(config.display_summary())
    else:
        console.print("[red]❌ Configuration errors found:[/red]")
        for error in errors:
            console.print(f"  • {error}")


@cli.command()
@click.option('--count', '-c', default=1, help='Number of wallets to generate')
def generate_wallets(count):
    """Generate new Solana wallets"""
    console.print(f"\n[cyan]Generating {count} new wallet(s)...[/cyan]\n")

    for i in range(count):
        wallet = Wallet.generate_new(f"Generated Wallet {i+1}")

        console.print(f"[bold]Wallet {i+1}:[/bold]")
        console.print(f"  Address: {wallet.public_key}")
        console.print(f"  Private Key: {wallet.get_private_key_base58()}\n")

    console.print("[bold red]⚠️  Save these private keys securely![/bold red]")


if __name__ == "__main__":
    cli()
