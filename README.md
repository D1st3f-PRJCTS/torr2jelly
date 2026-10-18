# Torr2Jelly 🚀🍿

<p align="center">
  <img src="static/logo.png" alt="Torr2Jelly Logo" width="128" height="128" />
</p>

<p align="center">
  <strong>Stream Torrents on Jellyfin in Seconds without Waiting for Downloads</strong>
</p>

<p align="center">
  <a href="https://github.com/D1st3f-PRJCTS/torr2jelly/actions/workflows/docker-publish.yml"><img src="https://img.shields.io/github/actions/workflow/status/D1st3f-PRJCTS/torr2jelly/docker-publish.yml?branch=main&label=Build%20%26%20Publish&style=flat-square" alt="Build Status" /></a>
  <a href="https://github.com/D1st3f-PRJCTS/torr2jelly/pkgs/container/torr2jelly"><img src="https://img.shields.io/badge/Container-GHCR-blue?style=flat-square&logo=docker" alt="Docker Container" /></a>
  <img src="https://img.shields.io/badge/Version-v1.5.0-orange?style=flat-square" alt="Version 1.5.0" />
  <img src="https://img.shields.io/badge/Python-3.11+-brightgreen?style=flat-square&logo=python" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/License-MIT-purple?style=flat-square" alt="License" />
</p>

---

## 🌟 Overview

**Torr2Jelly** is a modern, lightweight bridge connecting **Prowlarr**, **TorrServer**, and **Jellyfin**. It allows users to search trackers, add torrents with one click, automatically generate `.strm` links, organize media hierarchies, and start streaming high-bitrate movies and shows directly on Jellyfin within seconds.

<p align="center">
  <img src="static/screenshot.png" alt="Torr2Jelly Web Interface" style="max-width: 100%; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1);" />
</p>

```mermaid
flowchart LR
    User([👤 User / Mobile / PC]) <--> WebUI[💻 Torr2Jelly Web UI]
    WebUI <--> Backend[⚡ FastAPI Backend]
    Backend <-->|Search & Trackers| Prowlarr[(📡 Prowlarr)]
    Backend <-->|Streams & Swarm Stats| TorrServer[(⚡ TorrServer)]
    Backend -->|Generate .strm & Category Routing| MediaDir[📁 Media Libraries]
    MediaDir --> Jellyfin[(🍿 Jellyfin Server)]
    Jellyfin <-->|Live Stream| TorrServer
```

---

## ✨ Key Features

- 🔍 **Unified Prowlarr Search**: Instant tracker search with automatic seeders/peers sorting, category filters, and live tracker badges.
- 🥇 **Freeleech & Gold Torrent Filtering**: Built-in toggle to restrict regular users to gold/freeleech torrents while admins retain full access.
- ⚡ **Instant Streaming via TorrServer**: No waiting hours for multi-gigabyte downloads. Playback starts immediately as TorrServer buffers sequential video chunks.
- 🍿 **Automated `.strm` Generation**: Intelligently detects movies vs. multi-episode series and writes clean, standardized `.strm` files into target Jellyfin libraries.
- 📁 **Multi-Category Custom Storage Paths**: Route content to dedicated folders (e.g. `/media/movies`, `/media/shows`, `/media/anime`, `/media/cartoons`) with automatic directory discovery.
- 📱 **Mobile-First Responsive Interface**: Clean dark glassmorphic design featuring isolated tab navigation (Dashboard, Torrents, Search, Magnet, Settings) and a fixed bottom thumb dock for smartphones.
- 🖼️ **Cinemeta & TMDB Poster Integration**: Automatic artwork matching with interactive visual poster picker modal.
- 📊 **Realtime Swarm & Speed Dashboard**: Live seeder/leecher counters, peer connection monitors, and realtime download/upload throughput gauges for active streams.
- 🗂️ **Interactive File Manager & Season Auto-Organizer**: Built-in directory browser with 1-click organizer that parses episode naming conventions (`S01E02`, `1x05`, etc.) into structured season folders.
- 🗑️ **Safe Torrent & Media Cleanup**: Confirmation modal with the choice to either retain or permanently delete generated `.strm` files when removing torrents.
- 👥 **Multi-User RBAC & Security**: Role-based access control (Admin / Regular User), salted SHA-256 passwords, JWT bearer tokens, and user management.
- 🌐 **Bilingual Localization**: Seamlessly switch between English and Ukrainian with a single click.

---

## ⚡ Quickstart with Docker Compose

Running Torr2Jelly is as simple as adding this service to your `docker-compose.yml`:

```yaml
services:
  torr2jelly:
    image: ghcr.io/d1st3f-prjcts/torr2jelly:latest
    container_name: torr2jelly
    restart: unless-stopped
    ports:
      - "8095:8095"
    environment:
      - TORRSERVER_URL=http://torrserver:8090
      - JELLYFIN_STREAM_TORR_URL=http://torrserver:8090
      - JELLYFIN_URL=http://jellyfin:8096
      - JELLYFIN_API_KEY=your_jellyfin_api_key
      - PROWLARR_URL=http://prowlarr:9696
      - PROWLARR_API_KEY=your_prowlarr_api_key
      - MEDIA_DIR=/media
    volumes:
      - /path/to/media:/media
      - /path/to/config:/app/config
    networks:
      - media-net

networks:
  media-net:
    name: media-net
    external: true
```

Start the container:
```bash
docker compose up -d
```

Open your browser at **`http://<server-ip>:8095`** to complete the initial admin setup and start streaming!

---

## ⚙️ Configuration Reference

All settings can be configured either through the **Settings UI** (saved persistently in `config/settings.json`) or via **environment variables**:

| Environment Variable | Default | Description |
|---|---|---|
| `PORT_BINDING` | `8095` | Host port to expose the web interface. |
| `TORRSERVER_URL` | `http://torrserver:8090` | Internal URL used by Torr2Jelly backend to communicate with TorrServer. |
| `JELLYFIN_STREAM_TORR_URL` | `http://torrserver:8090` | URL written into `.strm` files accessible by Jellyfin to stream video. |
| `JELLYFIN_URL` | `http://jellyfin:8096` | Jellyfin server URL for library refreshes. |
| `JELLYFIN_API_KEY` | `""` | Jellyfin API Key (Admin Dashboard -> API Keys). |
| `PROWLARR_URL` | `http://prowlarr:9696` | Prowlarr URL for searching torrent indexers. |
| `PROWLARR_API_KEY` | `""` | Prowlarr API Key (Settings -> General -> Security). |
| `MEDIA_DIR` | `/media` | Target root directory where `.strm` files are written. |
| `AUTO_SYNC` | `true` | Periodically scans TorrServer and refreshes library. |
| `SYNC_INTERVAL` | `30` | Interval in seconds between auto-sync checks. |
| `ONLY_GOLD_TORRENTS` | `false` | When enabled, non-admin users only see gold/freeleech torrents in search results. |
| `JWT_SECRET` | Auto-generated | Secret key used to sign JWT authentication tokens. |

---

## 🛠️ Development & Testing

Run unit and integration tests:
```bash
# Install dependencies
pip install -r requirements.txt

# Run pytest suite
pytest
```

Format and lint Python code (PEP 8):
```bash
ruff check backend tests
ruff format backend tests
```

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
