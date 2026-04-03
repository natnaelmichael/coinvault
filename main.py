#!/usr/bin/env python3
"""
Pump.fun Bot - Main Entry Point

Usage:
  python main.py start      — classic CLI (numeric menus)
  python main.py tui        — Textual TUI (arrow keys + mouse)
  python main.py config-check
  python main.py generate-wallets
"""

import click
from src.cli import cli


@cli.command()
def tui():
    """Start the bot in interactive Textual TUI mode (arrow keys + mouse)."""
    from src.tui import run_tui
    run_tui()


if __name__ == "__main__":
    cli()
