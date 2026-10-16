import httpx
from typing import List, Dict, Any, Optional

async def torr_request(base_url: str, action: str, data: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{base_url.rstrip('/')}/torrents"
    payload = {"action": action}
    if data:
        payload.update(data)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return None
        return resp.json()

async def list_torrents(base_url: str) -> List[Dict[str, Any]]:
    res = await torr_request(base_url, "list")
    return res if isinstance(res, list) else []

async def get_torrent(base_url: str, hash_id: str) -> Optional[Dict[str, Any]]:
    return await torr_request(base_url, "get", {"hash": hash_id})

async def add_torrent(
    base_url: str,
    link: str,
    title: Optional[str] = None,
    category: Optional[str] = None,
    poster: Optional[str] = None,
    save_to_db: bool = True
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "link": link,
        "save_to_db": save_to_db
    }
    if title:
        payload["title"] = title
    if category:
        payload["category"] = category
    if poster:
        payload["poster"] = poster
    res = await torr_request(base_url, "add", payload)
    return res or {}

async def set_torrent_poster(base_url: str, hash_id: str, poster: str) -> bool:
    try:
        await torr_request(base_url, "set", {"hash": hash_id, "poster": poster})
        return True
    except Exception:
        return False

async def set_torrent_title(base_url: str, hash_id: str, title: str) -> bool:
    try:
        await torr_request(base_url, "set", {"hash": hash_id, "title": title})
        return True
    except Exception:
        return False

async def set_torrent_category(base_url: str, hash_id: str, category: str) -> bool:
    try:
        await torr_request(base_url, "set", {"hash": hash_id, "category": category})
        return True
    except Exception:
        return False

async def remove_torrent(base_url: str, hash_id: str) -> bool:
    try:
        await torr_request(base_url, "rem", {"hash": hash_id})
        return True
    except Exception:
        try:
            await torr_request(base_url, "drop", {"hash": hash_id})
            return True
        except Exception:
            return False

async def check_health(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/echo")
            return resp.status_code == 200
    except Exception:
        return False
