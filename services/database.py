"""
Database service — async SQLite via aiosqlite.
All sensitive data (seeds, private keys) stored encrypted.
"""

import aiosqlite
import os
from typing import Optional, List, Dict

DB_PATH = os.getenv("DATABASE_PATH", "data/bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now')),
    is_active     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS wallets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    chain_type     TEXT NOT NULL,
    address        TEXT NOT NULL,
    encrypted_seed TEXT NOT NULL,
    encrypted_pk   TEXT NOT NULL,
    created_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS tracked_wallets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    wallet_address      TEXT NOT NULL,
    label               TEXT,
    chain               TEXT NOT NULL,
    autobuy_enabled     INTEGER DEFAULT 0,
    autosell_enabled    INTEGER DEFAULT 0,
    autobuy_amount_usd  REAL DEFAULT 0,
    autosell_percentage REAL DEFAULT 100,
    added_at            TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE(user_id, wallet_address)
);

CREATE TABLE IF NOT EXISTS trade_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    action        TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_symbol  TEXT,
    chain         TEXT NOT NULL,
    amount_usd    REAL,
    amount_tokens REAL,
    tx_hash       TEXT,
    status        TEXT DEFAULT 'pending',
    triggered_by  TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    message    TEXT NOT NULL,
    read       INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_tracked_user   ON tracked_wallets(user_id);
CREATE INDEX IF NOT EXISTS idx_trade_user     ON trade_history(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_user     ON notifications(user_id, read);
"""


async def _conn() -> aiosqlite.Connection:
    path = DB_PATH
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await _conn()
    await db.executescript(SCHEMA)
    await db.commit()
    await db.close()


# ── Users ────────────────────────────────────────────────────

async def create_user(user_id: int, username: str, password_hash: str) -> bool:
    db = await _conn()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, password_hash) VALUES (?,?,?)",
            (user_id, username, password_hash)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_user(user_id: int) -> Optional[Dict]:
    db = await _conn()
    try:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def user_exists(user_id: int) -> bool:
    return (await get_user(user_id)) is not None


async def update_password(user_id: int, new_hash: str):
    db = await _conn()
    try:
        await db.execute(
            "UPDATE users SET password_hash=? WHERE user_id=?", (new_hash, user_id)
        )
        await db.commit()
    finally:
        await db.close()


# ── Wallets ──────────────────────────────────────────────────

async def save_wallet(user_id: int, chain_type: str, address: str,
                      encrypted_seed: str, encrypted_pk: str):
    db = await _conn()
    try:
        await db.execute(
            "INSERT INTO wallets (user_id,chain_type,address,encrypted_seed,encrypted_pk) "
            "VALUES (?,?,?,?,?)",
            (user_id, chain_type, address, encrypted_seed, encrypted_pk)
        )
        await db.commit()
    finally:
        await db.close()


async def get_wallets(user_id: int) -> List[Dict]:
    db = await _conn()
    try:
        cur  = await db.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_wallet_by_chain(user_id: int, chain_type: str) -> Optional[Dict]:
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT * FROM wallets WHERE user_id=? AND chain_type=?",
            (user_id, chain_type)
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# ── Tracked wallets ──────────────────────────────────────────

async def add_tracked_wallet(user_id: int, wallet_address: str,
                              label: str, chain: str) -> bool:
    db = await _conn()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) as cnt FROM tracked_wallets WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if row["cnt"] >= 5:
            return False
        await db.execute(
            "INSERT OR REPLACE INTO tracked_wallets "
            "(user_id,wallet_address,label,chain) VALUES (?,?,?,?)",
            (user_id, wallet_address, label, chain)
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_tracked_wallets(user_id: int) -> List[Dict]:
    db = await _conn()
    try:
        cur  = await db.execute(
            "SELECT * FROM tracked_wallets WHERE user_id=?", (user_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def remove_tracked_wallet(user_id: int, wallet_address: str):
    db = await _conn()
    try:
        await db.execute(
            "DELETE FROM tracked_wallets WHERE user_id=? AND wallet_address=?",
            (user_id, wallet_address)
        )
        await db.commit()
    finally:
        await db.close()


async def update_tracked_wallet(user_id: int, wallet_address: str, **kwargs):
    if not kwargs:
        return
    db = await _conn()
    try:
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id, wallet_address]
        await db.execute(
            f"UPDATE tracked_wallets SET {sets} WHERE user_id=? AND wallet_address=?",
            vals
        )
        await db.commit()
    finally:
        await db.close()


async def get_all_tracked_wallets() -> List[Dict]:
    db = await _conn()
    try:
        cur  = await db.execute("SELECT * FROM tracked_wallets")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Trade history ────────────────────────────────────────────

async def log_trade(user_id: int, action: str, token_address: str,
                    token_symbol: str, chain: str, amount_usd: float,
                    amount_tokens: float, tx_hash: str, status: str,
                    triggered_by: str = "manual"):
    db = await _conn()
    try:
        await db.execute(
            "INSERT INTO trade_history "
            "(user_id,action,token_address,token_symbol,chain,amount_usd,"
            "amount_tokens,tx_hash,status,triggered_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, action, token_address, token_symbol, chain,
             amount_usd, amount_tokens, tx_hash, status, triggered_by)
        )
        await db.commit()
    finally:
        await db.close()


async def get_trade_history(user_id: int, limit: int = 20) -> List[Dict]:
    db = await _conn()
    try:
        cur  = await db.execute(
            "SELECT * FROM trade_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# ── Notifications ────────────────────────────────────────────

async def add_notification(user_id: int, message: str):
    db = await _conn()
    try:
        await db.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?,?)",
            (user_id, message)
        )
        await db.commit()
    finally:
        await db.close()
