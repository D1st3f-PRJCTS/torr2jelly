import httpx
from typing import Dict, Any, Optional

def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f'MediaBrowser Token="{api_key}"',
        "Accept": "application/json"
    }

async def check_health(jellyfin_url: str, api_key: str) -> bool:
    try:
        url = f"{jellyfin_url.rstrip('/')}/System/Info"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=_get_headers(api_key))
            return resp.status_code == 200
    except Exception:
        return False

async def get_system_info(jellyfin_url: str, api_key: str) -> Optional[Dict[str, Any]]:
    try:
        url = f"{jellyfin_url.rstrip('/')}/System/Info"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=_get_headers(api_key))
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None

async def refresh_library(jellyfin_url: str, api_key: str) -> bool:
    try:
        url = f"{jellyfin_url.rstrip('/')}/Library/Refresh"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=_get_headers(api_key))
            return resp.status_code in (200, 204)
    except Exception:
        return False

async def get_item_counts(jellyfin_url: str, api_key: str) -> Optional[Dict[str, Any]]:
    try:
        url = f"{jellyfin_url.rstrip('/')}/Items/Counts"
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=_get_headers(api_key))
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None
