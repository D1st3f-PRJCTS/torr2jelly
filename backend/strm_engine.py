import json
import os
import re
import shutil
from typing import Any

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".ts", ".mov", ".m4v", ".webm"}


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\x5c\x2f\x2a\x3f\x3a\x22\x3c\x3e\x7c]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def clean_media_title(title: str) -> str:
    if not title:
        return "Untitled"
    cleaned = re.sub(r"\[.*?\]", " ", title)
    # Remove years like (2019) or ranges (2019-2022)
    cleaned = re.sub(r"\(\s*\d{4}(?:[-\u2013]\d{4})?\s*\)", " ", cleaned)
    # Remove season tags: Season 1-2, Сезон 1, S1, S01-S05
    # (requiring word boundary so Peaky Blinders does not match S1080)
    cleaned = re.sub(
        r"\(?\s*(?:\b(?:Season|Сезон)\s*\d+(?:[.\-\u2013]\d+)?|\bS\d{1,2}(?:[.\-\u2013]S?\d{1,2})?)\s*\)?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove episode tags: E01-E10, Серії 1-10 з 10, etc.
    cleaned = re.sub(
        r"\(?\s*(?:\b(?:Episode|Сері[яї]|Серій|Епизод)\s*\d+(?:[.\-\u2013]\d+)?|\bE\d{1,3}(?:[.\-\u2013]E?\d{1,3})?)\s*\)?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Comprehensive release, audio, codec and language tags
    tags = [
        r"\b(?:BD|UHD)?Remux\b",
        r"\b\d+x(?:Ukr|Eng|Rus|Pol|Fra|Ger|Jap|Multi)\b",
        r"\b(?:Sub\s*(?:Ukr|Eng|Rus)?)\b",
        r"\b(?:BDRip|WEBRip|WEB-DL|DVDRip|HDRip|BluRay|Blu-ray|BD|1080p|720p|2160p|4K|UHD|HDTV|HD|SD)\b",
        r"\b(?:HDR10\+?|Dolby\s*Vision|DV|SDR|10bit|8bit|IMAX|AV1|HEVC|H\.?265|x265|H\.?264|x264|XviD|DivX)\b",
        r"\b(?:DTS-HD(?:\s*MA)?|TrueHD|Atmos|E-?AC-?3|DDP\d?\.?\d?|AC3|AAC|FLAC|Dual|DVO|MVO|VO|Dub|Line)\b",
        r"\b(?:PROPER|REPACK|EXTENDED|UNRATED|THEATRICAL|DIRECTOR\x27?S?\s*CUT|RESTORED|CRITERION|HYBRID)\b",
        r"\b(?:UkrEng|Ukr|Eng|Toloka|Hurtom|NF)\b",
    ]
    for tag in tags:
        cleaned = re.sub(tag, " ", cleaned, flags=re.IGNORECASE)

    # Remove standalone 4-digit years like 2024 if preceded by title words
    cleaned = re.sub(r"(?<=[a-zA-Z0-9])[._ ]+(?:19\d{2}|20\d{2})(?=[._ ]|$)", " ", cleaned)
    cleaned = cleaned.replace(".", " ").replace("_", " ")
    cleaned = sanitize_filename(cleaned)
    cleaned = re.sub(r"[\(\)\-\u2013|/]+$", "", cleaned).strip()
    return cleaned if cleaned else sanitize_filename(title)


def extract_video_files(torrent_item: dict[str, Any]) -> list[dict[str, Any]]:
    file_stats = torrent_item.get("file_stats") or []
    if not file_stats and torrent_item.get("data"):
        try:
            parsed_data = json.loads(torrent_item["data"])
            file_stats = parsed_data.get("TorrServer", {}).get("Files", [])
        except Exception:
            file_stats = []

    video_files = []
    for f in file_stats:
        path = f.get("path") or f.get("name") or ""
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXTS:
            video_files.append(f)
    return video_files


def parse_episode_info(filename: str, parts: list[str], default_title: str) -> tuple[str, str, str]:
    show_name = clean_media_title(default_title)
    base_name = os.path.splitext(filename)[0]

    # 1. Specials check
    is_special = False
    for p in parts:
        if re.search(r"\b(special|спеш[еа]л|s1\.5|sp)\b", p, re.IGNORECASE):
            is_special = True
            break
    if not is_special and re.search(r"\b(special|спеш[еа]л|s00e\d+)\b", filename, re.IGNORECASE):
        is_special = True

    if is_special:
        em = re.search(r"[Ee](\d{1,2})", filename)
        ep_num = int(em.group(1)) if em else 1
        prefix_match = re.search(r"^(.*?)[._ -]+(?:Special|S00|SP)", filename, re.IGNORECASE)
        if prefix_match:
            cand = clean_media_title(prefix_match.group(1))
            if cand:
                show_name = cand
        out_name = f"{show_name}.S00E{ep_num:02d}.Special.E{ep_num:02d}"
        return show_name, "Season 00", out_name

    # 2. Match standard S01E02 or 1x02 directly in filename
    m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", filename)
    if not m:
        m = re.search(r"\b(\d{1,2})x(\d{1,2})\b", filename)

    if m:
        season_num = int(m.group(1))
        season_folder = f"Season {season_num:02d}"
        prefix = filename[: m.start()].strip(" ._-[]()")
        if prefix:
            cand = clean_media_title(prefix)
            if cand:
                show_name = cand
        return show_name, season_folder, sanitize_filename(base_name)

    # 3. Check parent folders
    for part in reversed(parts[:-1]):
        sm = re.search(r"\b(?:season|сезон)\s*(\d{1,2})\b", part, re.IGNORECASE)
        if sm:
            season_num = int(sm.group(1))
            return show_name, f"Season {season_num:02d}", sanitize_filename(base_name)

    return show_name, "Season 01", sanitize_filename(base_name)


def get_category_path(category_def: Any, media_dir: str) -> str:
    """
    Resolves the storage directory for a category.
    Supports relative paths (under media_dir) and absolute paths.
    """
    if hasattr(category_def, "model_dump"):
        category_def = category_def.model_dump()
    path = category_def.get("path") if isinstance(category_def, dict) else getattr(category_def, "path", "")
    if not path:
        cat_id = category_def.get("id", "") if isinstance(category_def, dict) else getattr(category_def, "id", "")
        path = cat_id or "movies"
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(media_dir, path))


def get_all_category_dirs(media_dir: str, categories: list[Any] | None = None) -> list[str]:
    """
    Returns list of all active and legacy category root directories.
    """
    dirs = set()
    if categories:
        for c in categories:
            dirs.add(get_category_path(c, media_dir))
    # Always include standard legacy dirs
    dirs.add(os.path.normpath(os.path.join(media_dir, "shows")))
    dirs.add(os.path.normpath(os.path.join(media_dir, "movies")))
    return sorted(list(dirs))


def migrate_category_folder(old_abs: str, new_abs: str) -> None:
    """
    Migrates files and directories from old_abs to new_abs when category storage path is changed.
    """
    if not old_abs or not new_abs or os.path.normpath(old_abs) == os.path.normpath(new_abs):
        return
    if not os.path.exists(old_abs):
        return
    os.makedirs(new_abs, exist_ok=True)
    for item in os.listdir(old_abs):
        s = os.path.join(old_abs, item)
        d = os.path.join(new_abs, item)
        if not os.path.exists(d):
            shutil.move(s, d)
        elif os.path.isdir(s) and os.path.isdir(d):
            for sub in os.listdir(s):
                sub_s = os.path.join(s, sub)
                sub_d = os.path.join(d, sub)
                if not os.path.exists(sub_d):
                    shutil.move(sub_s, sub_d)
            try:
                if not os.listdir(s):
                    os.rmdir(s)
            except Exception:
                pass
    try:
        if os.path.exists(old_abs) and not os.listdir(old_abs):
            os.rmdir(old_abs)
    except Exception:
        pass


def recover_title_from_disk(t_hash: str, media_dir: str, categories: list[Any] | None = None) -> tuple[str, str] | None:
    """
    Recovers the torrent/media title by inspecting existing .strm files on disk that point to this hash.
    Returns (discovered_title, folder_name) or None.
    """
    if not t_hash:
        return None
    pattern = f"link={t_hash}"

    for cat_dir in get_all_category_dirs(media_dir, categories):
        if not os.path.exists(cat_dir):
            continue
        for show_or_movie in os.listdir(cat_dir):
            sub_path = os.path.join(cat_dir, show_or_movie)
            if not os.path.isdir(sub_path):
                continue
            for root, dirs, files in os.walk(sub_path):
                for f in files:
                    if f.endswith(".strm"):
                        try:
                            with open(os.path.join(root, f), "r", encoding="utf-8") as fl:
                                if pattern in fl.read():
                                    folder_name = show_or_movie
                                    if folder_name and not re.match(r"^[0-9a-fA-F]{40}$", folder_name):
                                        return folder_name, folder_name
                                    base_file = os.path.splitext(f)[0]
                                    clean_f = clean_media_title(base_file)
                                    if clean_f and not re.match(r"^[0-9a-fA-F]{40}$", clean_f):
                                        return clean_f, clean_f
                        except Exception:
                            pass
    return None


def sync_single_torrent(
    torrent_item: dict[str, Any],
    media_dir: str,
    stream_base_url: str,
    override_category: str | None = None,
    override_title: str | None = None,
    categories: list[Any] | None = None,
) -> list[str]:
    t_hash = torrent_item.get("hash")
    if not t_hash:
        return []

    raw_title = override_title or torrent_item.get("title") or torrent_item.get("name")
    if not raw_title or raw_title == t_hash:
        recovered = recover_title_from_disk(t_hash, media_dir, categories)
        if recovered:
            raw_title = recovered[0]
        else:
            raw_title = t_hash
    video_files = extract_video_files(torrent_item)
    if not video_files:
        return []

    is_single_file = len(video_files) <= 1
    cat_id = override_category or torrent_item.get("category")
    if not cat_id or cat_id == "auto":
        target_type = "movie" if is_single_file else "show"
        if categories:
            matched_cat = next(
                (
                    c
                    for c in categories
                    if (c.get("type") if isinstance(c, dict) else getattr(c, "type", "")) == target_type
                ),
                None,
            )
            cat_id = (
                (matched_cat.get("id") if isinstance(matched_cat, dict) else getattr(matched_cat, "id", None))
                if matched_cat
                else target_type
            )
        else:
            cat_id = target_type

    cat_def = None
    if categories:
        cat_def = next(
            (c for c in categories if (c.get("id") if isinstance(c, dict) else getattr(c, "id", "")) == cat_id),
            None,
        )

    if cat_def:
        cat_type = cat_def.get("type", "movie") if isinstance(cat_def, dict) else getattr(cat_def, "type", "movie")
        dest_base_dir = get_category_path(cat_def, media_dir)
    else:
        cat_type = "movie" if (cat_id == "movie" or (cat_id not in ("show", "series") and is_single_file)) else "show"
        dest_base_dir = os.path.join(media_dir, "movies" if cat_type == "movie" else "shows")

    os.makedirs(dest_base_dir, exist_ok=True)
    synced_paths: list[str] = []

    if cat_type == "movie":
        clean_title = clean_media_title(raw_title)
        movie_dir = os.path.join(dest_base_dir, clean_title)
        os.makedirs(movie_dir, exist_ok=True)
        try:
            os.chmod(movie_dir, 0o777)
        except Exception:
            pass
        strm_path = os.path.join(movie_dir, f"{clean_title}.strm")
        v_file = video_files[0]
        stream_url = f"{stream_base_url.rstrip('/')}/stream?link={t_hash}&index={v_file['id']}&play\n"

        needs_write = True
        if os.path.exists(strm_path):
            try:
                with open(strm_path, "r", encoding="utf-8") as f:
                    if f.read() == stream_url:
                        needs_write = False
            except Exception:
                pass

        if needs_write:
            with open(strm_path, "w", encoding="utf-8") as f:
                f.write(stream_url)
            try:
                os.chmod(strm_path, 0o666)
            except Exception:
                pass

        synced_paths.append(strm_path)
    else:
        for v_file in video_files:
            rel_path = v_file.get("path") or v_file.get("name") or ""
            parts = [p for p in rel_path.split("/") if p]
            filename = parts[-1] if parts else f"episode_{v_file['id']}.mkv"

            show_name, season_folder, file_base_name = parse_episode_info(filename, parts, raw_title)
            dest_dir = os.path.join(dest_base_dir, show_name, season_folder)
            os.makedirs(dest_dir, exist_ok=True)
            try:
                os.chmod(dest_dir, 0o777)
            except Exception:
                pass

            strm_path = os.path.join(dest_dir, f"{file_base_name}.strm")
            stream_url = f"{stream_base_url.rstrip('/')}/stream?link={t_hash}&index={v_file['id']}&play\n"

            needs_write = True
            if os.path.exists(strm_path):
                try:
                    with open(strm_path, "r", encoding="utf-8") as f:
                        if f.read() == stream_url:
                            needs_write = False
                except Exception:
                    pass

            if needs_write:
                with open(strm_path, "w", encoding="utf-8") as f:
                    f.write(stream_url)
                try:
                    os.chmod(strm_path, 0o666)
                except Exception:
                    pass

            synced_paths.append(strm_path)

    if synced_paths:
        cleanup_orphaned_strm_files(t_hash, set(synced_paths), media_dir, categories)

    return synced_paths


def sync_all_torrents(
    torrents: list[dict[str, Any]],
    media_dir: str,
    stream_base_url: str,
    title_overrides: dict[str, str] | None = None,
    category_overrides: dict[str, str] | None = None,
    categories: list[Any] | None = None,
) -> dict[str, Any]:
    total_files = 0
    synced_items = 0
    all_synced_paths: set[str] = set()

    for item in torrents:
        t_hash = item.get("hash")
        override_title = title_overrides.get(t_hash) if (title_overrides and t_hash) else None
        override_cat = category_overrides.get(t_hash) if (category_overrides and t_hash) else None
        paths = sync_single_torrent(
            torrent_item=item,
            media_dir=media_dir,
            stream_base_url=stream_base_url,
            override_category=override_cat,
            override_title=override_title,
            categories=categories,
        )
        if paths:
            synced_items += 1
            total_files += len(paths)
            all_synced_paths.update(paths)

    return {
        "torrents_count": len(torrents),
        "synced_torrents": synced_items,
        "total_strm_files": total_files,
    }


def cleanup_orphaned_strm_files(
    t_hash: str,
    valid_paths: set[str],
    media_dir: str,
    categories: list[Any] | None = None,
) -> int:
    """
    Finds and deletes any .strm files referencing t_hash that are not in valid_paths.
    Also cleans up empty parent directories.
    """
    if not t_hash:
        return 0
    removed_count = 0
    pattern = f"link={t_hash}"
    norm_valid = {os.path.normpath(p) for p in valid_paths}

    for base_cat_dir in get_all_category_dirs(media_dir, categories):
        if not os.path.exists(base_cat_dir):
            continue

        for root, dirs, files in os.walk(base_cat_dir, topdown=False):
            for file in files:
                if file.endswith(".strm"):
                    file_path = os.path.normpath(os.path.join(root, file))
                    if file_path not in norm_valid:
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                            if pattern in content:
                                os.remove(file_path)
                                removed_count += 1
                        except Exception:
                            pass
            # Clean up empty directories
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

    return removed_count


def remove_torrent_files(torrent_item: dict[str, Any], media_dir: str, categories: list[Any] | None = None) -> int:
    t_hash = torrent_item.get("hash")
    if not t_hash:
        return 0
    return cleanup_orphaned_strm_files(t_hash, set(), media_dir, categories)


# ==================== ONLINE POSTER DISCOVERY ====================


def extract_poster_search_candidates(raw_title: str) -> list[str]:
    """
    Produces an ordered list of search candidate strings for Cinemeta.
    E.g. for "Молодий Папа / The Young Pope (2016)", candidates are:
    1. "The Young Pope"
    2. "Молодий Папа"
    3. "Молодий Папа The Young Pope"
    """
    if not raw_title:
        return []
    candidates = []
    if "/" in raw_title or "|" in raw_title:
        parts = re.split(r"[/|]", raw_title)
        clean_parts = [clean_media_title(p) for p in parts]
        latin_parts = [p for p in clean_parts if re.search(r"[a-zA-Z]", p) and len(p) >= 2]
        cyrillic_parts = [p for p in clean_parts if not re.search(r"[a-zA-Z]", p) and len(p) >= 2]
        candidates.extend(latin_parts)
        candidates.extend(cyrillic_parts)

    full_clean = clean_media_title(raw_title)
    if full_clean and full_clean not in candidates:
        candidates.append(full_clean)

    seen = set()
    result = []
    for c in candidates:
        c_clean = c.strip()
        if c_clean and c_clean not in seen:
            seen.add(c_clean)
            result.append(c_clean)
    return result


def extract_year(raw_title: str) -> str | None:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", raw_title)
    return m.group(1) if m else None


def score_meta(meta: dict[str, Any], candidate: str, target_year: str | None) -> int:
    name = (meta.get("name") or "").strip().lower()
    cand = candidate.strip().lower()
    if not name or not cand:
        return -1

    cand_tokens = set(re.findall(r"\w+", cand))
    name_tokens = set(re.findall(r"\w+", name))
    if not cand_tokens:
        return -1

    # Exact or substring match
    if name == cand:
        score = 100
    elif cand in name or name in cand:
        score = 60
    elif cand_tokens.issubset(name_tokens):
        score = 45
    elif len(cand_tokens & name_tokens) >= max(1, len(cand_tokens) // 2):
        score = 25
    else:
        return -1  # Reject irrelevant matches

    meta_year = str(meta.get("year") or meta.get("releaseInfo") or "")
    if target_year and target_year in meta_year:
        score += 50

    return score


async def fetch_poster_online(title: str, category: str | None = "show") -> str | None:
    import httpx

    candidates = extract_poster_search_candidates(title)
    if not candidates:
        return None

    year = extract_year(title)
    is_series = (category in ("show", "series")) or bool(
        re.search(r"\b(?:season|сезон|s\d+|сері[яї])\b", title, re.IGNORECASE)
    )
    cat_types = ["series", "movie"] if is_series else ["movie", "series"]

    best_match = None
    best_score = 0

    async with httpx.AsyncClient(timeout=6.0) as client:
        for cand in candidates:
            for cat_type in cat_types:
                url = f"https://v3-cinemeta.strem.io/catalog/{cat_type}/top/search={cand}.json"
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        data = res.json()
                        metas = data.get("metas") or []
                        for m in metas:
                            if not m.get("poster"):
                                continue
                            s = score_meta(m, cand, year)
                            if s > best_score:
                                best_score = s
                                best_match = m
                except Exception:
                    pass
            if best_match and best_score >= 100:
                break

    if best_match and best_score > 0:
        return best_match.get("poster")
    return None


# ==================== FILE STRUCTURE MANAGEMENT ====================


def find_torrent_root_folder(
    torrent_item: dict[str, Any], media_dir: str, categories: list[Any] | None = None
) -> tuple[str, str]:
    """
    Finds the root media directory for this torrent.
    Returns (abs_path, rel_path), e.g. ('/media/shows/Euphoria', 'shows/Euphoria')
    """
    t_hash = torrent_item.get("hash")
    pattern = f"link={t_hash}" if t_hash else None

    if pattern:
        for cat_dir in get_all_category_dirs(media_dir, categories):
            if not os.path.exists(cat_dir):
                continue
            for show_or_movie in os.listdir(cat_dir):
                sub_path = os.path.join(cat_dir, show_or_movie)
                if os.path.isdir(sub_path):
                    for root, dirs, files in os.walk(sub_path):
                        for f in files:
                            if f.endswith(".strm"):
                                try:
                                    with open(os.path.join(root, f), "r", encoding="utf-8") as fl:
                                        if pattern in fl.read():
                                            rel = os.path.relpath(sub_path, media_dir)
                                            return sub_path, rel
                                except Exception:
                                    pass

    # Fallback to default path based on clean title
    raw_title = torrent_item.get("title") or torrent_item.get("name") or t_hash or "Untitled"
    clean_title = clean_media_title(raw_title)
    video_files = extract_video_files(torrent_item)
    is_movie = len(video_files) <= 1

    cat_id = torrent_item.get("category")
    cat_def = None
    if categories and cat_id:
        cat_def = next(
            (c for c in categories if (c.get("id") if isinstance(c, dict) else getattr(c, "id", "")) == cat_id),
            None,
        )
    if not cat_def and categories:
        target_type = "movie" if is_movie else "show"
        cat_def = next(
            (
                c
                for c in categories
                if (c.get("type") if isinstance(c, dict) else getattr(c, "type", "")) == target_type
            ),
            None,
        )

    if cat_def:
        target_base = get_category_path(cat_def, media_dir)
    else:
        target_base = os.path.join(media_dir, "movies" if is_movie else "shows")

    target = os.path.join(target_base, clean_title)
    rel = os.path.relpath(target, media_dir)
    return target, rel


def get_media_structure(abs_root: str, rel_root: str) -> dict[str, Any]:
    """
    Returns directory tree and list of all media files for this show/movie.
    """
    if not os.path.exists(abs_root):
        return {"root_path": rel_root, "exists": False, "folders": [""], "files": []}

    folders: list[str] = [""]
    files_list: list[dict[str, Any]] = []

    for root, dirs, files in os.walk(abs_root):
        rel_dir = os.path.relpath(root, abs_root)
        if rel_dir == ".":
            rel_dir = ""
        else:
            folders.append(rel_dir)

        for f in sorted(files):
            file_abs = os.path.join(root, f)
            rel_path = os.path.join(rel_dir, f) if rel_dir else f
            files_list.append(
                {
                    "name": f,
                    "folder": rel_dir,
                    "rel_dir": rel_dir,
                    "path": rel_path,
                    "rel_path": rel_path,
                    "size": os.path.getsize(file_abs) if os.path.exists(file_abs) else 0,
                }
            )

    folders = sorted(list(set(folders)))
    return {
        "root_path": rel_root,
        "exists": True,
        "folders": folders,
        "files": files_list,
    }


def _check_safe_path(base_dir: str, rel_path: str) -> str:
    target_abs = os.path.abspath(os.path.join(base_dir, rel_path))
    base_abs = os.path.abspath(base_dir)
    if not (target_abs == base_abs or target_abs.startswith(base_abs + os.sep)):
        raise ValueError("Invalid path: traversal outside allowed directory")
    return target_abs


def create_media_folder(abs_root: str, folder_name: str) -> str:
    _check_safe_path(abs_root, folder_name)
    parts = [sanitize_filename(p) for p in folder_name.replace(chr(92), chr(47)).split("/") if p]
    if not parts or not any(parts):
        raise ValueError("Folder name cannot be empty")
    rel_path = os.path.join(*parts)
    target_dir = _check_safe_path(abs_root, rel_path)
    os.makedirs(target_dir, exist_ok=True)
    return os.path.relpath(target_dir, abs_root)


def rename_media_item(abs_root: str, old_rel_path: str, new_name_or_rel: str) -> str:
    old_abs = _check_safe_path(abs_root, old_rel_path)
    if not os.path.exists(old_abs):
        raise FileNotFoundError(f"Item not found: {old_rel_path}")

    # If new_name_or_rel is just a basename, keep same parent folder
    if "/" not in new_name_or_rel and "\\" not in new_name_or_rel:
        parent_dir = os.path.dirname(old_abs)
        new_abs = os.path.join(parent_dir, sanitize_filename(new_name_or_rel))
    else:
        new_abs = _check_safe_path(abs_root, new_name_or_rel)

    if os.path.exists(new_abs):
        raise FileExistsError(f"Target already exists: {os.path.relpath(new_abs, abs_root)}")

    os.rename(old_abs, new_abs)
    return os.path.relpath(new_abs, abs_root)


def move_media_files(abs_root: str, file_rel_paths: list[str], target_folder_rel: str) -> int:
    target_dir = _check_safe_path(abs_root, target_folder_rel.strip("/"))
    os.makedirs(target_dir, exist_ok=True)

    moved = 0
    for rel_f in file_rel_paths:
        src = _check_safe_path(abs_root, rel_f)
        if os.path.exists(src) and os.path.isfile(src):
            dst = os.path.join(target_dir, os.path.basename(src))
            if src != dst:
                shutil.move(src, dst)
                moved += 1
    return moved


def delete_media_item(abs_root: str, rel_path: str) -> bool:
    target_abs = _check_safe_path(abs_root, rel_path)
    if target_abs == os.path.abspath(abs_root):
        raise ValueError("Cannot delete root media directory")

    if not os.path.exists(target_abs):
        return False

    if os.path.isdir(target_abs):
        if not os.listdir(target_abs):
            os.rmdir(target_abs)
        else:
            shutil.rmtree(target_abs)
    else:
        os.remove(target_abs)
    return True


def rename_torrent_root_folder(abs_root: str, new_title: str) -> str | None:
    """
    Renames the show or movie root folder on disk when torrent title is renamed.
    e.g. /media/shows/OldName -> /media/shows/NewName
    """
    if not abs_root or not os.path.exists(abs_root):
        return None
    parent_dir = os.path.dirname(abs_root)
    clean_new = clean_media_title(new_title)
    if not clean_new:
        raise ValueError("Invalid new media title")
    new_abs = os.path.join(parent_dir, clean_new)
    if new_abs == abs_root:
        return abs_root
    if os.path.exists(new_abs):
        for item in os.listdir(abs_root):
            s = os.path.join(abs_root, item)
            d = os.path.join(new_abs, item)
            if not os.path.exists(d):
                shutil.move(s, d)
        if os.path.exists(abs_root) and not os.listdir(abs_root):
            shutil.rmtree(abs_root, ignore_errors=True)
    else:
        shutil.move(abs_root, new_abs)
    return new_abs


def auto_organize_seasons(abs_root: str) -> dict[str, Any]:
    """
    Intelligently detects season numbers from episode filenames (loose or scattered),
    creates standard Season XX folders, moves the files into them,
    and cleans up empty folders.
    """
    if not os.path.exists(abs_root):
        return {"status": "error", "message": "Media folder does not exist"}

    all_strm_files: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(abs_root):
        for f in files:
            if f.endswith(".strm"):
                all_strm_files.append((os.path.join(root, f), f))

    moved_count = 0
    created_folders: set[str] = set()

    for full_path, filename in all_strm_files:
        # Detect season
        season_num = None
        # Pattern S01E02 or 1x02
        m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,2})", filename)
        if not m:
            m = re.search(r"\b(\d{1,2})x(\d{1,2})\b", filename)
        if m:
            season_num = int(m.group(1))
        else:
            # Pattern Season 1, Сезон 1
            sm = re.search(r"\b(?:season|сезон)\s*(\d{1,2})\b", filename, re.IGNORECASE)
            if sm:
                season_num = int(sm.group(1))

        # Check specials
        is_special = bool(re.search(r"\b(special|спеш[еа]л|s00)\b", filename, re.IGNORECASE))
        if is_special:
            target_folder = "Season 00"
        elif season_num is not None:
            target_folder = f"Season {season_num:02d}"
        else:
            # Cannot determine season, leave untouched
            continue

        target_dir = os.path.join(abs_root, target_folder)
        os.makedirs(target_dir, exist_ok=True)
        created_folders.add(target_folder)

        target_file = os.path.join(target_dir, filename)
        if full_path != target_file:
            shutil.move(full_path, target_file)
            moved_count += 1

    # Clean up empty directories
    for root, dirs, files in os.walk(abs_root, topdown=False):
        for d in dirs:
            dir_path = os.path.join(root, d)
            try:
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
            except Exception:
                pass

    return {
        "status": "ok",
        "moved_count": moved_count,
        "folders": sorted(list(created_folders)),
    }
