"""
Wallet service — EVM + Solana wallet generation with Fernet encryption.
"""

import os
import hashlib
import hmac
import secrets
import base64
from typing import Dict

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

MASTER_KEY = os.getenv("MASTER_ENCRYPTION_KEY", Fernet.generate_key().decode())

# ── Key derivation ───────────────────────────────────────────

def _derive_fernet(user_id: int) -> Fernet:
    master = MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY
    salt   = f"memecoin_bot_user_{user_id}".encode()
    kdf    = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    key    = base64.urlsafe_b64encode(kdf.derive(master))
    return Fernet(key)


def encrypt_data(user_id: int, plaintext: str) -> str:
    return _derive_fernet(user_id).encrypt(plaintext.encode()).decode()


def decrypt_data(user_id: int, ciphertext: str) -> str:
    return _derive_fernet(user_id).decrypt(ciphertext.encode()).decode()


# ── Password hashing ─────────────────────────────────────────

def hash_password(password: str, user_id: int) -> str:
    salt = f"pw_salt_{user_id}_memecoin".encode()
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return dk.hex()


def verify_password(password: str, user_id: int, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_password(password, user_id), stored_hash)


# ── Mnemonic ─────────────────────────────────────────────────

WORDLIST = [
    "abandon","ability","able","about","above","absent","absorb","abstract","absurd","abuse",
    "access","accident","account","accuse","achieve","acid","acoustic","acquire","across","act",
    "action","actor","actress","actual","adapt","add","addict","address","adjust","admit",
    "adult","advance","advice","aerobic","afford","afraid","again","age","agent","agree",
    "ahead","aim","air","airport","aisle","alarm","album","alcohol","alert","alien",
    "all","alley","allow","almost","alone","alpha","already","also","alter","always",
    "amateur","amazing","among","amount","amused","analyst","anchor","ancient","anger","angle",
    "angry","animal","ankle","announce","annual","another","answer","antenna","antique","anxiety",
    "any","apart","apology","appear","apple","approve","april","arch","arctic","area",
    "arena","argue","arm","armor","army","around","arrange","arrest","arrive","arrow",
    "art","artefact","artist","artwork","ask","aspect","assault","asset","assist","assume",
    "asthma","athlete","atom","attack","attend","attitude","attract","auction","audit","august",
    "aunt","author","auto","autumn","average","avocado","avoid","awake","aware","away",
    "awesome","awful","awkward","axis","baby","balance","bamboo","banana","banner","barely",
    "bargain","barrel","base","basic","basket","battle","beach","bean","beauty","because",
    "become","beef","before","begin","behave","behind","believe","below","belt","bench",
    "benefit","best","betray","better","between","beyond","bicycle","bind","biology","bird",
    "birth","bitter","black","blade","blame","blanket","blast","bleak","bless","blind",
    "blood","blossom","blouse","blue","blur","blush","board","boat","body","boil",
    "bomb","bone","book","boost","border","boring","borrow","boss","bottom","bounce",
    "box","boy","bracket","brain","brand","brave","bread","breeze","brick","bridge",
]


def generate_mnemonic(num_words: int = 12) -> str:
    return " ".join(WORDLIST[secrets.randbelow(len(WORDLIST))] for _ in range(num_words))


def _mnemonic_to_seed(mnemonic: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), b"mnemonic", 2048, 64)


# ── EVM wallet ───────────────────────────────────────────────

def generate_evm_wallet(mnemonic: str) -> Dict[str, str]:
    try:
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(mnemonic)
        return {"address": acct.address, "private_key": acct.key.hex(), "mnemonic": mnemonic}
    except Exception:
        seed        = _mnemonic_to_seed(mnemonic)
        private_key = seed[:32].hex()
        addr_bytes  = hashlib.sha256(seed[:32]).digest()[-20:]
        return {
            "address":     "0x" + addr_bytes.hex(),
            "private_key": "0x" + private_key,
            "mnemonic":    mnemonic,
        }


# ── Solana wallet ────────────────────────────────────────────

_B58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    count = sum(1 for b in data if b == 0)
    num   = int.from_bytes(data, "big")
    res   = []
    while num:
        num, rem = divmod(num, 58)
        res.append(_B58[rem:rem+1])
    res.extend([_B58[0:1]] * count)
    return b"".join(reversed(res)).decode()


def generate_solana_wallet(mnemonic: str) -> Dict[str, str]:
    seed = _mnemonic_to_seed(mnemonic)[:32]
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        pk       = Ed25519PrivateKey.from_private_bytes(seed)
        pub      = pk.public_key().public_bytes_raw()
        full_kp  = seed + pub
        return {
            "address":     _b58encode(pub),
            "private_key": _b58encode(full_kp),
            "mnemonic":    mnemonic,
        }
    except Exception:
        pub = hashlib.sha256(seed).digest()
        return {
            "address":     _b58encode(pub),
            "private_key": _b58encode(seed + pub),
            "mnemonic":    mnemonic,
        }


# ── Main entry ───────────────────────────────────────────────

def create_user_wallets(user_id: int) -> Dict:
    mnemonic = generate_mnemonic(12)
    evm      = generate_evm_wallet(mnemonic)
    sol      = generate_solana_wallet(mnemonic)
    return {
        "evm": {
            "address":        evm["address"],
            "encrypted_seed": encrypt_data(user_id, evm["mnemonic"]),
            "encrypted_pk":   encrypt_data(user_id, evm["private_key"]),
        },
        "solana": {
            "address":        sol["address"],
            "encrypted_seed": encrypt_data(user_id, sol["mnemonic"]),
            "encrypted_pk":   encrypt_data(user_id, sol["private_key"]),
        },
    }


def reveal_wallet_seed(user_id: int, encrypted_seed: str) -> str:
    return decrypt_data(user_id, encrypted_seed)


def reveal_wallet_pk(user_id: int, encrypted_pk: str) -> str:
    return decrypt_data(user_id, encrypted_pk)
