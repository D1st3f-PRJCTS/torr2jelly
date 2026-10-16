import sqlite3
import os
from typing import Optional, Dict, Any

def get_db_path() -> str:
    from .config import CONFIG_FILE_PATH
    config_dir = os.path.dirname(CONFIG_FILE_PATH)
    os.makedirs(config_dir, exist_ok=True)
    return os.getenv("USERS_DB_PATH", os.path.join(config_dir, "users.db"))

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_torrent_store() -> None:
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS torrent_meta (
                    hash TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    clean_title TEXT,
                    category TEXT,
                    poster TEXT,
                    folder_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    finally:
        conn.close()

def save_torrent_meta(
    hash_id: str,
    title: Optional[str] = None,
    clean_title: Optional[str] = None,
    category: Optional[str] = None,
    poster: Optional[str] = None,
    folder_name: Optional[str] = None
) -> None:
    if not hash_id:
        return
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            existing = get_torrent_meta(hash_id)
            final_title = title or (existing.get("title") if existing else hash_id)
            final_clean = clean_title or (existing.get("clean_title") if existing else None)
            cur.execute("""
                INSERT INTO torrent_meta (hash, title, clean_title, category, poster, folder_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(hash) DO UPDATE SET
                    title = COALESCE(excluded.title, torrent_meta.title),
                    clean_title = COALESCE(excluded.clean_title, torrent_meta.clean_title),
                    category = COALESCE(excluded.category, torrent_meta.category),
                    poster = COALESCE(excluded.poster, torrent_meta.poster),
                    folder_name = COALESCE(excluded.folder_name, torrent_meta.folder_name),
                    updated_at = CURRENT_TIMESTAMP
            """, (hash_id, final_title, final_clean, category, poster, folder_name))
    finally:
        conn.close()

def get_torrent_meta(hash_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT hash, title, clean_title, category, poster, folder_name FROM torrent_meta WHERE hash = ?", (hash_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_all_torrent_meta() -> Dict[str, Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT hash, title, clean_title, category, poster, folder_name FROM torrent_meta")
        rows = cur.fetchall()
        return {r["hash"]: dict(r) for r in rows}
    finally:
        conn.close()

def delete_torrent_meta(hash_id: str) -> bool:
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM torrent_meta WHERE hash = ?", (hash_id,))
            return cur.rowcount > 0
    finally:
        conn.close()
