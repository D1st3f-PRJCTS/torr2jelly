import asyncio
import logging
import os
import shutil

logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (
    auth,
    jellyfin_client,
    prowlarr_client,
    strm_engine,
    torr_client,
    torrent_store,
)
from .config import Settings, load_settings, save_settings

settings = load_settings()
background_sync_task = None
POSTER_CACHE: dict[str, str] = {}


async def sync_job(trigger_jellyfin: bool = True):
    global settings
    try:
        torrents = await torr_client.list_torrents(settings.torrserver_url)
        stored_meta = torrent_store.get_all_torrent_meta()
        title_overrides = {h: m["title"] for h, m in stored_meta.items() if m.get("title")}
        category_overrides = {h: m["category"] for h, m in stored_meta.items() if m.get("category")}
        categories_list = [c.model_dump() for c in settings.categories]
        stats = strm_engine.sync_all_torrents(
            torrents=torrents,
            media_dir=settings.media_dir,
            stream_base_url=settings.jellyfin_stream_torr_url,
            title_overrides=title_overrides,
            category_overrides=category_overrides,
            categories=categories_list,
        )
        if trigger_jellyfin and stats.get("synced_torrents", 0) > 0 and settings.jellyfin_api_key:
            await jellyfin_client.refresh_library(settings.jellyfin_url, settings.jellyfin_api_key)
        return stats
    except Exception as e:
        print(f"Error in sync_job: {e}")
        return {"error": str(e)}


async def auto_sync_worker():
    while True:
        try:
            if settings.auto_sync and settings.sync_interval > 0:
                await sync_job(trigger_jellyfin=True)
                await asyncio.sleep(settings.sync_interval)
            else:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Sync worker loop error: {e}")
            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global background_sync_task
    auth.seed_initial_admin_if_needed()
    torrent_store.init_torrent_store()
    background_sync_task = asyncio.create_task(auto_sync_worker())
    yield
    if background_sync_task:
        background_sync_task.cancel()
        try:
            await background_sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Torr2Jelly", version="1.5.0", lifespan=lifespan)


# Request schemas
class ChangeCategoryRequest(BaseModel):
    category: str


class AddTorrentRequest(BaseModel):
    link: str
    title: str | None = None
    category: str | None = None  # "movie" or "show"
    poster: str | None = None
    sync_now: bool = True


class RenameTorrentRequest(BaseModel):
    title: str
    rename_folder: bool = True
    category: str | None = None


class DeleteTorrentRequest(BaseModel):
    delete_strm: bool = True


class TestServiceRequest(BaseModel):
    service: str  # "prowlarr", "jellyfin", "torrserver"
    url: str
    api_key: str | None = None


class SetPosterRequest(BaseModel):
    poster: str | None = None
    auto_fetch: bool = False
    auto_find: bool = False

    @property
    def should_auto_fetch(self) -> bool:
        return self.auto_fetch or self.auto_find


class CreateFolderRequest(BaseModel):
    folder_name: str


class RenameItemRequest(BaseModel):
    old_path: str
    new_path: str | None = None
    new_name: str | None = None

    @property
    def target_name(self) -> str:
        return self.new_path or self.new_name or ""


class MoveFilesRequest(BaseModel):
    files: list[str] | None = None
    file_paths: list[str] | None = None
    target_folder: str = ""

    @property
    def target_files(self) -> list[str]:
        return self.files or self.file_paths or []


# Authentication dependencies
async def get_current_user(authorization: str | None = Header(None)) -> auth.User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    payload = auth.decode_access_token(token, settings.jwt_secret)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_dict = auth.get_user_by_username(payload["sub"])
    if not user_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.User(
        id=user_dict["id"],
        username=user_dict["username"],
        role=user_dict["role"],
        created_at=str(user_dict.get("created_at") or ""),
    )


async def get_admin_user(
    current_user: auth.User = Depends(get_current_user),
) -> auth.User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to administrators",
        )
    return current_user


