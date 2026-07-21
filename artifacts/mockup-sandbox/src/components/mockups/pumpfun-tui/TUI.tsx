import { useState } from "react";

const NAV_ITEMS = [
  { key: "balances",  label: "💰  Balances" },
  { key: "distribute",label: "📤  Distribute SOL" },
  { key: "create",   label: "🪙  Create Token" },
  { key: "bundle",   label: "🔄  Bundle Buy" },
  { key: "monitor",  label: "📊  Monitor Token" },
  { key: "sell",     label: "💸  Sell & Withdraw" },
  { key: "preload",  label: "💾  Pre-load Token" },
  { key: "wallets",  label: "⚙️   Manage Wallets" },
  { key: "settings", label: "🔧  Settings" },
];

const WALLET_DATA = [
  { label: "DEV WALLET",  addr: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", bal: "2.4821", dev: true },
  { label: "Fund #1",     addr: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", bal: "0.1500", dev: false },
  { label: "Fund #2",     addr: "B62qm4G7t5JXWP8HbzUF9eQmVNm4Ky7ZzTzJXHNBCkwk", bal: "0.1500", dev: false },
  { label: "Fund #3",     addr: "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG3TZLVH", bal: "0.1500", dev: false },
  { label: "Fund #4",     addr: "Fy8d5FNGmke7T9QiVpzHb6Ltr5v8YbXE3nJCZFy6wSNQ", bal: "0.1500", dev: false },
];

function BalancesPane() {
  const total = WALLET_DATA.reduce((s, w) => s + parseFloat(w.bal), 0).toFixed(4);
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px", marginBottom: "4px" }}>
        💰  Wallet Balances
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: "13px" }}>
          <thead>
            <tr style={{ background: "#181825", color: "#6c7086", borderBottom: "1px solid #313244" }}>
              <th style={{ textAlign: "left", padding: "4px 10px", fontWeight: "normal" }}>Label</th>
              <th style={{ textAlign: "left", padding: "4px 10px", fontWeight: "normal" }}>Address</th>
              <th style={{ textAlign: "right", padding: "4px 10px", fontWeight: "normal" }}>Balance (SOL)</th>
            </tr>
          </thead>
          <tbody>
            {WALLET_DATA.map((w, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #1e1e2e", background: i % 2 === 0 ? "#1e1e2e" : "#181825" }}>
                <td style={{ padding: "5px 10px", color: w.dev ? "#cdd6f4" : "#a6adc8", fontWeight: w.dev ? "bold" : "normal" }}>
                  {w.dev ? <span style={{ fontWeight: "bold" }}>{w.label}</span> : w.label}
                </td>
                <td style={{ padding: "5px 10px", color: "#6c7086", fontFamily: "monospace", fontSize: "12px" }}>
                  {w.addr}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: w.dev ? "#a6e3a1" : "#cdd6f4", fontWeight: w.dev ? "bold" : "normal" }}>
                  {w.dev ? <strong style={{ color: "#a6e3a1" }}>{w.bal}</strong> : w.bal}
                </td>
              </tr>
            ))}
            <tr style={{ borderTop: "1px solid #313244", background: "#181825" }}>
              <td style={{ padding: "5px 10px", color: "#f9e2af", fontWeight: "bold" }}>TOTAL</td>
              <td style={{ padding: "5px 10px", color: "#6c7086", fontStyle: "italic", fontSize: "12px" }}>
                {WALLET_DATA.length - 1} fund wallet(s)
              </td>
              <td style={{ padding: "5px 10px", textAlign: "right", color: "#f9e2af", fontWeight: "bold" }}>{total}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{
          background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px",
          fontFamily: "monospace", cursor: "pointer", fontSize: "13px"
        }}>Refresh Balances</button>
      </div>
    </div>
  );
}

