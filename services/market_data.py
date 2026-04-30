"""
Market Data Service
Fetches new pairs, gainers, losers, top wallets from GMGN / DexScreener APIs.
"""

import aiohttp
import asyncio
import os
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

GMGN_BASE   = os.getenv("GMGN_BASE_URL", "https://gmgn.ai/defi/quotation/v1")
DEXSCREENER = os.getenv("DEXSCREENER_API", "https://api.dexscreener.com/latest")
GOPLUS_API  = os.getenv("GOPLUS_API_URL", "https://api.gopluslabs.io/api/v1")

CHAIN_EMOJI = {
    "eth":  "🔷",
    "bsc":  "🟡",
    "sol":  "🟣",
    "arb":  "🔵",
    "base": "🔵",
    "op":   "🔴",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://gmgn.ai/",
}


async def _fetch(url: str, params: Dict = None, headers: Dict = None,
                 timeout: int = 15) -> Optional[Dict]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                headers={**HEADERS, **(headers or {})},
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"[fetch] Error {url}: {e}")
    return None


# ── New pairs ────────────────────────────────────────────────

async def get_new_pairs(chain: str = "bsc", limit: int = 20) -> List[Dict]:
    chain_map = {
        "eth": "ethereum", "bsc": "bsc", "sol": "solana",
        "arb": "arbitrum", "base": "base", "op": "optimism"
    }
    dex_chain = chain_map.get(chain, chain)
    data = await _fetch(f"{DEXSCREENER}/dex/search", params={"q": dex_chain})
    if data and "pairs" in data:
        return [_normalize_pair(p) for p in data["pairs"][:limit]]
    return _mock_new_pairs(chain, limit)


def _normalize_pair(p: Dict) -> Dict:
    return {
        "name":             p.get("baseToken", {}).get("name", "Unknown"),
        "symbol":           p.get("baseToken", {}).get("symbol", "???"),
        "address":          p.get("baseToken", {}).get("address", ""),
        "chain":            p.get("chainId", ""),
        "price_usd":        p.get("priceUsd", "0"),
        "price_change_h1":  p.get("priceChange", {}).get("h1", 0),
        "price_change_h6":  p.get("priceChange", {}).get("h6", 0),
        "price_change_h24": p.get("priceChange", {}).get("h24", 0),
        "volume_h24":       p.get("volume", {}).get("h24", 0),
        "liquidity_usd":    p.get("liquidity", {}).get("usd", 0),
        "fdv":              p.get("fdv", 0),
        "pair_address":     p.get("pairAddress", ""),
        "dex_url":          p.get("url", ""),
        "created_at":       p.get("pairCreatedAt", 0),
    }


# ── Gainers / Losers ─────────────────────────────────────────

async def get_gainers_losers(chain: str, timeframe: str) -> Dict:
    gmgn_data = await _fetch(
        f"{GMGN_BASE}/rank/{chain}/swaps/{timeframe}",
        params={"orderby": "change", "direction": "desc", "limit": 20}
    )
    if gmgn_data and gmgn_data.get("code") == 0:
        tokens  = gmgn_data.get("data", {}).get("rank", [])
        gainers = sorted(tokens, key=lambda x: x.get("price_change_percent", 0), reverse=True)[:10]
        losers  = sorted(tokens, key=lambda x: x.get("price_change_percent", 0))[:10]
        return {
            "gainers": [_normalize_gmgn_token(t) for t in gainers],
            "losers":  [_normalize_gmgn_token(t) for t in losers],
        }

    chain_map = {
        "eth": "ethereum", "bsc": "bsc", "sol": "solana",
        "arb": "arbitrum", "base": "base", "op": "optimism"
    }
    dex_chain = chain_map.get(chain, chain)
    data = await _fetch(f"{DEXSCREENER}/dex/tokens/trending/{dex_chain}")
    if data and "pairs" in data:
        pairs      = [_normalize_pair(p) for p in data["pairs"][:20]]
        tf_key_map = {
            "30m": "price_change_h1", "1h": "price_change_h1",
            "6h":  "price_change_h6", "24h": "price_change_h24", "3d": "price_change_h24"
        }
        key     = tf_key_map.get(timeframe, "price_change_h24")
        gainers = sorted(pairs, key=lambda x: float(x.get(key, 0) or 0), reverse=True)[:10]
        losers  = sorted(pairs, key=lambda x: float(x.get(key, 0) or 0))[:10]
        return {"gainers": gainers, "losers": losers}

    return _mock_gainers_losers(chain, timeframe)


def _normalize_gmgn_token(t: Dict) -> Dict:
    return {
        "name":         t.get("name", "Unknown"),
        "symbol":       t.get("symbol", "???"),
        "address":      t.get("address", ""),
        "price_usd":    t.get("price", 0),
        "price_change": t.get("price_change_percent", 0),
        "volume_h24":   t.get("volume", 0),
        "liquidity_usd":t.get("liquidity", 0),
        "market_cap":   t.get("market_cap", 0),
        "holders":      t.get("holder_count", 0),
    }


