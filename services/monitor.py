"""
Monitor service — polls tracked wallets every N seconds
and fires Telegram notifications on new trades.
"""

import asyncio
import logging
import os
from typing import Dict, List

from services.database import get_all_tracked_wallets, log_trade, add_notification
from services.market_data import get_wallet_recent_trades

logger = logging.getLogger(__name__)

POLL_SECONDS = int(os.getenv("MONITOR_POLL_SECONDS", "30"))

# cache: wallet_address -> last seen trade id
_last_seen: Dict[str, str] = {}


async def _check_wallet(wallet: Dict, app) -> None:
    address = wallet["wallet_address"]
    chain   = wallet["chain"]
    user_id = wallet["user_id"]

    try:
        trades = await get_wallet_recent_trades(address, chain)
    except Exception as e:
        logger.warning(f"[monitor] fetch error {address}: {e}")
        return

    if not trades:
        return

    latest    = trades[0]
    trade_id  = str(latest.get("id") or latest.get("tx_hash") or "")
    cache_key = f"{user_id}:{address}"

    if _last_seen.get(cache_key) == trade_id:
        return  # nothing new

    _last_seen[cache_key] = trade_id

    action       = latest.get("type", "buy").lower()
    token_symbol = latest.get("token_symbol") or latest.get("symbol") or "???"
    token_addr   = latest.get("token_address") or latest.get("address") or ""
    amount_usd   = float(latest.get("amount_usd") or latest.get("value_usd") or 0)

    label = wallet.get("label") or f"{address[:6]}...{address[-4:]}"

    emoji  = "🟢" if action == "buy" else "🔴"
    notify = (
        f"{emoji} <b>Tracked wallet alert</b>\n"
        f"👛 <b>{label}</b>\n"
        f"📌 Action: <b>{action.upper()}</b>\n"
        f"🪙 Token: <b>{token_symbol}</b>\n"
        f"💵 Value: <b>${amount_usd:,.2f}</b>\n"
        f"🔗 Chain: <b>{chain.upper()}</b>"
    )

    await add_notification(user_id, notify)

    try:
        await app.bot.send_message(
            chat_id=user_id,
            text=notify,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"[monitor] send_message failed uid={user_id}: {e}")

    # ── Auto-buy / auto-sell ──────────────────────────────────
    if action == "buy" and wallet.get("autobuy_enabled"):
        await _handle_autobuy(wallet, token_addr, token_symbol, amount_usd, chain, app)
    elif action == "sell" and wallet.get("autosell_enabled"):
        await _handle_autosell(wallet, token_addr, token_symbol, chain, app)


async def _handle_autobuy(wallet: Dict, token_addr: str, token_symbol: str,
                           amount_usd: float, chain: str, app) -> None:
    from services.database import get_wallet_by_chain
    from services.wallet_service import reveal_wallet_pk
    from services.trade_service import execute_trade

    user_id    = wallet["user_id"]
    buy_amount = float(wallet.get("autobuy_amount_usd") or 0)
    if buy_amount <= 0:
        return

    chain_type = "solana" if chain == "sol" else "evm"
    user_wallet = await get_wallet_by_chain(user_id, chain_type)
    if not user_wallet:
        return

    try:
        pk     = reveal_wallet_pk(user_id, user_wallet["encrypted_pk"])
        result = await execute_trade(
            chain=chain,
            wallet_address=user_wallet["address"],
            private_key=pk,
            token_address=token_addr,
            amount_usd=buy_amount,
            action="buy",
        )
        status   = "success" if result.get("ok") else "failed"
        tx_hash  = result.get("tx_hash") or ""
        await log_trade(user_id, "buy", token_addr, token_symbol, chain,
                        buy_amount, 0, tx_hash, status,
                        triggered_by=wallet["wallet_address"])

        msg = (
            f"🤖 <b>Auto-buy executed</b>\n"
            f"🪙 {token_symbol} — ${buy_amount:.2f}\n"
            f"{'✅ ' + tx_hash[:16] + '...' if status == 'success' else '❌ Failed'}"
        )
        await app.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[autobuy] uid={user_id} error: {e}")


async def _handle_autosell(wallet: Dict, token_addr: str, token_symbol: str,
                            chain: str, app) -> None:
    from services.database import get_wallet_by_chain
    from services.wallet_service import reveal_wallet_pk
    from services.trade_service import execute_trade

    user_id  = wallet["user_id"]
    pct      = float(wallet.get("autosell_percentage") or 100)
    if pct <= 0:
        return

    chain_type  = "solana" if chain == "sol" else "evm"
    user_wallet = await get_wallet_by_chain(user_id, chain_type)
    if not user_wallet:
        return

    try:
        pk     = reveal_wallet_pk(user_id, user_wallet["encrypted_pk"])
        # amount_usd here represents the % of holdings — trade_service handles it
        result = await execute_trade(
            chain=chain,
            wallet_address=user_wallet["address"],
            private_key=pk,
            token_address=token_addr,
            amount_usd=pct,       # passed as percentage for sell
            action="sell",
        )
        status  = "success" if result.get("ok") else "failed"
        tx_hash = result.get("tx_hash") or ""
        await log_trade(user_id, "sell", token_addr, token_symbol, chain,
                        0, 0, tx_hash, status,
                        triggered_by=wallet["wallet_address"])

        msg = (
            f"🤖 <b>Auto-sell executed</b>\n"
            f"🪙 {token_symbol} — {pct:.0f}% of holdings\n"
            f"{'✅ ' + tx_hash[:16] + '...' if status == 'success' else '❌ Failed'}"
        )
        await app.bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"[autosell] uid={user_id} error: {e}")


async def monitor_loop(app) -> None:
    logger.info(f"[monitor] started — polling every {POLL_SECONDS}s")
    while True:
        try:
            wallets = await get_all_tracked_wallets()
            tasks   = [_check_wallet(w, app) for w in wallets]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"[monitor] loop error: {e}")
        await asyncio.sleep(POLL_SECONDS)