# Helper to find torrent & root directory
async def _get_torrent_and_root(hash_id: str):
    torrent = await torr_client.get_torrent(settings.torrserver_url, hash_id)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found in TorrServer")
    meta = torrent_store.get_torrent_meta(hash_id)
    if meta:
        if meta.get("title") and not torrent.get("title"):
            torrent["title"] = meta["title"]
        if meta.get("category"):
            torrent["category"] = meta["category"]
    categories_list = [c.model_dump() for c in settings.categories]
    abs_root, rel_root = strm_engine.find_torrent_root_folder(torrent, settings.media_dir, categories_list)
    return torrent, abs_root, rel_root


# ==================== AUTH ENDPOINTS ====================


@app.get("/api/auth/setup-status")
async def get_setup_status():
    return {
        "setup_required": auth.count_users() == 0,
        "language": settings.language,
        "only_gold_torrents": settings.only_gold_torrents,
    }


@app.post("/api/auth/setup")
async def initial_setup(req: auth.SetupRequest):
    if auth.count_users() > 0:
        raise HTTPException(status_code=403, detail="Initial setup already completed.")
    try:
        user = auth.create_user(req.username, req.password, role="admin")
        token = auth.create_access_token(user.username, user.role, settings.jwt_secret)
        return {"status": "ok", "token": token, "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def login(req: auth.LoginRequest):
    user_dict = auth.get_user_by_username(req.username.strip())
    if not user_dict or not auth.verify_password(req.password, user_dict["password_hash"], user_dict["salt"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user = auth.User(
        id=user_dict["id"],
        username=user_dict["username"],
        role=user_dict["role"],
        created_at=str(user_dict.get("created_at") or ""),
    )
    token = auth.create_access_token(user.username, user.role, settings.jwt_secret)
    return {"status": "ok", "token": token, "user": user}


@app.get("/api/auth/me")
async def get_me(current_user: auth.User = Depends(get_current_user)):
    return current_user


@app.post("/api/auth/change-password")
async def change_password(req: auth.UserChangePassword, current_user: auth.User = Depends(get_current_user)):
    user_dict = auth.get_user_by_username(current_user.username)
    if not user_dict or not auth.verify_password(req.current_password, user_dict["password_hash"], user_dict["salt"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        auth.update_user_password(current_user.username, req.new_password)
        return {"status": "ok", "message": "Password changed successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== USER MANAGEMENT (ADMIN ONLY) ====================


@app.get("/api/users")
async def list_users_endpoint(admin: auth.User = Depends(get_admin_user)):
    return auth.list_users()


@app.post("/api/users")
async def create_user_endpoint(req: auth.UserCreate, admin: auth.User = Depends(get_admin_user)):
    try:
        new_user = auth.create_user(req.username, req.password, req.role)
        return {"status": "ok", "user": new_user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/users/{username}")
async def delete_user_endpoint(username: str, admin: auth.User = Depends(get_admin_user)):
    if username.lower() == admin.username.lower():
        raise HTTPException(status_code=400, detail="Cannot delete your own administrator account")
    deleted = auth.delete_user(username)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "message": f"User {username} deleted"}


@app.post("/api/users/{username}/reset-password")
async def reset_user_password_endpoint(
    username: str,
    req: auth.UserResetPassword,
    admin: auth.User = Depends(get_admin_user),
):
    user_dict = auth.get_user_by_username(username)
    if not user_dict:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        auth.update_user_password(username, req.new_password)
        return {
            "status": "ok",
            "message": f"Password for {username} reset successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== SYSTEM STATUS & TORRENTS ====================


@app.get("/api/status")
async def get_status(user: auth.User = Depends(get_current_user)):
    torr_ok = await torr_client.check_health(settings.torrserver_url)
    jelly_ok = await jellyfin_client.check_health(settings.jellyfin_url, settings.jellyfin_api_key)
    jelly_info = (
        await jellyfin_client.get_system_info(settings.jellyfin_url, settings.jellyfin_api_key) if jelly_ok else None
    )
    prowl_ok = (
        await prowlarr_client.check_health(settings.prowlarr_url, settings.prowlarr_api_key)
        if settings.prowlarr_url
        else False
    )

    # Disk usage
    disk_total, disk_used, disk_free = 0, 0, 0
    if os.path.exists(settings.media_dir):
        total, used, free = shutil.disk_usage(settings.media_dir)
        disk_total, disk_used, disk_free = total, used, free

    return {
        "torrserver": {
            "status": "online" if torr_ok else "offline",
            "url": settings.torrserver_url,
        },
        "jellyfin": {
            "status": "online" if jelly_ok else "offline",
            "url": settings.jellyfin_url,
            "info": jelly_info,
        },
        "prowlarr": {
            "status": "online" if prowl_ok else "offline",
            "url": settings.prowlarr_url,
        },
        "media_dir": {
            "path": settings.media_dir,
            "total_gb": round(disk_total / (1024**3), 2),
            "free_gb": round(disk_free / (1024**3), 2),
            "used_pct": round((disk_used / disk_total) * 100, 1) if disk_total else 0,
        },
        "categories": [c.model_dump() for c in settings.categories],
        "auto_sync": settings.auto_sync,
        "sync_interval": settings.sync_interval,
        "language": settings.language,
        "only_gold_torrents": getattr(settings, "only_gold_torrents", False),
    }


@app.get("/api/search")
async def search_torrents(
    query: str = Query(..., min_length=1),
    category: str | None = None,
    user: auth.User = Depends(get_current_user),
):
    if not settings.prowlarr_url or not settings.prowlarr_api_key:
        raise HTTPException(status_code=400, detail="Prowlarr is not configured. Contact admin.")
    try:
        results = await prowlarr_client.search(
            prowlarr_url=settings.prowlarr_url,
            api_key=settings.prowlarr_api_key,
            query=query,
        )
        for r in results:
            clean = strm_engine.clean_media_title(r["title"])
            r["clean_title"] = clean
        if settings.only_gold_torrents and user.role != "admin":
            results = [r for r in results if r.get("release_status") == "gold"]
        return results
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Prowlarr search error: {e}")


@app.get("/api/torrents")
async def get_torrents(user: auth.User = Depends(get_current_user)):
    try:
        items = await torr_client.list_torrents(settings.torrserver_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach TorrServer: {e}")

    stored_meta = torrent_store.get_all_torrent_meta()

    enriched = []
    for t in items:
        t_hash = t.get("hash", "")
        meta = stored_meta.get(t_hash)

        raw_title = ""
        if meta and meta.get("title"):
            raw_title = meta["title"]
        elif t.get("title"):
            raw_title = t.get("title")
        elif t.get("name"):
            raw_title = t.get("name")
        else:
            recovered = strm_engine.recover_title_from_disk(t_hash, settings.media_dir)
            if recovered:
                raw_title = recovered[0]
            else:
                raw_title = t_hash

        clean_title = strm_engine.clean_media_title(raw_title)
        video_files = strm_engine.extract_video_files(t)
        is_movie = len(video_files) <= 1
        cat = (
            meta.get("category")
            if (meta and meta.get("category") and meta.get("category") != "auto")
            else ("movie" if is_movie else "show")
        )

        # Save to persistent store if new or missing
        if raw_title and raw_title != t_hash and (not meta or not meta.get("title")):
            torrent_store.save_torrent_meta(hash_id=t_hash, title=raw_title, clean_title=clean_title, category=cat)

        # Sync title back to TorrServer if TorrServer title is empty
        if raw_title and raw_title != t_hash and not t.get("title"):
            asyncio.create_task(torr_client.set_torrent_title(settings.torrserver_url, t_hash, raw_title))

        poster = (meta.get("poster") if meta else None) or t.get("poster")
        if not poster and t_hash in POSTER_CACHE:
            poster = POSTER_CACHE[t_hash]

        # Auto-discover poster if missing
        if not poster and raw_title and raw_title != t_hash:
            try:
                discovered = await strm_engine.fetch_poster_online(raw_title, cat)
                if discovered:
                    POSTER_CACHE[t_hash] = discovered
                    poster = discovered
                    torrent_store.save_torrent_meta(hash_id=t_hash, title=raw_title, poster=discovered)
                    asyncio.create_task(torr_client.set_torrent_poster(settings.torrserver_url, t_hash, discovered))
            except Exception:
                pass

        enriched.append(
            {
                "hash": t_hash,
                "title": raw_title,
                "clean_title": clean_title,
                "category": cat,
                "poster": poster,
                "stat": t.get("stat"),
                "stat_string": t.get("stat_string"),
                "torrent_size": t.get("torrent_size"),
                "loaded_size": t.get("loaded_size"),
                "download_speed": t.get("download_speed") or 0,
                "upload_speed": t.get("upload_speed") or 0,
                "total_peers": t.get("total_peers") or 0,
                "pending_peers": t.get("pending_peers") or 0,
                "active_peers": t.get("active_peers") or 0,
                "connected_seeders": t.get("connected_seeders") or 0,
                "video_files_count": len(video_files),
                "video_files": [
                    {
                        "id": f.get("id"),
                        "name": os.path.basename(f.get("path") or f.get("name") or ""),
                        "size": f.get("size"),
                    }
                    for f in video_files
                ],
            }
        )
    return enriched


async def _delayed_poster_discovery(t_hash: str, req_title: str | None, category: str | None):
    await asyncio.sleep(4)
    try:
        t = await torr_client.get_torrent(settings.torrserver_url, t_hash)
        if not t:
            return
        current_poster = t.get("poster")
        if current_poster:
            POSTER_CACHE[t_hash] = current_poster
            torrent_store.save_torrent_meta(hash_id=t_hash, poster=current_poster)
            return
        meta = torrent_store.get_torrent_meta(t_hash) or {}
        title = meta.get("title") or req_title or t.get("title") or t.get("name")
        if not title:
            return
        video_files = strm_engine.extract_video_files(t)
        cat = category or meta.get("category") or ("movie" if len(video_files) <= 1 else "show")
        discovered = await strm_engine.fetch_poster_online(title, cat)
        if discovered:
            POSTER_CACHE[t_hash] = discovered
            torrent_store.save_torrent_meta(hash_id=t_hash, poster=discovered)
            await torr_client.set_torrent_poster(settings.torrserver_url, t_hash, discovered)
    except Exception as e:
        logger.debug(f"Delayed poster discovery failed for {t_hash}: {e}")


@app.post("/api/torrents")
async def add_torrent(
    req: AddTorrentRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    try:
        # If no poster provided, try online discovery
        poster = req.poster
        if not poster and req.title:
            discovered = await strm_engine.fetch_poster_online(req.title, req.category)
            if discovered:
                poster = discovered

        res = await torr_client.add_torrent(
            base_url=settings.torrserver_url,
            link=req.link,
            title=req.title,
            category=req.category,
            poster=poster,
        )
        if not res:
            raise HTTPException(status_code=400, detail="Failed to add torrent to TorrServer.")

        t_hash = res.get("hash")
        if t_hash:
            if poster:
                POSTER_CACHE[t_hash] = poster
            title_to_save = req.title or t_hash
            torrent_store.save_torrent_meta(
                hash_id=t_hash,
                title=title_to_save,
                clean_title=strm_engine.clean_media_title(title_to_save),
                category=req.category,
                poster=poster,
            )
            if not poster:
                background_tasks.add_task(_delayed_poster_discovery, t_hash, req.title, req.category)

        if req.sync_now:
            background_tasks.add_task(sync_job, True)

        return {"status": "ok", "torrent": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/torrents/{hash_id}/poster")
async def update_torrent_poster(hash_id: str, req: SetPosterRequest, user: auth.User = Depends(get_current_user)):
    torrent = await torr_client.get_torrent(settings.torrserver_url, hash_id)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")

    new_poster = req.poster
    if req.should_auto_fetch or not new_poster:
        existing_meta = torrent_store.get_torrent_meta(hash_id) or {}
        raw_title = existing_meta.get("title") or torrent.get("title") or torrent.get("name") or ""
        cat = existing_meta.get("category") or torrent.get("category")
        if not cat or cat == "auto":
            video_files = strm_engine.extract_video_files(torrent)
            cat = "movie" if len(video_files) <= 1 else "show"
        new_poster = await strm_engine.fetch_poster_online(raw_title, cat)

    if not new_poster:
        raise HTTPException(status_code=404, detail="Could not find a poster online")

    POSTER_CACHE[hash_id] = new_poster
    torrent_store.save_torrent_meta(hash_id=hash_id, poster=new_poster)
    await torr_client.set_torrent_poster(settings.torrserver_url, hash_id, new_poster)
    return {"status": "ok", "poster": new_poster}


@app.post("/api/torrents/{hash_id}/category")
async def change_torrent_category(
    hash_id: str,
    req: ChangeCategoryRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    torrent = await torr_client.get_torrent(settings.torrserver_url, hash_id)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found in TorrServer")

    new_cat = req.category.strip()
    if not new_cat:
        raise HTTPException(status_code=400, detail="Category cannot be empty")

    categories_list = [c.model_dump() for c in settings.categories]
    target_cat_def = next((c for c in categories_list if c["id"] == new_cat), None)
    if not target_cat_def and new_cat not in ("movie", "show"):
        raise HTTPException(status_code=400, detail=f"Category '{new_cat}' does not exist")

    existing_meta = torrent_store.get_torrent_meta(hash_id) or {}
    raw_title = existing_meta.get("title") or torrent.get("title") or torrent.get("name") or hash_id
    clean_title = strm_engine.clean_media_title(raw_title)
    torrent_store.save_torrent_meta(hash_id=hash_id, title=raw_title, clean_title=clean_title, category=new_cat)

    await torr_client.set_torrent_category(settings.torrserver_url, hash_id, new_cat)

    dest_folder = None
    try:
        abs_root, rel_root = strm_engine.find_torrent_root_folder(torrent, settings.media_dir, categories_list)
        if abs_root and os.path.exists(abs_root):
            target_base = strm_engine.get_category_path(
                target_cat_def
                or {
                    "id": new_cat,
                    "type": "movie" if new_cat == "movie" else "show",
                    "path": new_cat,
                },
                settings.media_dir,
            )
            os.makedirs(target_base, exist_ok=True)
            folder_name = os.path.basename(abs_root)
            dest_abs = os.path.join(target_base, folder_name)
            if os.path.normpath(abs_root) != os.path.normpath(dest_abs):
                strm_engine.migrate_category_folder(abs_root, dest_abs)
                dest_folder = dest_abs
    except Exception as e:
        logger.warning(f"Could not migrate folder for torrent {hash_id}: {e}")

    if settings.jellyfin_api_key:
        background_tasks.add_task(
            jellyfin_client.refresh_library,
            settings.jellyfin_url,
            settings.jellyfin_api_key,
        )

    return {"status": "ok", "category": new_cat, "migrated_to": dest_folder}


@app.post("/api/torrents/{hash_id}/rename")
async def rename_torrent_endpoint(
    hash_id: str,
    req: RenameTorrentRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    torrent = await torr_client.get_torrent(settings.torrserver_url, hash_id)
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found in TorrServer")

    clean_new = strm_engine.clean_media_title(new_title)
    existing_meta = torrent_store.get_torrent_meta(hash_id) or {}
    old_cat = existing_meta.get("category") or torrent.get("category")
    new_cat = req.category or old_cat

    torrent_store.save_torrent_meta(
        hash_id=hash_id,
        title=new_title,
        clean_title=clean_new,
        category=new_cat,
        folder_name=clean_new,
    )

    ok = await torr_client.set_torrent_title(settings.torrserver_url, hash_id, new_title)
    if not ok:
        logger.warning(f"Failed to update title in TorrServer for {hash_id}")

    new_root = None
    categories_list = [c.model_dump() for c in settings.categories]
    if req.rename_folder:
        try:
            abs_root, rel_root = strm_engine.find_torrent_root_folder(torrent, settings.media_dir, categories_list)
            if abs_root and os.path.exists(abs_root):
                if new_cat and old_cat and new_cat != old_cat:
                    target_cat_def = next((c for c in categories_list if c["id"] == new_cat), None)
                    if target_cat_def:
                        new_cat_base = strm_engine.get_category_path(target_cat_def, settings.media_dir)
                        os.makedirs(new_cat_base, exist_ok=True)
                        dest_abs = os.path.join(new_cat_base, clean_new)
                        if abs_root != dest_abs:
                            strm_engine.migrate_category_folder(abs_root, dest_abs)
                            abs_root = dest_abs
                new_root = strm_engine.rename_torrent_root_folder(abs_root, new_title)
        except Exception as e:
            logger.warning(f"Could not rename media folder: {e}")

    if settings.jellyfin_api_key:
        background_tasks.add_task(
            jellyfin_client.refresh_library,
            settings.jellyfin_url,
            settings.jellyfin_api_key,
        )

    return {
        "status": "ok",
        "title": new_title,
        "clean_title": clean_new,
        "category": new_cat,
        "new_root": new_root,
    }


@app.delete("/api/torrents/{hash_id}")
async def delete_torrent(hash_id: str, delete_strm: bool = True, user: auth.User = Depends(get_current_user)):
    torrent = await torr_client.get_torrent(settings.torrserver_url, hash_id)
    success = await torr_client.remove_torrent(settings.torrserver_url, hash_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove torrent from TorrServer")

    torrent_store.delete_torrent_meta(hash_id)

    removed_files = 0
    if delete_strm and torrent:
        categories_list = [c.model_dump() for c in settings.categories]
        removed_files = strm_engine.remove_torrent_files(torrent, settings.media_dir, categories_list)
        if removed_files > 0 and settings.jellyfin_api_key:
            await jellyfin_client.refresh_library(settings.jellyfin_url, settings.jellyfin_api_key)

    return {"status": "ok", "removed_strm_files": removed_files}


# ==================== FILE STRUCTURE MANAGEMENT ====================


@app.get("/api/torrents/{hash_id}/files")
async def get_torrent_files_structure(hash_id: str, user: auth.User = Depends(get_current_user)):
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    return strm_engine.get_media_structure(abs_root, rel_root)


@app.post("/api/torrents/{hash_id}/files/organize")
async def organize_torrent_files(
    hash_id: str,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    res = strm_engine.auto_organize_seasons(abs_root)
    if settings.jellyfin_api_key and res.get("moved_count", 0) > 0:
        background_tasks.add_task(
            jellyfin_client.refresh_library,
            settings.jellyfin_url,
            settings.jellyfin_api_key,
        )
    res["structure"] = strm_engine.get_media_structure(abs_root, rel_root)
    return res


@app.post("/api/torrents/{hash_id}/files/folder")
async def create_folder_endpoint(hash_id: str, req: CreateFolderRequest, user: auth.User = Depends(get_current_user)):
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    try:
        created = strm_engine.create_media_folder(abs_root, req.folder_name)
        return {
            "status": "ok",
            "created": created,
            "structure": strm_engine.get_media_structure(abs_root, rel_root),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/torrents/{hash_id}/files/rename")
async def rename_file_endpoint(
    hash_id: str,
    req: RenameItemRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    target_name = req.target_name
    if not target_name:
        raise HTTPException(status_code=400, detail="Field 'new_name' or 'new_path' is required")
    try:
        new_rel = strm_engine.rename_media_item(abs_root, req.old_path, target_name)
        if settings.jellyfin_api_key:
            background_tasks.add_task(
                jellyfin_client.refresh_library,
                settings.jellyfin_url,
                settings.jellyfin_api_key,
            )
        return {
            "status": "ok",
            "new_path": new_rel,
            "structure": strm_engine.get_media_structure(abs_root, rel_root),
        }
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/torrents/{hash_id}/files/move")
async def move_files_endpoint(
    hash_id: str,
    req: MoveFilesRequest,
    background_tasks: BackgroundTasks,
    user: auth.User = Depends(get_current_user),
):
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    files_to_move = req.target_files
    if not files_to_move:
        raise HTTPException(status_code=400, detail="No files specified to move")
    try:
        moved = strm_engine.move_media_files(abs_root, files_to_move, req.target_folder)
        if settings.jellyfin_api_key and moved > 0:
            background_tasks.add_task(
                jellyfin_client.refresh_library,
                settings.jellyfin_url,
                settings.jellyfin_api_key,
            )
        return {
            "status": "ok",
            "moved_count": moved,
            "structure": strm_engine.get_media_structure(abs_root, rel_root),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/torrents/{hash_id}/files")
async def delete_file_endpoint(
    hash_id: str,
    path: str | None = Query(None),
    target_path: str | None = Query(None),
    background_tasks: BackgroundTasks = None,
    user: auth.User = Depends(get_current_user),
):
    del_path = path or target_path
    if not del_path:
        raise HTTPException(
            status_code=400,
            detail="Query parameter 'path' or 'target_path' is required",
        )
    torrent, abs_root, rel_root = await _get_torrent_and_root(hash_id)
    try:
        deleted = strm_engine.delete_media_item(abs_root, del_path)
        if not deleted:
            raise HTTPException(status_code=404, detail="File or folder not found")
        if settings.jellyfin_api_key and background_tasks:
            background_tasks.add_task(
                jellyfin_client.refresh_library,
                settings.jellyfin_url,
                settings.jellyfin_api_key,
            )
        return {
            "status": "ok",
            "structure": strm_engine.get_media_structure(abs_root, rel_root),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== SYNC & JELLYFIN ====================


@app.post("/api/sync")
async def trigger_sync(user: auth.User = Depends(get_current_user)):
    stats = await sync_job(trigger_jellyfin=True)
    return {"status": "ok", "stats": stats}


@app.post("/api/jellyfin/refresh")
async def refresh_jellyfin(user: auth.User = Depends(get_current_user)):
    if not settings.jellyfin_api_key:
        raise HTTPException(status_code=400, detail="Jellyfin API key not configured")
    ok = await jellyfin_client.refresh_library(settings.jellyfin_url, settings.jellyfin_api_key)
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to trigger Jellyfin library refresh")
    return {"status": "ok", "message": "Library refresh requested"}


# ==================== SETTINGS (ADMIN ONLY) ====================


@app.get("/api/settings")
async def get_settings(admin: auth.User = Depends(get_admin_user)):
    data = settings.model_dump()
    data.pop("jwt_secret", None)
    return data


@app.get("/api/categories")
async def get_categories():
    return [c.model_dump() for c in settings.categories]


@app.post("/api/settings")
async def update_settings(
    new_settings: Settings,
    background_tasks: BackgroundTasks,
    admin: auth.User = Depends(get_admin_user),
):
    global settings
    if not new_settings.jwt_secret:
        new_settings.jwt_secret = settings.jwt_secret

    # Check for category path changes and migrate if needed
    old_cats_map = {c.id: strm_engine.get_category_path(c, settings.media_dir) for c in settings.categories}
    new_cats_map = {c.id: strm_engine.get_category_path(c, new_settings.media_dir) for c in new_settings.categories}

    migrated_any = False
    for cat_id, new_path in new_cats_map.items():
        old_path = old_cats_map.get(cat_id)
        if old_path and old_path != new_path and os.path.exists(old_path):
            try:
                strm_engine.migrate_category_folder(old_path, new_path)
                migrated_any = True
                logger.info(f"Migrated category '{cat_id}' from {old_path} to {new_path}")
            except Exception as e:
                logger.warning(f"Error migrating category '{cat_id}': {e}")

    settings = new_settings
    save_settings(settings)

    if migrated_any and settings.jellyfin_api_key:
        background_tasks.add_task(
            jellyfin_client.refresh_library,
            settings.jellyfin_url,
            settings.jellyfin_api_key,
        )

    data = settings.model_dump()
    data.pop("jwt_secret", None)
    return {"status": "ok", "settings": data}


@app.post("/api/settings/test")
async def test_service_connection(req: TestServiceRequest, admin: auth.User = Depends(get_admin_user)):
    if req.service == "prowlarr":
        ok = await prowlarr_client.check_health(req.url, req.api_key or "")
        return {"status": "ok" if ok else "error", "reachable": ok}
    elif req.service == "jellyfin":
        ok = await jellyfin_client.check_health(req.url, req.api_key or "")
        return {"status": "ok" if ok else "error", "reachable": ok}
    elif req.service == "torrserver":
        ok = await torr_client.check_health(req.url)
        return {"status": "ok" if ok else "error", "reachable": ok}
    else:
        raise HTTPException(status_code=400, detail="Unknown service name")


# ==================== STATIC & FAVICON ====================

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    fav_path = os.path.join(static_dir, "logo.png")
    if os.path.exists(fav_path):
        return FileResponse(fav_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/")
async def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
