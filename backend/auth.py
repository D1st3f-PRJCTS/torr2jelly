import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from typing import Optional, List, Dict, Any
from fastapi import Header, HTTPException, status
from pydantic import BaseModel

class User(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"  # "admin" or "user"

class UserChangePassword(BaseModel):
    current_password: str
    new_password: str

class UserResetPassword(BaseModel):
    new_password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SetupRequest(BaseModel):
    username: str
    password: str

# Database initialization
def get_db_path() -> str:
    from .config import CONFIG_FILE_PATH
    config_dir = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(config_dir, exist_ok=True)
    return os.getenv("USERS_DB_PATH", os.path.join(config_dir, "users.db"))

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    finally:
        conn.close()

# Password Hashing using PBKDF2-HMAC-SHA256 (100,000 iterations)
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000
    ).hex()
    return hashed, salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    hashed, _ = hash_password(password, salt)
    return hmac.compare_digest(hashed, password_hash)

# Base64URL helpers for standard JWT tokens
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding and padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("utf-8"))

def create_access_token(username: str, role: str, secret_key: str, expires_in_seconds: int = 7 * 86400) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in_seconds
    }
    
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_access_token(token: str, secret_key: str) -> Optional[Dict[str, Any]]:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Check expiration
        if "exp" in payload and int(time.time()) > payload["exp"]:
            return None
        return payload
    except Exception:
        return None

# User Database Operations
def count_users() -> int:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]
    finally:
        conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, salt, role, created_at FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()

def create_user(username: str, password: str, role: str = "user") -> User:
    username = username.strip()
    if not username:
        raise ValueError("Ім'я користувача не може бути порожнім")
    if len(password) < 4:
        raise ValueError("Пароль повинен містити щонайменше 4 символи")
    if role not in ("admin", "user"):
        raise ValueError("Неприпустима роль користувача")
    
    password_hash, salt = hash_password(password)
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, role)
            )
            user_id = cur.lastrowid
            return User(id=user_id, username=username, role=role)
    except sqlite3.IntegrityError:
        raise ValueError(f"Користувач з іменем '{username}' вже існує")
    finally:
        conn.close()

def list_users() -> List[User]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id ASC")
        return [User(**dict(row)) for row in cur.fetchall()]
    finally:
        conn.close()

def delete_user(username: str) -> bool:
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE username = ?", (username,))
            return cur.rowcount > 0
    finally:
        conn.close()

def update_user_password(username: str, new_password: str) -> bool:
    if len(new_password) < 4:
        raise ValueError("Пароль повинен містити щонайменше 4 символи")
    password_hash, salt = hash_password(new_password)
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
                (password_hash, salt, username)
            )
            return cur.rowcount > 0
    finally:
        conn.close()

def seed_initial_admin_if_needed() -> None:
    init_db()
    if count_users() == 0:
        env_user = os.getenv("INITIAL_ADMIN_USERNAME")
        env_pass = os.getenv("INITIAL_ADMIN_PASSWORD")
        if env_user and env_pass:
            create_user(env_user, env_pass, role="admin")
            print(f"Created initial admin user from env: {env_user}")
