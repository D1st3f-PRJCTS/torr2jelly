try:
    import httpx
except ImportError:
    httpx = None

from typing import List, Dict, Any, Optional

def _get_headers(api_key: str) -> Dict[str, str]:
    return {
        "X-Api-Key": api_key,
        "Accept": "application/json"
    }

async def check_health(prowlarr_url: str, api_key: str) -> bool:
    if not httpx:
        return False
    try:
        url = f"{prowlarr_url.rstrip('/')}/api/v1/system/status"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=_get_headers(api_key))
            return resp.status_code == 200
    except Exception:
        return False

def determine_release_status(indexer_flags: List[str], download_volume_factor: Optional[float]) -> str:
    flags_lower = [str(f).lower() for f in indexer_flags]
    if "freeleech" in flags_lower or download_volume_factor == 0:
        return "gold"
    if "halfleech" in flags_lower or download_volume_factor == 0.5:
        return "silver"
    return "normal"

async def search(
    prowlarr_url: str,
    api_key: str,
    query: str,
    categories: Optional[List[int]] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    if not query.strip() or not httpx:
        return []

    url = f"{prowlarr_url.rstrip('/')}/api/v1/search"
    params: Dict[str, Any] = {
        "query": query,
        "type": "search",
        "limit": limit
    }
    if categories:
        params["categories"] = categories

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params=params, headers=_get_headers(api_key))
        resp.raise_for_status()
        raw_results = resp.json()

    results = []
    for item in raw_results:
        download_url = item.get("downloadUrl")
        magnet_url = item.get("magnetUrl")
        info_url = item.get("infoUrl")
        guid = item.get("guid")
        link = magnet_url or download_url or info_url
        if not link:
            continue

        page_url = info_url
        if not page_url and guid and guid.startswith("http"):
            page_url = guid

        raw_flags = item.get("indexerFlags") or []
        vol_factor = item.get("downloadVolumeFactor")
        status = determine_release_status(raw_flags, vol_factor)

        # Priority score: gold=3, silver=2, normal=1
        priority = 3 if status == "gold" else (2 if status == "silver" else 1)

        results.append({
            "guid": guid,
            "title": item.get("title"),
            "indexer": item.get("indexer"),
            "indexer_id": item.get("indexerId"),
            "size": item.get("size", 0),
            "seeders": item.get("seeders", 0),
            "leechers": item.get("leechers", 0),
            "publish_date": item.get("publishDate"),
            "link": link,
            "page_url": page_url or link,
            "download_url": download_url,
            "magnet_url": magnet_url,
            "info_hash": item.get("infoHash"),
            "indexer_flags": raw_flags,
            "release_status": status,  # "gold", "silver", "normal"
            "priority": priority,
            "categories": [c.get("name") for c in item.get("categories", []) if isinstance(c, dict)]
        })

    # Default sorting: by PRIORITY first (Gold -> Silver -> Normal), then by seeders desc
    results.sort(key=lambda x: (x.get("priority", 0), x.get("seeders", 0)), reverse=True)
    return results
