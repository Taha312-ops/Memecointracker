"""
Keyboard builder — all inline bubble keyboards.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=url)


def mk(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows))


# ── Main menu ────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return mk(
        [btn("🔥 New Pairs",       "menu_pairs"),
         btn("📈 Gainers/Losers",  "menu_gainers")],
        [btn("🧠 Top Wallets",     "menu_wallets"),
         btn("👛 My Wallet",       "menu_mywallet")],
        [btn("🔍 Track Wallets",   "menu_track"),
         btn("🔎 Search Wallet",   "menu_search")],
        [btn("📊 Trade History",   "menu_history"),
         btn("⚙️ Settings",        "menu_settings")],
    )


# ── Chain selector ───────────────────────────────────────────

def chain_kb(prefix: str) -> InlineKeyboardMarkup:
    return mk(
        [btn("🟣 Solana", f"{prefix}_sol"),
         btn("🔷 ETH",    f"{prefix}_eth")],
        [btn("🟡 BSC",    f"{prefix}_bsc"),
         btn("🔵 Arb",    f"{prefix}_arb")],
        [btn("🔵 Base",   f"{prefix}_base"),
         btn("🔴 OP",     f"{prefix}_op")],
        [btn("🏠 Home",   "home")],
    )


# ── Timeframe selector ───────────────────────────────────────

def timeframe_kb(prefix: str, chain: str) -> InlineKeyboardMarkup:
    return mk(
        [btn("30m",  f"{prefix}_{chain}_30m"),
         btn("1h",   f"{prefix}_{chain}_1h"),
         btn("6h",   f"{prefix}_{chain}_6h")],
        [btn("24h",  f"{prefix}_{chain}_24h"),
         btn("3d",   f"{prefix}_{chain}_3d")],
        [btn("🔙 Back", f"back_{prefix}"),
         btn("🏠 Home",  "home")],
    )


# ── Gainers / Losers ─────────────────────────────────────────

def gainers_losers_kb(chain: str, timeframe: str,
                      tokens: List[dict], mode: str = "gainers") -> InlineKeyboardMarkup:
    rows = []
    for i, t in enumerate(tokens[:5]):
        sym    = t.get("symbol", "???")
        change = t.get("price_change") or t.get("price_change_h24") or 0
        arrow  = "▲" if float(change) >= 0 else "▼"
        rows.append([btn(
            f"{arrow} {sym} {float(change):+.1f}%",
            f"token_{t.get('address','x')}_{chain}"
        )])
    other = "losers" if mode == "gainers" else "gainers"
    rows.append([
        btn(f"{'📉 Losers' if mode == 'gainers' else '📈 Gainers'}",
            f"gl_{other}_{chain}_{timeframe}"),
        btn("🔄 Refresh", f"gl_{mode}_{chain}_{timeframe}"),
    ])
    rows.append([btn("🔙 Back", "menu_gainers"), btn("🏠 Home", "home")])
    return InlineKeyboardMarkup(rows)


# ── Token detail ─────────────────────────────────────────────

def token_detail_kb(token_address: str, chain: str,
                    dex_url: str = "") -> InlineKeyboardMarkup:
    rows = [
        [btn("🛡 Risk Check",    f"risk_{token_address}_{chain}"),
         btn("📋 Copy Address",  f"copy_{token_address}")],
        [btn("🔙 Back", "menu_gainers"),
         btn("🏠 Home", "home")],
    ]
    if dex_url:
        rows.insert(1, [url_btn("📊 DexScreener", dex_url)])
    return InlineKeyboardMarkup(rows)


# ── Top wallets ──────────────────────────────────────────────

def top_wallets_kb(wallets: List[dict], mode: str,
                   chain: str, timeframe: str) -> InlineKeyboardMarkup:
    rows = []
    for w in wallets[:5]:
        addr = w.get("address", "")
        pnl  = w.get("pnl_usd", 0)
        short = f"{addr[:6]}...{addr[-4:]}"
        emoji = "💚" if float(pnl) >= 0 else "🔴"
        rows.append([btn(
            f"{emoji} {short} ${float(pnl):+,.0f}",
            f"wallet_detail_{addr}_{chain}"
        )])
    other = "losers" if mode == "gainers" else "gainers"
    rows.append([
        btn(f"{'📉 Biggest Losers' if mode == 'gainers' else '📈 Biggest Gainers'}",
            f"tw_{other}_{chain}_{timeframe}"),
        btn("🔄 Refresh", f"tw_{mode}_{chain}_{timeframe}"),
    ])
    rows.append([btn("🔙 Back", "menu_wallets"), btn("🏠 Home", "home")])
    return InlineKeyboardMarkup(rows)


# ── Wallet detail ────────────────────────────────────────────

def wallet_detail_kb(wallet_address: str, chain: str,
                     already_tracked: bool = False) -> InlineKeyboardMarkup:
    track_label = "✅ Tracked" if already_tracked else "➕ Track Wallet"
    track_data  = f"already_tracked_{wallet_address}" if already_tracked \
                  else f"track_add_{wallet_address}_{chain}"
    return mk(
        [btn(track_label,          track_data)],
        [btn("📋 Copy Address",    f"copy_{wallet_address}"),
         btn("🔄 Refresh",         f"wallet_detail_{wallet_address}_{chain}")],
        [btn("🔙 Back", "menu_wallets"), btn("🏠 Home", "home")],
    )


# ── Track list ───────────────────────────────────────────────

def tracked_list_kb(tracked: List[dict]) -> InlineKeyboardMarkup:
    rows = []
    for t in tracked:
        label = t.get("label") or f"{t['wallet_address'][:6]}...{t['wallet_address'][-4:]}"
        rows.append([btn(f"👛 {label}", f"track_view_{t['wallet_address']}")])
    rows.append([btn("🔍 Search & Add", "menu_search"), btn("🏠 Home", "home")])
    return InlineKeyboardMarkup(rows)


# ── Single tracked wallet ────────────────────────────────────

def tracked_wallet_kb(wallet_address: str, wallet: dict) -> InlineKeyboardMarkup:
    ab_icon  = "🟢" if wallet.get("autobuy_enabled")  else "⚪"
    as_icon  = "🟢" if wallet.get("autosell_enabled") else "⚪"
    return mk(
        [btn(f"{ab_icon} Auto-Buy",  f"autobuy_toggle_{wallet_address}"),
         btn(f"{as_icon} Auto-Sell", f"autosell_toggle_{wallet_address}")],
        [btn("✏️ Set Buy Amount",    f"autobuy_amount_{wallet_address}"),
         btn("✏️ Set Sell %",        f"autosell_pct_{wallet_address}")],
        [btn("🏷 Rename",            f"track_rename_{wallet_address}"),
         btn("🗑 Remove",            f"track_remove_{wallet_address}")],
        [btn("🔙 Back", "menu_track"), btn("🏠 Home", "home")],
    )


# ── My wallet ────────────────────────────────────────────────

def my_wallet_kb() -> InlineKeyboardMarkup:
    return mk(
        [btn("🟣 Solana Wallet",  "wallet_show_solana"),
         btn("🔷 EVM Wallet",    "wallet_show_evm")],
        [btn("🔑 Show Seed",     "wallet_seed"),
         btn("🔐 Show PK",       "wallet_pk")],
        [btn("🏠 Home", "home")],
    )


def wallet_show_kb(chain_type: str) -> InlineKeyboardMarkup:
    return mk(
        [btn("🔑 Show Seed Phrase", f"wallet_seed_{chain_type}"),
         btn("🔐 Show Private Key", f"wallet_pk_{chain_type}")],
        [btn("🔙 Back", "menu_mywallet"), btn("🏠 Home", "home")],
    )


# ── Risk check ───────────────────────────────────────────────

def risk_kb(token_address: str, chain: str) -> InlineKeyboardMarkup:
    return mk(
        [btn("🔄 Re-check",  f"risk_{token_address}_{chain}"),
         btn("📋 Copy CA",   f"copy_{token_address}")],
        [btn("🔙 Back", "menu_gainers"), btn("🏠 Home", "home")],
    )


# ── Search result ────────────────────────────────────────────

def search_result_kb(wallet_address: str, chain: str,
                     already_tracked: bool = False) -> InlineKeyboardMarkup:
    track_label = "✅ Already Tracked" if already_tracked else "➕ Add to Tracked"
    track_data  = f"already_tracked_{wallet_address}" if already_tracked \
                  else f"track_add_{wallet_address}_{chain}"
    return mk(
        [btn(track_label, track_data)],
        [btn("📋 Copy Address", f"copy_{wallet_address}")],
        [btn("🔙 Back", "menu_search"), btn("🏠 Home", "home")],
    )


# ── Confirm / Cancel ─────────────────────────────────────────

def confirm_kb(confirm_data: str, cancel_data: str = "home") -> InlineKeyboardMarkup:
    return mk([btn("✅ Confirm", confirm_data), btn("❌ Cancel", cancel_data)])


# ── Settings ─────────────────────────────────────────────────

def settings_kb() -> InlineKeyboardMarkup:
    return mk(
        [btn("🔑 Change Password", "settings_pw")],
        [btn("🏠 Home", "home")],
    )
