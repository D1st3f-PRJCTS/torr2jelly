import json
import os
import secrets

from pydantic import BaseModel, Field

CONFIG_FILE_PATH = os.getenv("CONFIG_FILE_PATH", "/app/config/settings.json")


class MediaCategory(BaseModel):
    id: str
    name: str
    type: str = "movie"  # "movie" or "show"
    path: str = ""  # e.g. "movies", "shows", or absolute "/media/cartoons"


def get_default_categories() -> list[MediaCategory]:
    return [
        MediaCategory(id="movie", name="Movies", type="movie", path="movies"),
        MediaCategory(id="show", name="Shows", type="show", path="shows"),
    ]


class Settings(BaseModel):
    torrserver_url: str = os.getenv("TORRSERVER_URL", "http://torrserver:8090")
    jellyfin_stream_torr_url: str = os.getenv("JELLYFIN_STREAM_TORR_URL", "http://torrserver:8090")
    jellyfin_url: str = os.getenv("JELLYFIN_URL", "http://jellyfin:8096")
    jellyfin_api_key: str = os.getenv("JELLYFIN_API_KEY", "")
    prowlarr_url: str = os.getenv("PROWLARR_URL", "http://prowlarr:9696")
    prowlarr_api_key: str = os.getenv("PROWLARR_API_KEY", "")
    media_dir: str = os.getenv("MEDIA_DIR", "/media")
    categories: list[MediaCategory] = Field(default_factory=get_default_categories)
    auto_sync: bool = os.getenv("AUTO_SYNC", "true").lower() in ("true", "1", "yes")
    sync_interval: int = int(os.getenv("SYNC_INTERVAL", "30"))
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    language: str = os.getenv("LANGUAGE", "en")
    only_gold_torrents: bool = os.getenv("ONLY_GOLD_TORRENTS", "false").lower() in (
        "true",
        "1",
        "yes",
    )


def load_settings() -> Settings:
    settings = Settings()
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                settings = Settings(**saved)
        except Exception as e:
            print(f"Warning: Failed to load config from {CONFIG_FILE_PATH}: {e}")

    # Ensure categories are initialized if empty
    if not settings.categories:
        settings.categories = get_default_categories()

    # Ensure persistent JWT secret
    if not settings.jwt_secret:
        settings.jwt_secret = secrets.token_hex(32)
        try:
            save_settings(settings)
        except Exception as e:
            print(f"Warning: Could not persist generated jwt_secret: {e}")

    return settings


def save_settings(new_settings: Settings) -> None:
    os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_settings.model_dump(), f, indent=2)
