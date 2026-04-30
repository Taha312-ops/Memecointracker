"""
Message formatters — build HTML strings for every bot screen.
"""

from typing import List, Dict
from datetime import datetime


def fmt_number(n) -> str:
    try:
        n = float(n)
        if n >= 1_000_000:
            return f"${n/1_000_000:.2f}M"
        if n >= 1_000:
            return f"${n/1_000:.1f}K"
        return f"${n:.2f}"
    except Exception:
        return str(n)


def fmt_price(p) -> str:
    try:
        p = float(p)
        if p < 0.000001:
            return f"${p:.10f}"
        if p < 0.01:
            return f"${p:.6f}"
        return f"${p:.4f}"
    except Exception:
        return str(p)


def fmt_change(c) -> str:
    try:
        c = float(c)
        arrow = "▲" if c >= 0 else "▼"
        return f"{arrow} {c:+.2f}%"
    except Exception:
        return str(c)


def fmt_address(addr: str, length: int = 8) -> str:
    if len(addr) <= length * 2:
        return addr
    return f"{addr[:length]}...{addr[-4:]}"


CHAIN_EMOJI = {
    "eth": "🔷", "bsc": "🟡", "sol": "🟣",
    "arb": "🔵", "base": "🔵", "op": "🔴",
}


# ── Welcome ──────────────────────────────────────────────────

def welcome_new_msg() -> str:
    return (
        "👋 <b>Welcome to MemeCoin Tracker Bot!</b>\n\n"
        "🔐 First, set a <b>password</b> to protect your wallets.\n"
        "This password encrypts your seed phrases and is required "
        "to view keys or activate auto-trading.\n\n"
        "Please type your desired password now:"
    )


def welcome_back_msg(username: str) -> str:
    return (
        f"👋 <b>Welcome back, {username}!</b>\n\n"
        "What would you like to do today?"
    )


def password_prompt_msg() -> str:
    return "🔐 Enter your password to continue:"


# ── New pairs ────────────────────────────────────────────────

def new_pairs_msg(pairs: List[Dict], chain: str) -> str:
    emoji = CHAIN_EMOJI.get(chain, "🔗")
    lines = [f"{emoji} <b>New Pairs on {chain.upper()}</b>\n"]
    for i, p in enumerate(pairs[:10], 1):
        age = ""
        if p.get("created_at"):
            ts  = int(p["created_at"]) // 1000
            age = f" · {int((datetime.now().timestamp() - ts) / 60)}m ago"
        lines.append(
            f"{i}. <b>{p['symbol']}</b> — {fmt_price(p['price_usd'])}\n"
            f"   24h: {fmt_change(p.get('price_change_h24', 0))} "
            f"| Liq: {fmt_number(p.get('liquidity_usd', 0))}{age}"
        )
    return "\n".join(lines)


# ── Gainers / Losers ─────────────────────────────────────────

def gainers_msg(tokens: List[Dict], chain: str, timeframe: str) -> str:
    emoji = CHAIN_EMOJI.get(chain, "🔗")
    lines = [f"📈 <b>Top Gainers — {chain.upper()} / {timeframe}</b>\n"]
    for i, t in enumerate(tokens[:10], 1):
        change = t.get("price_change") or t.get("price_change_h24") or 0
        lines.append(
            f"{i}. <b>{t.get('symbol','???')}</b> {fmt_change(change)}\n"
            f"   Price: {fmt_price(t.get('price_usd', 0))} "
            f"| Vol: {fmt_number(t.get('volume_h24', 0))}"
        )
    return "\n".join(lines)


def losers_msg(tokens: List[Dict], chain: str, timeframe: str) -> str:
    lines = [f"📉 <b>Top Losers — {chain.upper()} / {timeframe}</b>\n"]
    for i, t in enumerate(tokens[:10], 1):
        change = t.get("price_change") or t.get("price_change_h24") or 0
        lines.append(
            f"{i}. <b>{t.get('symbol','???')}</b> {fmt_change(change)}\n"
            f"   Price: {fmt_price(t.get('price_usd', 0))} "
            f"| Vol: {fmt_number(t.get('volume_h24', 0))}"
        )
    return "\n".join(lines)


# ── Token detail ─────────────────────────────────────────────