function DistributePane() {
  return (
    <div className="flex flex-col h-full p-3 gap-3">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        📤  Distribute SOL to Fund Wallets
      </div>
      <div style={{ color: "#6c7086", fontSize: "13px" }}>
        Dev wallet: 7xKXtg2C…AsU &nbsp;|&nbsp; 4 fund wallets
      </div>
      {[
        ["Amount per wallet (SOL)", "0.15"],
        ["Reserve in dev wallet (SOL)", "0.05"],
      ].map(([label, val]) => (
        <div key={label} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ width: "220px", textAlign: "right", color: "#6c7086", fontSize: "13px", paddingRight: "6px" }}>{label}</span>
          <input readOnly value={val} style={{
            background: "#181825", border: "1px solid #45475a", color: "#cdd6f4",
            padding: "3px 8px", fontFamily: "monospace", width: "120px", fontSize: "13px"
          }} />
        </div>
      ))}
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>
          Distribute SOL
        </button>
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", background: "#181825", padding: "6px", marginTop: "4px", fontFamily: "monospace", fontSize: "12px", color: "#6c7086", overflow: "auto" }}>
        <div style={{ color: "#a6e3a1" }}>✓ Ready — awaiting distribution command…</div>
      </div>
    </div>
  );
}

function CreateTokenPane() {
  const fields = [
    ["Token Name",   "My Awesome Token"],
    ["Ticker",       "MAT"],
    ["Description",  "A pump.fun token"],
    ["Telegram URL", "https://t.me/mytoken"],
    ["Website URL",  ""],
    ["Image Path",   "/path/to/image.png"],
    ["Dev Buy (SOL)","0.5"],
  ];
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        🪙  Create Token
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {fields.map(([label, val]) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
            <span style={{ width: "160px", textAlign: "right", color: "#6c7086", fontSize: "13px", paddingRight: "6px", flexShrink: 0 }}>{label}</span>
            <input readOnly value={val} style={{
              background: "#181825", border: "1px solid #45475a", color: "#cdd6f4",
              padding: "3px 8px", fontFamily: "monospace", width: "240px", fontSize: "13px"
            }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>
          Create &amp; Launch
        </button>
        <button style={{ background: "#181825", color: "#cdd6f4", border: "1px solid #45475a", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function MonitorPane() {
  const sparkData = [0.000012, 0.000014, 0.000013, 0.000018, 0.000021, 0.000019, 0.000024, 0.000022, 0.000027, 0.000025, 0.000030, 0.000028, 0.000033, 0.000031, 0.000036];
  const chars = "▁▂▃▄▅▆▇█";
  const min = Math.min(...sparkData), max = Math.max(...sparkData), rng = max - min;
  const mid = (min + max) / 2;
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        📊  Monitor Token
      </div>
      <div style={{ background: "#181825", border: "1px solid #a6e3a1", color: "#a6e3a1", padding: "6px 10px", fontSize: "13px", marginBottom: "4px" }}>
        🪙 MAT — My Awesome Token — 7xK…AsU
      </div>
      <div style={{ fontFamily: "monospace", fontSize: "12px", display: "flex", gap: "24px", color: "#6c7086", marginBottom: "4px" }}>
        <span>Price: <span style={{ color: "#cdd6f4" }}>0.00003100 SOL</span></span>
        <span>MCap: <span style={{ color: "#f9e2af" }}>$31,000</span></span>
        <span>Vol: <span style={{ color: "#cdd6f4" }}>142 trades</span></span>
      </div>
      <div style={{ border: "1px solid #313244", background: "#181825", padding: "6px 10px", fontFamily: "monospace", fontSize: "13px" }}>
        <div style={{ color: "#6c7086", marginBottom: "4px", fontSize: "11px" }}>Price chart</div>
        <div style={{ display: "flex", gap: "1px" }}>
          {sparkData.map((p, i) => {
            const idx = Math.min(7, Math.floor((p - min) / (rng || 1) * 8));
            const color = p >= mid ? "#a6e3a1" : "#f38ba8";
            return <span key={i} style={{ color, fontSize: "18px" }}>{chars[idx]}</span>;
          })}
        </div>
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", background: "#181825", padding: "6px", fontFamily: "monospace", fontSize: "12px", color: "#6c7086", overflow: "auto" }}>
        <div style={{ color: "#a6e3a1" }}>● trade  +12.5 SOL  0.00002800  10:14:22</div>
        <div style={{ color: "#f38ba8" }}>● sell   -4.0 SOL   0.00003100  10:14:35</div>
        <div style={{ color: "#a6e3a1" }}>● trade  +8.0 SOL   0.00003050  10:14:51</div>
        <div style={{ color: "#a6e3a1" }}>● trade  +22.0 SOL  0.00003100  10:15:02</div>
        <div style={{ color: "#6c7086" }}>  awaiting next trade…</div>
      </div>
    </div>
  );
}

function SettingsPane() {
  const settings = [
    ["Dry Run Mode",              true],
    ["Desktop Notifications",     false],
    ["Sound Alerts",              false],
    ["Skip Confirm Dialogs",      false],
    ["Auto-refresh Balances",     true],
  ];
  return (
    <div className="flex flex-col h-full p-3 gap-3">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        🔧  Settings
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {settings.map(([name, val]) => (
          <div key={String(name)} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "40px", height: "20px", borderRadius: "10px",
              background: val ? "#a6e3a1" : "#45475a",
              position: "relative", cursor: "pointer", transition: "background 0.2s"
            }}>
              <div style={{
                width: "16px", height: "16px", borderRadius: "50%", background: "#1e1e2e",
                position: "absolute", top: "2px", left: val ? "22px" : "2px", transition: "left 0.2s"
              }} />
            </div>
            <span style={{ color: "#cdd6f4", fontFamily: "monospace", fontSize: "13px" }}>{String(name)}</span>
          </div>
        ))}
      </div>
      <div style={{ color: "#6c7086", fontSize: "12px", marginTop: "8px" }}>
        Changes are persisted to your .env file automatically.
      </div>
    </div>
  );
}

function BundleBuyPane() {
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        🔄  Bundle Buy
      </div>
      <div style={{ background: "#181825", border: "1px solid #a6e3a1", color: "#a6e3a1", padding: "6px 10px", fontSize: "13px", marginBottom: "4px" }}>
        No token selected — use Create Token or pick from watchlist
      </div>
      {[["Buy Amount per Wallet (SOL)", "0.1"], ["Slippage (%)", "10"]].map(([l, v]) => (
        <div key={l} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          <span style={{ width: "220px", textAlign: "right", color: "#6c7086", fontSize: "13px", paddingRight: "6px" }}>{l}</span>
          <input readOnly value={v} style={{ background: "#181825", border: "1px solid #45475a", color: "#cdd6f4", padding: "3px 8px", fontFamily: "monospace", width: "100px", fontSize: "13px" }} />
        </div>
      ))}
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Execute Bundle Buy</button>
        <button style={{ background: "#181825", color: "#cdd6f4", border: "1px solid #45475a", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Pick Token</button>
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", background: "#181825", padding: "6px", fontFamily: "monospace", fontSize: "12px", color: "#6c7086", marginTop: "4px" }}>
        <div>Awaiting bundle buy…</div>
      </div>
    </div>
  );
}

function SellPane() {
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        💸  Sell &amp; Withdraw
      </div>
      <div style={{ background: "#181825", border: "1px solid #a6e3a1", color: "#a6e3a1", padding: "6px 10px", fontSize: "13px", marginBottom: "4px" }}>
        No token selected
      </div>
      {[["Sell %", "100"], ["Slippage (%)", "10"]].map(([l, v]) => (
        <div key={l} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          <span style={{ width: "160px", textAlign: "right", color: "#6c7086", fontSize: "13px", paddingRight: "6px" }}>{l}</span>
          <input readOnly value={v} style={{ background: "#181825", border: "1px solid #45475a", color: "#cdd6f4", padding: "3px 8px", fontFamily: "monospace", width: "100px", fontSize: "13px" }} />
        </div>
      ))}
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#e64553", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Sell Tokens</button>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Withdraw SOL</button>
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", background: "#181825", padding: "6px", fontFamily: "monospace", fontSize: "12px", color: "#6c7086", marginTop: "4px" }}>
        <div>Awaiting sell/withdraw command…</div>
      </div>
    </div>
  );
}

function ManageWalletsPane() {
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        ⚙️  Manage Wallets
      </div>
      <div style={{ flex: 1, border: "1px solid #313244", overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "monospace", fontSize: "13px" }}>
          <thead>
            <tr style={{ background: "#181825", color: "#6c7086", borderBottom: "1px solid #313244" }}>
              <th style={{ textAlign: "left", padding: "4px 10px", fontWeight: "normal" }}>Label</th>
              <th style={{ textAlign: "left", padding: "4px 10px", fontWeight: "normal" }}>Public Key</th>
              <th style={{ textAlign: "right", padding: "4px 10px", fontWeight: "normal" }}>SOL</th>
            </tr>
          </thead>
          <tbody>
            {WALLET_DATA.map((w, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #1e1e2e", background: i === 0 ? "#2a2637" : "#1e1e2e" }}>
                <td style={{ padding: "5px 10px", color: w.dev ? "#cdd6f4" : "#a6adc8", fontWeight: w.dev ? "bold" : "normal" }}>{w.label}</td>
                <td style={{ padding: "5px 10px", color: "#6c7086", fontSize: "11px" }}>{w.addr}</td>
                <td style={{ padding: "5px 10px", textAlign: "right", color: w.dev ? "#a6e3a1" : "#cdd6f4" }}>{w.bal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 14px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Generate Wallets</button>
        <button style={{ background: "#181825", color: "#cdd6f4", border: "1px solid #45475a", padding: "4px 14px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Export Keys</button>
        <button style={{ background: "#e64553", color: "#fff", border: "none", padding: "4px 14px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Wipe Wallets</button>
      </div>
    </div>
  );
}

function PreloadPane() {
  return (
    <div className="flex flex-col h-full p-3 gap-2">
      <div style={{ color: "#a6e3a1", fontWeight: "bold", borderBottom: "1px solid #313244", paddingBottom: "6px" }}>
        💾  Pre-load Token
      </div>
      <div style={{ color: "#6c7086", fontSize: "13px", marginBottom: "8px" }}>
        Pre-load an existing token for bundle buy / monitoring without recreating it.
      </div>
      {[["Mint Address", ""], ["Token Symbol", ""], ["Token Name", ""]].map(([l, v]) => (
        <div key={l} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
          <span style={{ width: "140px", textAlign: "right", color: "#6c7086", fontSize: "13px", paddingRight: "6px" }}>{l}</span>
          <input readOnly value={v} placeholder={l === "Mint Address" ? "Base58 address…" : ""} style={{
            background: "#181825", border: "1px solid #45475a", color: "#cdd6f4",
            padding: "3px 8px", fontFamily: "monospace", width: "260px", fontSize: "13px"
          }} />
        </div>
      ))}
      <div style={{ display: "flex", gap: "8px", paddingTop: "4px" }}>
        <button style={{ background: "#1c6ef3", color: "#fff", border: "none", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Load Token</button>
        <button style={{ background: "#181825", color: "#cdd6f4", border: "1px solid #45475a", padding: "4px 16px", fontFamily: "monospace", fontSize: "13px", cursor: "pointer" }}>Cancel</button>
      </div>
    </div>
  );
}

const PANE_COMPONENTS: Record<string, () => JSX.Element> = {
  balances:  BalancesPane,
  distribute: DistributePane,
  create:    CreateTokenPane,
  bundle:    BundleBuyPane,
  monitor:   MonitorPane,
  sell:      SellPane,
  preload:   PreloadPane,
  wallets:   ManageWalletsPane,
  settings:  SettingsPane,
};

export function TUI() {
  const [active, setActive] = useState("balances");
  const now = new Date();
  const clock = now.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

  const PaneComponent = PANE_COMPONENTS[active] ?? BalancesPane;

  return (
    <div style={{
      width: "100vw", height: "100vh",
      background: "#1e1e2e", color: "#cdd6f4",
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      display: "flex", flexDirection: "column", overflow: "hidden",
      fontSize: "14px",
    }}>
      {/* Header */}
      <div style={{
        height: "28px", background: "#181825",
        borderBottom: "1px solid #313244",
        display: "flex", alignItems: "center",
        justifyContent: "space-between", padding: "0 12px",
        flexShrink: 0,
      }}>
        <span style={{ color: "#a6e3a1", fontWeight: "bold", letterSpacing: "0.05em" }}>
          pump.fun bot
        </span>
        <span style={{ color: "#6c7086", fontSize: "12px" }}>v1.0.0</span>
        <span style={{ color: "#cdd6f4", fontSize: "12px" }}>{clock}</span>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Sidebar */}
        <div style={{
          width: "210px", flexShrink: 0,
          background: "#24273a",
          borderRight: "1px solid #a6e3a1",
          display: "flex", flexDirection: "column",
          padding: "8px 0",
        }}>
          {/* Brand */}
          <div style={{
            textAlign: "center", color: "#a6e3a1", fontWeight: "bold",
            padding: "0 8px 8px 8px",
            borderBottom: "1px solid #313244", marginBottom: "8px",
            letterSpacing: "0.08em", fontSize: "13px",
          }}>
            ⚡ PUMP.FUN BOT
          </div>

          {/* Mode Badge */}
          <div style={{
            margin: "0 8px 8px 8px", padding: "2px 8px",
            border: "1px solid #f9e2af", background: "rgba(249,226,175,0.08)",
            color: "#f9e2af", textAlign: "center", fontSize: "12px",
          }}>
            🔴 DRY RUN
          </div>

          {/* Nav list */}
          <div style={{ flex: 1 }}>
            {NAV_ITEMS.map(({ key, label }) => {
              const isActive = active === key;
              return (
                <div
                  key={key}
                  onClick={() => setActive(key)}
                  style={{
                    padding: "5px 16px",
                    cursor: "pointer",
                    color: isActive ? "#a6e3a1" : "#6c7086",
                    fontWeight: isActive ? "bold" : "normal",
                    background: isActive ? "rgba(166,227,161,0.12)" : "transparent",
                    fontSize: "13px",
                    whiteSpace: "nowrap",
                    userSelect: "none",
                    transition: "background 0.1s",
                  }}
                >
                  {label}
                </div>
              );
            })}
          </div>
        </div>

        {/* Content area */}
        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <PaneComponent />
        </div>
      </div>

      {/* Footer */}
      <div style={{
        height: "24px", background: "#181825",
        borderTop: "1px solid #313244",
        display: "flex", alignItems: "center", gap: "0",
        flexShrink: 0, overflow: "hidden",
      }}>
        {[
          ["q", "Quit"],
          ["r", "Refresh"],
          ["Escape", "Menu"],
          ["ctrl+b", "Sidebar"],
        ].map(([key, desc]) => (
          <span key={key} style={{ display: "flex", alignItems: "stretch", fontSize: "12px" }}>
            <span style={{ background: "#313244", color: "#cdd6f4", padding: "0 6px", lineHeight: "24px" }}>{key}</span>
            <span style={{ background: "#1e1e2e", color: "#6c7086", padding: "0 8px", lineHeight: "24px", borderRight: "1px solid #313244" }}>{desc}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