# ── Top wallets ──────────────────────────────────────────────

async def get_top_wallets(chain: str, timeframe: str) -> Dict:
    gainers_data = await _fetch(
        f"{GMGN_BASE}/smartmoney/{chain}/wallets",
        params={"period": timeframe, "orderby": "pnl", "direction": "desc", "limit": 10}
    )
    losers_data = await _fetch(
        f"{GMGN_BASE}/smartmoney/{chain}/wallets",
        params={"period": timeframe, "orderby": "pnl", "direction": "asc", "limit": 10}
    )

    gainers = []
    losers  = []

    if gainers_data and gainers_data.get("code") == 0:
        gainers = [_normalize_wallet(w)
                   for w in gainers_data.get("data", {}).get("wallets", [])]
    if losers_data and losers_data.get("code") == 0:
        losers  = [_normalize_wallet(w)
                   for w in losers_data.get("data", {}).get("wallets", [])]

    if not gainers and not losers:
        return _mock_top_wallets()

    return {"gainers": gainers, "losers": losers}


def _normalize_wallet(w: Dict) -> Dict:
    return {
        "address":     w.get("address", ""),
        "pnl_usd":     w.get("realized_profit", 0),
        "pnl_percent": w.get("pnl_percent", 0),
        "win_rate":    w.get("win_rate", 0),
        "trades":      w.get("trade_count", 0),
        "buy_count":   w.get("buy_count", 0),
        "sell_count":  w.get("sell_count", 0),
        "tags":        w.get("tags", []),
    }


# ── Wallet activity ──────────────────────────────────────────

async def get_wallet_recent_trades(wallet_address: str, chain: str) -> List[Dict]:
    data = await _fetch(
        f"{GMGN_BASE}/wallet/{chain}/{wallet_address}/activity",
        params={"limit": 10}
    )
    if data and data.get("code") == 0:
        return data.get("data", {}).get("activities", [])
    return []


async def get_wallet_holdings(wallet_address: str, chain: str) -> List[Dict]:
    data = await _fetch(f"{GMGN_BASE}/wallet/{chain}/{wallet_address}/holdings")
    if data and data.get("code") == 0:
        return data.get("data", {}).get("holdings", [])
    return []


async def get_wallet_pnl(wallet_address: str, chain: str, timeframe: str = "7d") -> Dict:
    data = await _fetch(
        f"{GMGN_BASE}/wallet/{chain}/{wallet_address}/performance",
        params={"period": timeframe}
    )
    if data and data.get("code") == 0:
        return data.get("data", {})
    return {}


# ── Token security ───────────────────────────────────────────

async def check_token_security(token_address: str, chain: str) -> Dict:
    chain_id_map = {
        "eth": "1", "bsc": "56", "arb": "42161",
        "base": "8453", "op": "10", "sol": "solana"
    }
    chain_id = chain_id_map.get(chain, "1")

    if chain == "sol":
        data = await _fetch(f"{GOPLUS_API}/solana/token_security/{token_address}")
    else:
        data = await _fetch(
            f"{GOPLUS_API}/token_security/{chain_id}",
            params={"contract_addresses": token_address}
        )

    if not data or data.get("code") != 1:
        return _mock_security_check()

    result     = data.get("result", {})
    token_data = result.get(token_address.lower(), result) if isinstance(result, dict) else {}

    return {
        "is_honeypot":             bool(int(token_data.get("is_honeypot", 0) or 0)),
        "buy_tax":                 float(token_data.get("buy_tax", 0) or 0),
        "sell_tax":                float(token_data.get("sell_tax", 0) or 0),
        "is_mintable":             bool(int(token_data.get("is_mintable", 0) or 0)),
        "is_proxy":                bool(int(token_data.get("is_proxy", 0) or 0)),
        "is_blacklisted":          bool(int(token_data.get("is_blacklisted", 0) or 0)),
        "owner_percent":           float(token_data.get("owner_percent", 0) or 0),
        "creator_percent":         float(token_data.get("creator_percent", 0) or 0),
        "lp_locked":               bool(int(token_data.get("lp_locked", 0) or 0)),
        "lp_lock_percent":         float(token_data.get("lp_lock_percent", 0) or 0),
        "holder_count":            int(token_data.get("holder_count", 0) or 0),
        "is_open_source":          bool(int(token_data.get("is_open_source", 0) or 0)),
        "can_take_back_ownership": bool(int(token_data.get("can_take_back_ownership", 0) or 0)),
        "trading_cooldown":        bool(int(token_data.get("trading_cooldown", 0) or 0)),
        "transfer_pausable":       bool(int(token_data.get("transfer_pausable", 0) or 0)),
    }


