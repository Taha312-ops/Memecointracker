"""
All Telegram command + callback handlers.
"""

import asyncio
import logging
from typing import Optional

from telegram import Update, Message
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from services.database import (
    user_exists, create_user, get_user, get_wallets,
    get_wallet_by_chain, save_wallet,
    get_tracked_wallets, add_tracked_wallet,
    remove_tracked_wallet, update_tracked_wallet,
    get_trade_history,
)
from services.wallet_service import (
    create_user_wallets, hash_password, verify_password,
    reveal_wallet_seed, reveal_wallet_pk,
)
from services.market_data import (
    get_new_pairs, get_gainers_losers, get_top_wallets,
    check_token_security, build_risk_score,
    get_wallet_pnl,
)
from utils.keyboards import (
    main_menu_kb, chain_kb, timeframe_kb,
    gainers_losers_kb, token_detail_kb,
    top_wallets_kb, wallet_detail_kb,
    tracked_list_kb, tracked_wallet_kb,
    my_wallet_kb, wallet_show_kb,
    risk_kb, search_result_kb,
    confirm_kb, settings_kb,
)
from utils.formatters import (
    welcome_new_msg, welcome_back_msg, password_prompt_msg,
    new_pairs_msg, gainers_msg, losers_msg,
    token_detail_msg, risk_msg,
    top_wallets_msg, wallet_detail_msg,
    my_wallet_msg, seed_reveal_msg, pk_reveal_msg,
    tracked_list_msg, tracked_wallet_detail_msg,
    trade_history_msg,
)

logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────
(
    STATE_SET_PW, STATE_VERIFY_PW, STATE_CHANGE_PW,
    STATE_TRACK_ADDR, STATE_TRACK_CHAIN, STATE_TRACK_LABEL,
    STATE_SEARCH_ADDR, STATE_AUTOBUY_AMT, STATE_AUTOSELL_PCT,
    STATE_REVEAL_PW, STATE_RENAME_LABEL,
) = range(11)

# ── Helper: send or edit ──────────────────────────────────────

async def _reply(update: Update, text: str, reply_markup=None, parse_mode="HTML"):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        except Exception:
            await update.callback_query.message.reply_text(
                text, reply_markup=reply_markup, parse_mode=parse_mode
            )
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )


async def _answer(update: Update, text: str = ""):
    if update.callback_query:
        await update.callback_query.answer(text)


