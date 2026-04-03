"""
Configuration Manager
Handles loading and validating all bot settings from .env file
"""

import os
from typing import List, Optional
from dotenv import load_dotenv
from pathlib import Path


class Config:
    """Central configuration manager for the pump.fun bot"""

    def __init__(self, env_path: Optional[str] = None):
        """Initialize configuration from .env file"""
        self._env_file: Optional[Path] = None

        if env_path:
            self._env_file = Path(env_path)
            load_dotenv(env_path)
        else:
            # Try multiple locations for .env: cwd first, then project root relative to this file
            candidates = [
                Path.cwd() / ".env",
                Path(__file__).parent.parent / ".env",
                Path(__file__).parent / ".env",
            ]
            self._env_file = next((p for p in candidates if p.exists()), None)
            if self._env_file:
                load_dotenv(self._env_file)
                print(f"✓  Loaded .env from {self._env_file}")
            else:
                print(f"⚠️  No .env file found (searched: {', '.join(str(p) for p in candidates)})")
                print(f"⚠️  Please copy .env.example to .env and configure it")

        self._load_config()

    def set(self, key: str, value) -> bool:
        """
        Update a single setting in memory and persist it to the .env file.

        The .env file is rewritten with the key updated in-place if it already
        exists, or appended if it doesn't.  Other lines (comments, blank lines,
        unrelated keys) are preserved exactly as-is.

        Args:
            key:   The env-var name, e.g. "DRY_RUN_MODE"
            value: The new value — booleans become "true"/"false", everything
                   else is converted with str()

        Returns:
            True if the .env file was updated, False if no file was found
            (the in-memory change is applied either way).
        """
        # Normalise value to a string suitable for .env
        if isinstance(value, bool):
            str_value = "true" if value else "false"
        else:
            str_value = str(value)

        # Update the live environment so os.getenv() stays consistent
        import os
        os.environ[key] = str_value

        if not self._env_file or not self._env_file.exists():
            return False

        lines = self._env_file.read_text().splitlines(keepends=True)
        new_line = f"{key}={str_value}\n"
        found = False

        for i, line in enumerate(lines):
            # Match "KEY=..." lines, ignoring commented-out lines
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[i] = new_line
                found = True
                break

        if not found:
            # Append with a blank line separator for readability
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(new_line)

        self._env_file.write_text("".join(lines))
        return True

    def _load_config(self):
        """Load all configuration values"""
        # Solana Network
        self.rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.network = os.getenv("SOLANA_NETWORK", "mainnet-beta")

        # Wallets
        self.dev_wallet_key = os.getenv("DEV_WALLET_PRIVATE_KEY", "")
        fund_keys_str = os.getenv("FUND_WALLET_PRIVATE_KEYS", "")# + os.getenv("FUND_WALLET_PRIVATE_KEYS2", "")
        self.fund_wallet_keys = [k.strip() for k in fund_keys_str.split(",") if k.strip()]

        # Trading
        self.default_slippage_bps = int(os.getenv("DEFAULT_SLIPPAGE_BPS", "500"))
        self.max_buy_amount_sol = float(os.getenv("MAX_BUY_AMOUNT_SOL", "1.0"))
        self.min_buy_amount_sol = float(os.getenv("MIN_BUY_AMOUNT_SOL", "0.01"))

        # Automation
        self.auto_sell_enabled = os.getenv("AUTO_SELL_ENABLED", "false").lower() == "true"
        self.auto_sell_profit_multiplier = float(os.getenv("AUTO_SELL_PROFIT_MULTIPLIER", "2.0"))
        self.auto_sell_mcap_threshold = float(os.getenv("AUTO_SELL_MCAP_THRESHOLD", "100000"))
        self.auto_withdraw_enabled = os.getenv("AUTO_WITHDRAW_ENABLED", "false").lower() == "true"

        # Monitoring
        self.price_alert_threshold_percent = float(os.getenv("PRICE_ALERT_THRESHOLD_PERCENT", "10"))
        self.volume_alert_threshold = float(os.getenv("VOLUME_ALERT_THRESHOLD", "1000"))
        self.enable_sound_alerts = os.getenv("ENABLE_SOUND_ALERTS", "true").lower() == "true"
        self.enable_desktop_notifications = os.getenv("ENABLE_DESKTOP_NOTIFICATIONS", "true").lower() == "true"

        # Safety
        self.dry_run_mode = os.getenv("DRY_RUN_MODE", "true").lower() == "true"
        self.require_confirmation = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"

        # Pump.fun Program IDs
        self.pumpfun_program_id = os.getenv("PUMPFUN_PROGRAM_ID", "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
        self.pumpfun_global = os.getenv("PUMPFUN_GLOBAL_ACCOUNT", "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf")
        self.pumpfun_fee_recipient = os.getenv("PUMPFUN_FEE_RECIPIENT", "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM")
        self.pumpfun_event_authority = os.getenv("PUMPFUN_EVENT_AUTHORITY", "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1")
        self.pumpfun_mint_authority = os.getenv("PUMPFUN_MINT_AUTHORITY", "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM")

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"

    def validate(self) -> tuple[bool, List[str]]:
        """Validate configuration and return (is_valid, errors)"""
        errors = []

        if not self.dev_wallet_key:
            errors.append("DEV_WALLET_PRIVATE_KEY is not set")

        if not self.fund_wallet_keys:
            errors.append("No FUND_WALLET_PRIVATE_KEYS configured (comma-separated keys in .env)")

        if self.max_buy_amount_sol < self.min_buy_amount_sol:
            errors.append("MAX_BUY_AMOUNT_SOL must be >= MIN_BUY_AMOUNT_SOL")

        if self.default_slippage_bps < 0 or self.default_slippage_bps > 10000:
            errors.append("DEFAULT_SLIPPAGE_BPS must be between 0 and 10000")

        return len(errors) == 0, errors

    def display_summary(self) -> str:
        """Return a formatted summary of current configuration"""
        mode = "🔴 DRY RUN" if self.dry_run_mode else "🟢 LIVE"

        summary = f"""
╔══════════════════════════════════════════════════════════════╗
║                  PUMP.FUN BOT CONFIGURATION                  ║
╠══════════════════════════════════════════════════════════════╣
║ Mode: {mode:52} ║
║ Network: {self.network:49} ║
║ RPC: {self.rpc_url[:54]:54} ║
╠══════════════════════════════════════════════════════════════╣
║ WALLETS                                                      ║
║ Dev Wallet: {'Configured' if self.dev_wallet_key else 'NOT SET':48} ║
║ Fund Wallets: {len(self.fund_wallet_keys):2} configured                              ║
╠══════════════════════════════════════════════════════════════╣
║ TRADING                                                      ║
║ Max Buy: {self.max_buy_amount_sol} SOL                                       ║
║ Min Buy: {self.min_buy_amount_sol} SOL                                       ║
║ Slippage: {self.default_slippage_bps / 100}%                                          ║
╠══════════════════════════════════════════════════════════════╣
║ AUTOMATION                                                   ║
║ Auto-Sell: {'Enabled' if self.auto_sell_enabled else 'Disabled':47} ║
║ Auto-Withdraw: {'Enabled' if self.auto_withdraw_enabled else 'Disabled':43} ║
║ Profit Target: {self.auto_sell_profit_multiplier}x                                    ║
╠══════════════════════════════════════════════════════════════╣
║ ALERTS                                                       ║
║ Desktop Notifications: {'Enabled' if self.enable_desktop_notifications else 'Disabled':35} ║
║ Sound Alerts: {'Enabled' if self.enable_sound_alerts else 'Disabled':44} ║
╚══════════════════════════════════════════════════════════════╝
        """
        return summary


# Global config instance
config = Config()