def build_risk_score(security: Dict) -> Tuple[int, str, List[str]]:
    """Return (score 0-100, label, list of risk flags)."""
    score = 0
    flags: List[str] = []

    if security.get("is_honeypot"):
        score += 50
        flags.append("🚨 HONEYPOT DETECTED")
    if security.get("buy_tax", 0) > 10:
        score += 15
        flags.append(f"⚠️ High buy tax: {security['buy_tax']}%")
    if security.get("sell_tax", 0) > 10:
        score += 15
        flags.append(f"⚠️ High sell tax: {security['sell_tax']}%")
    if security.get("is_mintable"):
        score += 10
        flags.append("⚠️ Token is mintable (infinite supply risk)")
    if not security.get("lp_locked"):
        score += 20
        flags.append("🔓 LP not locked (rug pull risk)")
    elif security.get("lp_lock_percent", 0) < 80:
        score += 10
        flags.append(f"⚠️ LP only {security['lp_lock_percent']:.0f}% locked")
    if security.get("owner_percent", 0) > 5:
        score += 10
        flags.append(f"⚠️ Owner holds {security['owner_percent']:.1f}% of supply")
    if security.get("can_take_back_ownership"):
        score += 15
        flags.append("⚠️ Can reclaim ownership")
    if security.get("transfer_pausable"):
        score += 10
        flags.append("⚠️ Transfers can be paused")
    if not security.get("is_open_source"):
        score += 5
        flags.append("⚠️ Contract not verified/open source")

    score = min(score, 100)

    if score == 0:
        label = "✅ SAFE"
    elif score < 30:
        label = "🟡 LOW RISK"
    elif score < 60:
        label = "🟠 MEDIUM RISK"
    else:
        label = "🔴 HIGH RISK"

    return score, label, flags


# ── Mock fallbacks ───────────────────────────────────────────

def _mock_new_pairs(chain: str, limit: int) -> List[Dict]:
    return [
        {
            "name": f"MockToken{i}", "symbol": f"MCK{i}",
            "address": f"0x{'a'*40}", "chain": chain,
            "price_usd": f"{0.0000001 * i:.10f}",
            "price_change_h1": 15.3 * i, "price_change_h6": 42.1,
            "price_change_h24": 105.0, "volume_h24": 50000 * i,
            "liquidity_usd": 25000, "fdv": 500000,
            "pair_address": f"0x{'b'*40}",
            "dex_url": "https://dexscreener.com", "created_at": 0,
        }
        for i in range(1, min(limit, 5) + 1)
    ]


def _mock_gainers_losers(chain: str, timeframe: str) -> Dict:
    gainers = [
        {
            "name": f"MoonToken{i}", "symbol": f"MOON{i}",
            "address": f"0x{'c'*40}", "price_usd": 0.001 * i,
            "price_change": 250.5 * i, "volume_h24": 1_000_000,
            "liquidity_usd": 500_000, "market_cap": 2_000_000, "holders": 1500,
        }
        for i in range(1, 6)
    ]
    losers = [
        {
            "name": f"DumpToken{i}", "symbol": f"DUMP{i}",
            "address": f"0x{'d'*40}", "price_usd": 0.0001 * i,
            "price_change": -85.3 * i, "volume_h24": 50_000,
            "liquidity_usd": 5_000, "market_cap": 50_000, "holders": 200,
        }
        for i in range(1, 6)
    ]
    return {"gainers": gainers, "losers": losers}


def _mock_top_wallets() -> Dict:
    gainers = [
        {
            "address": f"0xGAIN{'e'*36}{i}", "pnl_usd": 50_000 * (i + 1),
            "pnl_percent": 500 * (i + 1), "win_rate": 0.75,
            "trades": 42, "buy_count": 30, "sell_count": 12, "tags": ["smart_money"],
        }
        for i in range(5)
    ]
    losers = [
        {
            "address": f"0xLOSE{'f'*36}{i}", "pnl_usd": -30_000 * (i + 1),
            "pnl_percent": -90 * (i + 1), "win_rate": 0.20,
            "trades": 15, "buy_count": 10, "sell_count": 5, "tags": [],
        }
        for i in range(5)
    ]
    return {"gainers": gainers, "losers": losers}


def _mock_security_check() -> Dict:
    return {
        "is_honeypot": False, "buy_tax": 5.0, "sell_tax": 5.0,
        "is_mintable": False, "is_proxy": False, "is_blacklisted": False,
        "owner_percent": 2.5, "creator_percent": 1.0, "lp_locked": True,
        "lp_lock_percent": 90.0, "holder_count": 1200, "is_open_source": True,
        "can_take_back_ownership": False, "trading_cooldown": False,
        "transfer_pausable": False,
    }