# ── /start ────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    uid  = user.id

    if not await user_exists(uid):
        await _reply(update, welcome_new_msg())
        return STATE_SET_PW

    await _reply(
        update,
        welcome_back_msg(user.first_name or user.username or "trader"),
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END


async def set_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    pw = update.message.text.strip()
    if len(pw) < 6:
        await update.message.reply_text("❌ Password must be at least 6 characters. Try again:")
        return STATE_SET_PW

    uid      = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or "user"
    pw_hash  = hash_password(pw, uid)

    await create_user(uid, username, pw_hash)

    # Generate wallets
    await update.message.reply_text("⏳ Creating your wallets...")
    wallets = create_user_wallets(uid)

    await save_wallet(uid, "evm",    wallets["evm"]["address"],
                      wallets["evm"]["encrypted_seed"],    wallets["evm"]["encrypted_pk"])
    await save_wallet(uid, "solana", wallets["solana"]["address"],
                      wallets["solana"]["encrypted_seed"], wallets["solana"]["encrypted_pk"])

    await update.message.reply_text(
        f"✅ <b>Wallets created!</b>\n\n"
        f"🔷 EVM:    <code>{wallets['evm']['address']}</code>\n"
        f"🟣 Solana: <code>{wallets['solana']['address']}</code>\n\n"
        "Your seed phrases are encrypted with your password.",
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END


# ── Home ──────────────────────────────────────────────────────

async def cb_home(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    user = update.effective_user
    await _reply(
        update,
        welcome_back_msg(user.first_name or "trader"),
        reply_markup=main_menu_kb(),
    )


# ── New pairs ─────────────────────────────────────────────────

async def cb_menu_pairs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    await _reply(update, "🔥 Select chain for new pairs:", reply_markup=chain_kb("pairs"))


async def cb_pairs_chain(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    chain = update.callback_query.data.split("_")[1]
    await _reply(update, "⏳ Fetching new pairs...")
    pairs = await get_new_pairs(chain, 20)
    await _reply(
        update,
        new_pairs_msg(pairs, chain),
        reply_markup=chain_kb("pairs"),
    )


# ── Gainers / Losers ─────────────────────────────────────────

async def cb_menu_gainers(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    await _reply(update, "📈 Select chain:", reply_markup=chain_kb("gl"))


async def cb_gl_chain(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    chain = update.callback_query.data.split("_")[1]
    ctx.user_data["gl_chain"] = chain
    await _reply(update, f"📊 Select timeframe for {chain.upper()}:",
                 reply_markup=timeframe_kb("gl", chain))


async def cb_gl_tf(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts     = update.callback_query.data.split("_")
    chain, tf = parts[1], parts[2]
    mode      = ctx.user_data.get("gl_mode", "gainers")
    await _reply(update, "⏳ Loading...")
    data    = await get_gainers_losers(chain, tf)
    tokens  = data.get(mode, [])
    text    = gainers_msg(tokens, chain, tf) if mode == "gainers" else losers_msg(tokens, chain, tf)
    await _reply(update, text, reply_markup=gainers_losers_kb(chain, tf, tokens, mode))


async def cb_gl_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts        = update.callback_query.data.split("_")
    mode, chain, tf = parts[1], parts[2], parts[3]
    ctx.user_data["gl_mode"] = mode
    data    = await get_gainers_losers(chain, tf)
    tokens  = data.get(mode, [])
    text    = gainers_msg(tokens, chain, tf) if mode == "gainers" else losers_msg(tokens, chain, tf)
    await _reply(update, text, reply_markup=gainers_losers_kb(chain, tf, tokens, mode))


# ── Token detail ─────────────────────────────────────────────

async def cb_token_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts         = update.callback_query.data.split("_")
    token_address = parts[1]
    chain         = parts[2]
    # We don't always have full token data, show address + risk button
    text = (
        f"🪙 <b>Token</b>\n\n"
        f"📋 <code>{token_address}</code>\n"
        f"🔗 Chain: <b>{chain.upper()}</b>\n\n"
        "Tap <b>Risk Check</b> to scan this token."
    )
    await _reply(update, text, reply_markup=token_detail_kb(token_address, chain))


# ── Risk check ───────────────────────────────────────────────

async def cb_risk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts         = update.callback_query.data.split("_")
    token_address = parts[1]
    chain         = parts[2]
    await _reply(update, "🔍 Scanning token security...")
    security      = await check_token_security(token_address, chain)
    score, label, flags = build_risk_score(security)
    text          = risk_msg(token_address, chain, security, score, label, flags)
    await _reply(update, text, reply_markup=risk_kb(token_address, chain))


# ── Top wallets ───────────────────────────────────────────────

async def cb_menu_wallets(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    await _reply(update, "🧠 Select chain:", reply_markup=chain_kb("tw"))


async def cb_tw_chain(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    chain = update.callback_query.data.split("_")[1]
    ctx.user_data["tw_chain"] = chain
    await _reply(update, f"📊 Select timeframe for {chain.upper()}:",
                 reply_markup=timeframe_kb("tw", chain))


async def cb_tw_tf(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts     = update.callback_query.data.split("_")
    chain, tf = parts[1], parts[2]
    mode      = ctx.user_data.get("tw_mode", "gainers")
    await _reply(update, "⏳ Loading top wallets...")
    data    = await get_top_wallets(chain, tf)
    wallets = data.get(mode, [])
    text    = top_wallets_msg(wallets, mode, chain, tf)
    await _reply(update, text, reply_markup=top_wallets_kb(wallets, mode, chain, tf))


async def cb_tw_switch(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts        = update.callback_query.data.split("_")
    mode, chain, tf = parts[1], parts[2], parts[3]
    ctx.user_data["tw_mode"] = mode
    data    = await get_top_wallets(chain, tf)
    wallets = data.get(mode, [])
    text    = top_wallets_msg(wallets, mode, chain, tf)
    await _reply(update, text, reply_markup=top_wallets_kb(wallets, mode, chain, tf))


async def cb_wallet_detail(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts   = update.callback_query.data.split("_")
    addr    = parts[2]
    chain   = parts[3]
    uid     = update.effective_user.id
    await _reply(update, "⏳ Loading wallet data...")
    pnl     = await get_wallet_pnl(addr, chain)
    tracked = await get_tracked_wallets(uid)
    is_tracked = any(t["wallet_address"] == addr for t in tracked)
    text    = wallet_detail_msg(addr, chain, pnl)
    await _reply(update, text, reply_markup=wallet_detail_kb(addr, chain, is_tracked))


# ── My wallet ────────────────────────────────────────────────

async def cb_menu_mywallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    uid     = update.effective_user.id
    evm_w   = await get_wallet_by_chain(uid, "evm")
    sol_w   = await get_wallet_by_chain(uid, "solana")
    evm_addr = evm_w["address"] if evm_w else "Not found"
    sol_addr = sol_w["address"] if sol_w else "Not found"
    await _reply(update, my_wallet_msg(evm_addr, sol_addr), reply_markup=my_wallet_kb())


async def cb_wallet_show(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    chain_type = update.callback_query.data.split("_")[-1]
    ctx.user_data["reveal_chain"] = chain_type
    ctx.user_data["reveal_action"] = "show"
    await _reply(update, password_prompt_msg())
    return STATE_REVEAL_PW


async def cb_wallet_seed(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts      = update.callback_query.data.split("_")
    chain_type = parts[-1] if len(parts) > 2 else "evm"
    ctx.user_data["reveal_chain"]  = chain_type
    ctx.user_data["reveal_action"] = "seed"
    await _reply(update, f"🔑 Enter your password to reveal {chain_type.upper()} seed:")
    return STATE_REVEAL_PW


async def cb_wallet_pk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts      = update.callback_query.data.split("_")
    chain_type = parts[-1] if len(parts) > 2 else "evm"
    ctx.user_data["reveal_chain"]  = chain_type
    ctx.user_data["reveal_action"] = "pk"
    await _reply(update, f"🔐 Enter your password to reveal {chain_type.upper()} private key:")
    return STATE_REVEAL_PW


async def handle_reveal_pw(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid        = update.effective_user.id
    pw         = update.message.text.strip()
    user       = await get_user(uid)
    chain_type = ctx.user_data.get("reveal_chain", "evm")
    action     = ctx.user_data.get("reveal_action", "seed")

    if not verify_password(pw, uid, user["password_hash"]):
        await update.message.reply_text("❌ Wrong password.")
        return ConversationHandler.END

    wallet = await get_wallet_by_chain(uid, chain_type)
    if not wallet:
        await update.message.reply_text("❌ Wallet not found.")
        return ConversationHandler.END

    if action == "seed":
        seed = reveal_wallet_seed(uid, wallet["encrypted_seed"])
        msg  = await update.message.reply_text(
            seed_reveal_msg(chain_type, seed), parse_mode="HTML"
        )
    else:
        pk  = reveal_wallet_pk(uid, wallet["encrypted_pk"])
        msg = await update.message.reply_text(
            pk_reveal_msg(chain_type, pk), parse_mode="HTML"
        )

    # auto-delete after 30s
    async def _delete():
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except Exception:
            pass
    asyncio.create_task(_delete())

    await update.message.reply_text("✅ Done. Message deletes in 30s.",
                                    reply_markup=my_wallet_kb())
    return ConversationHandler.END


# ── Track wallets ─────────────────────────────────────────────

async def cb_menu_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    uid     = update.effective_user.id
    tracked = await get_tracked_wallets(uid)
    await _reply(update, tracked_list_msg(tracked), reply_markup=tracked_list_kb(tracked))


async def cb_track_view(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr    = update.callback_query.data.replace("track_view_", "")
    uid     = update.effective_user.id
    tracked = await get_tracked_wallets(uid)
    wallet  = next((t for t in tracked if t["wallet_address"] == addr), None)
    if not wallet:
        await _reply(update, "❌ Wallet not found.")
        return
    await _reply(update, tracked_wallet_detail_msg(wallet),
                 reply_markup=tracked_wallet_kb(addr, wallet))


async def cb_track_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    parts = update.callback_query.data.split("_")
    addr  = parts[2]
    chain = parts[3]
    ctx.user_data["track_addr"]  = addr
    ctx.user_data["track_chain"] = chain
    await _reply(update, "🏷 Enter a label for this wallet (e.g. 'whale1'):")
    return STATE_TRACK_LABEL


async def handle_track_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    label = update.message.text.strip()[:30]
    addr  = ctx.user_data.get("track_addr", "")
    chain = ctx.user_data.get("track_chain", "sol")

    ok = await add_tracked_wallet(uid, addr, label, chain)
    if ok:
        await update.message.reply_text(
            f"✅ Wallet <b>{label}</b> added to tracking!\n"
            f"<code>{addr}</code>",
            parse_mode="HTML",
            reply_markup=main_menu_kb(),
        )
    else:
        await update.message.reply_text(
            "❌ Limit reached — you can track max 5 wallets.",
            reply_markup=main_menu_kb(),
        )
    return ConversationHandler.END


async def cb_track_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("track_remove_", "")
    uid  = update.effective_user.id
    await remove_tracked_wallet(uid, addr)
    tracked = await get_tracked_wallets(uid)
    await _reply(update, "✅ Wallet removed.\n\n" + tracked_list_msg(tracked),
                 reply_markup=tracked_list_kb(tracked))


async def cb_track_rename(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("track_rename_", "")
    ctx.user_data["rename_addr"] = addr
    await _reply(update, "✏️ Enter new label:")
    return STATE_RENAME_LABEL


async def handle_rename(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    label = update.message.text.strip()[:30]
    addr  = ctx.user_data.get("rename_addr", "")
    await update_tracked_wallet(uid, addr, label=label)
    await update.message.reply_text(f"✅ Renamed to <b>{label}</b>.",
                                    parse_mode="HTML", reply_markup=main_menu_kb())
    return ConversationHandler.END


# ── Auto-buy / Auto-sell ──────────────────────────────────────

async def cb_autobuy_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("autobuy_toggle_", "")
    ctx.user_data["autobuy_addr"] = addr
    ctx.user_data["auto_action"]  = "autobuy_toggle"
    await _reply(update, "🔐 Enter your password to toggle Auto-Buy:")
    return STATE_VERIFY_PW


async def cb_autosell_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("autosell_toggle_", "")
    ctx.user_data["autosell_addr"] = addr
    ctx.user_data["auto_action"]   = "autosell_toggle"
    await _reply(update, "🔐 Enter your password to toggle Auto-Sell:")
    return STATE_VERIFY_PW


async def cb_autobuy_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("autobuy_amount_", "")
    ctx.user_data["autobuy_addr"] = addr
    await _reply(update, "💵 How many USD per auto-buy? (e.g. 10):")
    return STATE_AUTOBUY_AMT


async def handle_autobuy_amt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    addr = ctx.user_data.get("autobuy_addr", "")
    try:
        amt = float(update.message.text.strip())
        await update_tracked_wallet(uid, addr, autobuy_amount_usd=amt)
        await update.message.reply_text(f"✅ Auto-buy amount set to <b>${amt:.2f}</b>.",
                                        parse_mode="HTML", reply_markup=main_menu_kb())
    except ValueError:
        await update.message.reply_text("❌ Invalid amount.", reply_markup=main_menu_kb())
    return ConversationHandler.END


async def cb_autosell_pct(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    addr = update.callback_query.data.replace("autosell_pct_", "")
    ctx.user_data["autosell_addr"] = addr
    await _reply(update, "📊 What % of your holdings to sell? (e.g. 50 for 50%):")
    return STATE_AUTOSELL_PCT


async def handle_autosell_pct(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    addr = ctx.user_data.get("autosell_addr", "")
    try:
        pct = float(update.message.text.strip())
        pct = max(1.0, min(100.0, pct))
        await update_tracked_wallet(uid, addr, autosell_percentage=pct)
        await update.message.reply_text(f"✅ Auto-sell set to <b>{pct:.0f}%</b> of holdings.",
                                        parse_mode="HTML", reply_markup=main_menu_kb())
    except ValueError:
        await update.message.reply_text("❌ Invalid percentage.", reply_markup=main_menu_kb())
    return ConversationHandler.END


async def handle_verify_pw(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid    = update.effective_user.id
    pw     = update.message.text.strip()
    user   = await get_user(uid)
    action = ctx.user_data.get("auto_action", "")

    if not verify_password(pw, uid, user["password_hash"]):
        await update.message.reply_text("❌ Wrong password.")
        return ConversationHandler.END

    if action == "autobuy_toggle":
        addr    = ctx.user_data.get("autobuy_addr", "")
        tracked = await get_tracked_wallets(uid)
        wallet  = next((t for t in tracked if t["wallet_address"] == addr), None)
        if wallet:
            new_val = 0 if wallet.get("autobuy_enabled") else 1
            await update_tracked_wallet(uid, addr, autobuy_enabled=new_val)
            state = "🟢 ON" if new_val else "⚪ OFF"
            await update.message.reply_text(f"✅ Auto-Buy is now <b>{state}</b>.",
                                            parse_mode="HTML", reply_markup=main_menu_kb())

    elif action == "autosell_toggle":
        addr    = ctx.user_data.get("autosell_addr", "")
        tracked = await get_tracked_wallets(uid)
        wallet  = next((t for t in tracked if t["wallet_address"] == addr), None)
        if wallet:
            new_val = 0 if wallet.get("autosell_enabled") else 1
            await update_tracked_wallet(uid, addr, autosell_enabled=new_val)
            state = "🟢 ON" if new_val else "⚪ OFF"
            await update.message.reply_text(f"✅ Auto-Sell is now <b>{state}</b>.",
                                            parse_mode="HTML", reply_markup=main_menu_kb())

    return ConversationHandler.END


# ── Search wallet ─────────────────────────────────────────────

async def cb_menu_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    await _reply(update, "🔍 Enter a wallet address to search:")
    return STATE_SEARCH_ADDR


async def handle_search_addr(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    addr = update.message.text.strip()

    # detect chain from address format
    if len(addr) in (32, 44) and not addr.startswith("0x"):
        chain = "sol"
    else:
        chain = "eth"

    tracked    = await get_tracked_wallets(uid)
    is_tracked = any(t["wallet_address"] == addr for t in tracked)
    pnl        = await get_wallet_pnl(addr, chain)
    text       = wallet_detail_msg(addr, chain, pnl)
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=search_result_kb(addr, chain, is_tracked),
    )
    return ConversationHandler.END


# ── Trade history ─────────────────────────────────────────────

async def cb_menu_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    uid    = update.effective_user.id
    trades = await get_trade_history(uid, 20)
    from utils.keyboards import mk, btn
    kb = mk([btn("🔙 Back", "home")])
    await _reply(update, trade_history_msg(trades), reply_markup=kb)


# ── Settings ──────────────────────────────────────────────────

async def cb_menu_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    await _reply(update, "⚙️ <b>Settings</b>", reply_markup=settings_kb())


async def cb_settings_pw(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update)
    ctx.user_data["auto_action"] = "change_pw_verify"
    await _reply(update, "🔐 Enter your current password:")
    return STATE_VERIFY_PW


async def cb_already_tracked(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, "✅ Already in your tracking list!")


# ── Copy address ──────────────────────────────────────────────

async def cb_copy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    addr = update.callback_query.data.replace("copy_", "")
    await update.callback_query.answer(f"Address: {addr}", show_alert=True)


# ── Conversation handler builder ──────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(cb_menu_search,      pattern="^menu_search$"),
            CallbackQueryHandler(cb_wallet_seed,      pattern="^wallet_seed"),
            CallbackQueryHandler(cb_wallet_pk,        pattern="^wallet_pk"),
            CallbackQueryHandler(cb_wallet_show,      pattern="^wallet_show"),
            CallbackQueryHandler(cb_autobuy_toggle,   pattern="^autobuy_toggle_"),
            CallbackQueryHandler(cb_autosell_toggle,  pattern="^autosell_toggle_"),
            CallbackQueryHandler(cb_autobuy_amount,   pattern="^autobuy_amount_"),
            CallbackQueryHandler(cb_autosell_pct,     pattern="^autosell_pct_"),
            CallbackQueryHandler(cb_track_add,        pattern="^track_add_"),
            CallbackQueryHandler(cb_track_rename,     pattern="^track_rename_"),
            CallbackQueryHandler(cb_settings_pw,      pattern="^settings_pw$"),
        ],
        states={
            STATE_SET_PW:      [MessageHandler(filters.TEXT & ~filters.COMMAND, set_password)],
            STATE_VERIFY_PW:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_verify_pw)],
            STATE_REVEAL_PW:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reveal_pw)],
            STATE_SEARCH_ADDR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_addr)],
            STATE_TRACK_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_track_label)],
            STATE_RENAME_LABEL:[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename)],
            STATE_AUTOBUY_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_autobuy_amt)],
            STATE_AUTOSELL_PCT:[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_autosell_pct)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        per_user=True,
        per_chat=True,
    )


def register_callbacks(app) -> None:
    """Register all non-conversation callback handlers."""
    patterns = [
        ("^home$",              cb_home),
        ("^menu_pairs$",        cb_menu_pairs),
        ("^pairs_",             cb_pairs_chain),
        ("^menu_gainers$",      cb_menu_gainers),
        ("^gl_[a-z]+_[a-z]+$", cb_gl_chain),
        ("^gl_[a-z]+_[a-z]+_", cb_gl_tf),
        ("^gl_(gainers|losers)_", cb_gl_switch),
        ("^token_",             cb_token_detail),
        ("^risk_",              cb_risk),
        ("^menu_wallets$",      cb_menu_wallets),
        ("^tw_[a-z]+_[a-z]+$", cb_tw_chain),
        ("^tw_[a-z]+_[a-z]+_", cb_tw_tf),
        ("^tw_(gainers|losers)_", cb_tw_switch),
        ("^wallet_detail_",     cb_wallet_detail),
        ("^menu_mywallet$",     cb_menu_mywallet),
        ("^menu_track$",        cb_menu_track),
        ("^track_view_",        cb_track_view),
        ("^track_remove_",      cb_track_remove),
        ("^menu_history$",      cb_menu_history),
        ("^menu_settings$",     cb_menu_settings),
        ("^already_tracked_",   cb_already_tracked),
        ("^copy_",              cb_copy),
    ]
    for pattern, handler in patterns:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