def token_detail_msg(token: Dict, chain: str) -> str:
    emoji = CHAIN_EMOJI.get(chain, "🔗")
    return (
        f"{emoji} <b>{token.get('name','?')} ({token.get('symbol','?')})</b>\n\n"
        f"💰 Price: <b>{fmt_price(token.get('price_usd', 0))}</b>\n"
        f"📈 1h:  {fmt_change(token.get('price_change_h1', 0))}\n"
        f"📈 6h:  {fmt_change(token.get('price_change_h6', 0))}\n"
        f"📈 24h: {fmt_change(token.get('price_change_h24', 0))}\n\n"
        f"📊 Volume 24h: <b>{fmt_number(token.get('volume_h24', 0))}</b>\n"
        f"💧 Liquidity:  <b>{fmt_number(token.get('liquidity_usd', 0))}</b>\n"
        f"🏦 FDV:        <b>{fmt_number(token.get('fdv', 0))}</b>\n\n"
        f"📋 CA: <code>{token.get('address','')}</code>"
    )


# ── Risk check ───────────────────────────────────────────────

def risk_msg(token_address: str, chain: str,
             security: Dict, score: int,
             label: str, flags: List[str]) -> str:
    flags_str = "\n".join(f"  {f}" for f in flags) if flags else "  ✅ No issues found"
    tax_bar   = "🟩" * min(int(security.get("sell_tax", 0) // 10), 10)
    return (
        f"🛡 <b>Security Report</b>\n"
        f"📋 <code>{fmt_address(token_address)}</code>\n"
        f"🔗 Chain: <b>{chain.upper()}</b>\n\n"
        f"<b>Risk Score: {score}/100 — {label}</b>\n\n"
        f"🔍 <b>Flags:</b>\n{flags_str}\n\n"
        f"💸 Buy Tax:  <b>{security.get('buy_tax', 0):.1f}%</b>\n"
        f"💸 Sell Tax: <b>{security.get('sell_tax', 0):.1f}%</b> {tax_bar}\n"
        f"🔒 LP Locked: <b>{'Yes' if security.get('lp_locked') else 'No'}</b> "
        f"({security.get('lp_lock_percent', 0):.0f}%)\n"
        f"👥 Holders: <b>{security.get('holder_count', 0):,}</b>\n"
        f"📝 Open Source: <b>{'Yes' if security.get('is_open_source') else 'No'}</b>"
    )


# ── Top wallets ──────────────────────────────────────────────

def top_wallets_msg(wallets: List[Dict], mode: str,
                    chain: str, timeframe: str) -> str:
    title = "📈 Biggest Winners" if mode == "gainers" else "📉 Biggest Losers"
    emoji = CHAIN_EMOJI.get(chain, "🔗")
    lines = [f"{emoji} <b>{title} — {chain.upper()} / {timeframe}</b>\n"]
    for i, w in enumerate(wallets[:10], 1):
        addr     = w.get("address", "")
        pnl      = float(w.get("pnl_usd", 0))
        wr       = float(w.get("win_rate", 0)) * 100
        trades   = w.get("trades", 0)
        pnl_icon = "💚" if pnl >= 0 else "🔴"
        lines.append(
            f"{i}. <code>{fmt_address(addr)}</code>\n"
            f"   {pnl_icon} PnL: <b>${pnl:+,.0f}</b> "
            f"| WR: <b>{wr:.0f}%</b> | Trades: <b>{trades}</b>"
        )
    return "\n".join(lines)


# ── Wallet detail ────────────────────────────────────────────

def wallet_detail_msg(address: str, chain: str, pnl_data: Dict) -> str:
    pnl     = float(pnl_data.get("realized_profit", 0))
    wr      = float(pnl_data.get("win_rate", 0)) * 100
    trades  = pnl_data.get("trade_count", 0)
    emoji   = CHAIN_EMOJI.get(chain, "🔗")
    return (
        f"{emoji} <b>Wallet Detail</b>\n\n"
        f"📋 <code>{address}</code>\n\n"
        f"💰 Realized PnL: <b>${pnl:+,.2f}</b>\n"
        f"🎯 Win Rate: <b>{wr:.1f}%</b>\n"
        f"📊 Total Trades: <b>{trades}</b>\n"
        f"🔗 Chain: <b>{chain.upper()}</b>"
    )


# ── My wallet ────────────────────────────────────────────────

def my_wallet_msg(evm_addr: str, sol_addr: str) -> str:
    return (
        "👛 <b>Your Wallets</b>\n\n"
        f"🔷 <b>EVM Wallet</b>\n"
        f"<code>{evm_addr}</code>\n\n"
        f"🟣 <b>Solana Wallet</b>\n"
        f"<code>{sol_addr}</code>\n\n"
        "⚠️ <i>Never share your seed phrases or private keys with anyone.</i>"
    )


def seed_reveal_msg(chain_type: str, seed: str) -> str:
    return (
        f"🔑 <b>{chain_type.upper()} Seed Phrase</b>\n\n"
        f"<code>{seed}</code>\n\n"
        "⚠️ <b>WARNING:</b> Never share this with anyone.\n"
        "<i>This message will self-delete in 30 seconds.</i>"
    )


def pk_reveal_msg(chain_type: str, pk: str) -> str:
    return (
        f"🔐 <b>{chain_type.upper()} Private Key</b>\n\n"
        f"<code>{pk}</code>\n\n"
        "⚠️ <b>WARNING:</b> Never share this with anyone.\n"
        "<i>This message will self-delete in 30 seconds.</i>"
    )


# ── Tracked wallets ──────────────────────────────────────────

def tracked_list_msg(tracked: List[Dict]) -> str:
    if not tracked:
        return (
            "🔍 <b>Tracked Wallets</b>\n\n"
            "You have no tracked wallets yet.\n"
            "You can track up to <b>5 wallets</b>.\n\n"
            "Use <b>Search Wallet</b> to find and add wallets."
        )
    lines = ["🔍 <b>Tracked Wallets</b>\n"]
    for t in tracked:
        label = t.get("label") or fmt_address(t["wallet_address"])
        ab    = "🟢" if t.get("autobuy_enabled")  else "⚪"
        as_   = "🟢" if t.get("autosell_enabled") else "⚪"
        lines.append(
            f"👛 <b>{label}</b>\n"
            f"   {t['chain'].upper()} · Auto-Buy {ab} · Auto-Sell {as_}\n"
            f"   <code>{t['wallet_address']}</code>"
        )
    lines.append(f"\n<i>{len(tracked)}/5 slots used</i>")
    return "\n\n".join(lines)


def tracked_wallet_detail_msg(wallet: Dict) -> str:
    label = wallet.get("label") or fmt_address(wallet["wallet_address"])
    ab    = "🟢 ON" if wallet.get("autobuy_enabled")  else "⚪ OFF"
    as_   = "🟢 ON" if wallet.get("autosell_enabled") else "⚪ OFF"
    buy_a = wallet.get("autobuy_amount_usd", 0)
    sell_p= wallet.get("autosell_percentage", 100)
    return (
        f"👛 <b>{label}</b>\n\n"
        f"📋 <code>{wallet['wallet_address']}</code>\n"
        f"🔗 Chain: <b>{wallet['chain'].upper()}</b>\n\n"
        f"🤖 Auto-Buy:  <b>{ab}</b> — ${buy_a:.2f} per buy\n"
        f"🤖 Auto-Sell: <b>{as_}</b> — {sell_p:.0f}% of holdings\n\n"
        "<i>Toggle buttons below to enable/disable copy trading.</i>\n"
        "<i>Password required to activate.</i>"
    )


# ── Trade history ────────────────────────────────────────────

def trade_history_msg(trades: List[Dict]) -> str:
    if not trades:
        return "📊 <b>Trade History</b>\n\nNo trades yet."
    lines = ["📊 <b>Trade History</b>\n"]
    for t in trades[:15]:
        action = t.get("action", "?").upper()
        symbol = t.get("token_symbol", "???")
        chain  = t.get("chain", "?").upper()
        usd    = float(t.get("amount_usd") or 0)
        status = t.get("status", "?")
        emoji  = "🟢" if action == "BUY" else "🔴"
        ok     = "✅" if status == "success" else "⏳" if status == "pending" else "❌"
        by     = t.get("triggered_by", "manual")
        trig   = "🤖 auto" if by != "manual" else "👤 manual"
        lines.append(
            f"{emoji} <b>{action}</b> {symbol} · {chain} · ${usd:.2f}\n"
            f"   {ok} {status} · {trig}"
        )
    return "\n\n".join(lines)
