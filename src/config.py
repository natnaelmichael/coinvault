"""
Configuration Manager
Handles loading and validating all bot settings from environment variables.
On Replit, secrets are injected automatically. A local .env file is also
supported for development convenience.
"""

import os
from typing import List, Optional
from dotenv import load_dotenv
from pathlib import Path


class Config:
    """Central configuration manager for the pump.fun bot"""

    def __init__(self, env_path: Optional[str] = None):
        """Initialize configuration from environment variables (and optional .env file)"""
        self._env_file: Optional[Path] = None

        if env_path:
            self._env_file = Path(env_path)
            load_dotenv(env_path)
        else:
            # Try loading a local .env file if present (Replit secrets take precedence)
            candidates = [
                Path.cwd() / ".env",
                Path(__file__).parent.parent / ".env",
                Path(__file__).parent / ".env",
            ]
            self._env_file = next((p for p in candidates if p.exists()), None)
            if self._env_file:
                load_dotenv(self._env_file, override=False)

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

    @staticmethod
    def _int_env(key: str, default: int) -> int:
        """Read an integer env var, falling back to `default` on bad values."""
        raw = os.getenv(key, "")
        if raw.strip():
            try:
                return int(raw.strip())
            except ValueError:
                import logging
                logging.getLogger("PumpFunBot").warning(
                    f"Config: {key}={raw!r} is not a valid integer — using default {default}"
                )
        return default

    @staticmethod
    def _float_env(key: str, default: float) -> float:
        """Read a float env var, falling back to `default` on bad values."""
        raw = os.getenv(key, "")
        if raw.strip():
            try:
                return float(raw.strip())
            except ValueError:
                import logging
                logging.getLogger("PumpFunBot").warning(
                    f"Config: {key}={raw!r} is not a valid number — using default {default}"
                )
        return default

    def _load_config(self):
        """Load all configuration values"""
        # Solana Network
        self.rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.network = os.getenv("SOLANA_NETWORK", "mainnet-beta")

        #Pinata for Solana:
        self.pinata_jwt = os.getenv("PINATA_JWT","")

        # Wallets
        self.dev_wallet_key = os.getenv("DEV_WALLET_PRIVATE_KEY", "")
        # Keys may be split across up to three env vars to work around per-secret
        # character limits.  All three are merged before parsing.
        _raw_keys = ",".join(filter(None, [
            os.getenv("FUND_WALLET_PRIVATE_KEYS",  ""),
            os.getenv("FUND_WALLET_PRIVATE_KEYS2", ""),
            os.getenv("FUND_WALLET_PRIVATE_KEYS3", ""),
        ]))
        self.fund_wallet_keys = [k.strip() for k in _raw_keys.split(",") if k.strip()]

        # Trading
        self.default_slippage_bps = self._int_env("DEFAULT_SLIPPAGE_BPS", 500)
        self.max_buy_amount_sol   = self._float_env("MAX_BUY_AMOUNT_SOL",  1.0)
        self.min_buy_amount_sol   = self._float_env("MIN_BUY_AMOUNT_SOL",  0.01)

        # Automation
        self.auto_sell_enabled = os.getenv("AUTO_SELL_ENABLED", "false").lower() == "true"
        self.auto_sell_profit_multiplier = self._float_env("AUTO_SELL_PROFIT_MULTIPLIER", 2.0)
        self.auto_sell_mcap_threshold    = self._float_env("AUTO_SELL_MCAP_THRESHOLD",    100000.0)
        self.auto_withdraw_enabled = os.getenv("AUTO_WITHDRAW_ENABLED", "false").lower() == "true"

        # ── Trailing stop ─────────────────────────────────────────────────────
        # Arms when price >= open × trailing_arm_multiplier (1.0 = any profit).
        # Sells when price drops trailing_stop_pct below its session peak (10%).
        # Sell-pressure tightening: if ≥ trailing_sell_ratio of the last
        #   trailing_sell_window trades are sells, trail narrows to
        #   trailing_sell_pct (3%).  Once tightened it stays tight.
        # Wick detection: immediate sell if price drops trailing_wick_pct
        #   within the last trailing_wick_window trades (5% / 5 trades).
        #   Active from the first trade — does not require arming.
        self.trailing_stop_enabled   = os.getenv("TRAILING_STOP_ENABLED", "false").lower() == "true"
        self.trailing_arm_multiplier = self._float_env("TRAILING_ARM_MULTIPLIER", 1.0)
        self.trailing_stop_pct       = self._float_env("TRAILING_STOP_PCT",       0.10)
        self.trailing_sell_pct       = self._float_env("TRAILING_SELL_PCT",       0.03)
        self.trailing_sell_window    = self._int_env("TRAILING_SELL_WINDOW",      10)
        self.trailing_sell_ratio     = self._float_env("TRAILING_SELL_RATIO",     0.70)
        self.trailing_wick_pct       = self._float_env("TRAILING_WICK_PCT",       0.05)
        self.trailing_wick_window    = self._int_env("TRAILING_WICK_WINDOW",      5)
        # Time-based exit: sell outright if no new high-water is set for this
        # many seconds after arming (default 900 = 15 min).
        self.trailing_max_flat_secs  = self._int_env("TRAILING_MAX_FLAT_SECS",    900)
        # MCap ceiling: sell outright if MCap drops >= this fraction from its
        # session peak, regardless of trail state (default 0.50 = 50% drop).
        self.trailing_mcap_drop_pct  = self._float_env("TRAILING_MCAP_DROP_PCT",  0.50)

        # Monitoring
        self.price_alert_threshold_percent = self._float_env("PRICE_ALERT_THRESHOLD_PERCENT", 10.0)
        self.volume_alert_threshold        = self._float_env("VOLUME_ALERT_THRESHOLD",         1000.0)
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

        # IPFS upload mode
        # "pumpfun" (default) — uses pump.fun's internal /api/ipfs endpoint
        # "local"             — uses a locally-running IPFS daemon (ipfs daemon)
        #                       with 2-stage pin+DHT and public gateway verification
        self.ipfs_mode = os.getenv("IPFS_MODE", "pumpfun").lower()
        self.ipfs_local_api = os.getenv("IPFS_LOCAL_API", "http://127.0.0.1:5001")

        # Stage 2 gateway verification settings — used by both IPFS backends
        # (local daemon mode polls ipfs.io; Pinata mode polls gateway.pinata.cloud)
        # Set IPFS_GATEWAY_VERIFY=false to skip the gateway check (not recommended)
        self.ipfs_gateway_verify = os.getenv("IPFS_GATEWAY_VERIFY", "true").lower() == "true"
        # How many seconds to wait for the content to appear on the public gateway
        self.ipfs_gateway_timeout       = self._int_env("IPFS_GATEWAY_TIMEOUT",       90)
        self.ipfs_gateway_poll_interval = self._float_env("IPFS_GATEWAY_POLL_INTERVAL", 0.5)

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"

        # UX — automatically open pump.fun in the browser after token creation
        self.auto_open_browser = os.getenv("AUTO_OPEN_BROWSER", "true").lower() == "true"

        # ── Jito MEV bundles ──────────────────────────────────────────────────
        # When enabled, sells and token creation use atomic Jito bundles instead
        # of individual RPC sends — all transactions land in the same block or
        # none do.  Requires a tip payment per bundle.
        self.jito_enabled  = os.getenv("JITO_ENABLED",  "false").lower() == "true"
        self.jito_tip_sol  = self._float_env("JITO_TIP_SOL",  0.001)
        # Regional block engine — one of: mainnet, amsterdam, ny, tokyo, frankfurt, auto
        self.jito_endpoint = os.getenv("JITO_ENDPOINT", "mainnet")

        # ── 4A: Tip auto-scaling with retry ──────────────────────────────────
        # On bundle timeout, retry up to jito_max_retries times, multiplying the
        # tip by jito_tip_multiplier each attempt, capped at jito_max_tip_sol.
        self.jito_max_retries     = self._int_env("JITO_MAX_RETRIES",     3)
        self.jito_tip_multiplier  = self._float_env("JITO_TIP_MULTIPLIER", 2.0)
        self.jito_max_tip_sol     = self._float_env("JITO_MAX_TIP_SOL",    0.05)

        # Two-wave sell: total wallet slots in wave 1 (dev wallet counts as 1).
        # Default 4 = dev + 3 fund wallets.  Remaining fund wallets fire in wave 2.
        self.sell_wave_size = self._int_env("SELL_WAVE_SIZE", 4)

    def validate(self) -> tuple[bool, List[str]]:
        """Validate configuration and return (is_valid, errors)"""
        errors = []

        if not self.dev_wallet_key:
            errors.append("DEV_WALLET_PRIVATE_KEY is not set")

        if not self.fund_wallet_keys:
            errors.append("No FUND_WALLET_PRIVATE_KEYS configured (comma-separated keys in .env)")

        # PINATA_JWT is only required for token creation (uploading metadata to IPFS).
        # It is intentionally NOT a hard startup error so that the TUI can start,
        # show balances, and sell existing positions even without Pinata configured.

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
║ IPFS                                                         ║
║ Mode: {('local (daemon @ ' + self.ipfs_local_api + ')') if self.ipfs_mode == 'local' else 'pumpfun (pump.fun /api/ipfs)':52} ║
║ Gateway Verify: {'Enabled (timeout ' + str(self.ipfs_gateway_timeout) + 's)' if self.ipfs_gateway_verify else 'Disabled':42} ║
╠══════════════════════════════════════════════════════════════╣
║ ALERTS                                                       ║
║ Desktop Notifications: {'Enabled' if self.enable_desktop_notifications else 'Disabled':35} ║
║ Sound Alerts: {'Enabled' if self.enable_sound_alerts else 'Disabled':44} ║
╚══════════════════════════════════════════════════════════════╝
        """
        return summary


# Global config instance
config = Config()
