# Spotify Public Playlist Telegram Bot

# Spotify Bot — Full Fallback Chain (spotdl → yt-dlp)

A portable Python Telegram bot that:

- Accepts **public** Spotify playlist / track links
- Retrieves **metadata** via the official Spotify Web API (Client Credentials)
- Lets users preview, select tracks, request individual files or ZIP archives
- Obtains audio via a **public-source fallback chain** (no Spotify stream ripping)
- **Never** decrypts protected Spotify streams, uses private cookies, or circumvents DRM

## Audio provider chain

| Order | Provider | Behaviour |
|-------|----------|-----------|
| 1 | **SpotdlProvider** | Spotify metadata + matching public audio (via `spotdl`) |
| 2 | **YtDlpProvider** | Direct `yt-dlp` search + download, tagged with Spotify metadata |

The registry tries each provider in order. If one raises `AudioSourceUnavailable`, the next is tried. If all fail, the track is marked skipped.

## Architecture

| Component | Role |
|-----------|------|
| `playlist_reader.py` | Public metadata via spotipy (optional Client ID/Secret) |
| `audio_sources.py` | Provider interface + spotdl → yt-dlp chain |
| `download_manager.py` | Ordered jobs, cancellation, concurrency limits |
| `database.py` | SQLite for settings, jobs, track status, selections |
| `handlers/*` | aiogram 3 routers for every menu button |
| `config.py` | Environment-driven, pathlib-based, cross-platform tri |

**Playlist track-list limitation (Spotify Web API, 2025–2026):**  
Spotify only returns the songs inside a playlist when the *authorized Spotify account* owns or collaborates on that playlist.  
Client-credentials (app-only) access therefore gets playlist name/owner but an empty or missing track list for most public playlists. The bot detects this and shows a clear access-restriction message instead of a false “0 tracks”.  
Single-track URLs still work. Playlists owned by the same Spotify account that owns the app’s Client ID also work.

## Requirements

- Python 3.11+
- FFmpeg / FFprobe (required by spotdl and yt-dlp for audio conversion)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Optional: Spotify Developer app (Client ID + Secret) for metadata
- `spotdl`, `yt-dlp`, `mutagen` (installed via requirements.txt)

## Official repository

**Source & updates:** https://github.com/arehsman1/song-loader

Clone from there so you always get the latest version and can push your own updates.

## Quick start (Windows 10/11 – PowerShell)

```powershell
# 1. Install Python 3.11+ from https://www.python.org/downloads/ (check "Add to PATH")
python --version
pip --version

# 2. (Optional) Install FFmpeg – e.g. via winget or chocolatey
winget install Gyan.FFmpeg
# or download from https://ffmpeg.org/download.html and add to PATH
ffmpeg -version
ffprobe -version

# 3. Clone the project
git clone https://github.com/arehsman1/song-loader.git
cd song-loader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3b. Verify provider binaries are on PATH
where.exe spotdl yt-dlp ffmpeg
python -c "from services.audio_sources import audio_registry; print([p.name for p in audio_registry.providers])"
# Expected print: ['spotdl', 'yt-dlp']

# 4. Configuration
copy .env.example .env
# Edit .env with Notepad and set TELEGRAM_BOT_TOKEN=...
# Optionally set SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET

# 5. Run
python bot.py
```

Open Telegram, find your bot, send `/start`. Test every menu button.

**CMD equivalent activation:**

```cmd
.venv\Scripts\activate.bat
```

## Quick start (Ubuntu / Debian VPS)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git

# After creating the venv and installing requirements:
# which spotdl yt-dlp ffmpeg
# python -c "from services.audio_sources import audio_registry; print([p.name for p in audio_registry.providers])"
# Expected: ['spotdl', 'yt-dlp']

# Clone as a normal user (recommended)
git clone https://github.com/arehsman1/song-loader.git
cd song-loader

# Optional: install under a dedicated non-root user
# sudo useradd -m -s /bin/bash songloader
# sudo mkdir -p /opt/song-loader
# sudo chown songloader:songloader /opt/song-loader
# then clone into /opt/song-loader

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # set TELEGRAM_BOT_TOKEN and optional Spotify credentials
chmod 600 .env

# Test interactively
python bot.py
```

### systemd service

Create `/etc/systemd/system/song-loader.service` (adjust paths if you cloned elsewhere):

```ini
[Unit]
Description=Song Loader – Spotify Public Playlist Telegram Bot
After=network.target

[Service]
Type=simple
User=songloader
WorkingDirectory=/opt/song-loader
EnvironmentFile=/opt/song-loader/.env
ExecStart=/opt/song-loader/.venv/bin/python bot.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now song-loader
sudo systemctl status song-loader
journalctl -u song-loader -f
```

Backup database:

```bash
cp data/bot.db /path/to/backup/bot-$(date +%F).db
# or if installed under /opt:
# cp /opt/song-loader/data/bot.db /path/to/backup/bot-$(date +%F).db
```

## Docker

```bash
git clone https://github.com/arehsman1/song-loader.git
cd song-loader
cp .env.example .env
# edit .env
docker compose build
docker compose up -d
docker compose logs -f
docker compose down
```

Data persists in the named volume `bot_data`.

## Running tests

```bash
# From project root with venv active
export TELEGRAM_BOT_TOKEN=0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY   # Linux
# or in PowerShell: $env:TELEGRAM_BOT_TOKEN="0000000000:TEST_TOKEN_FOR_UNIT_TESTS_ONLY"
pytest -v
```

Tests use mocks / temporary directories and never contact Telegram or download copyrighted audio.

## Hosting notes

| Environment | Works? | Notes |
|-------------|--------|-------|
| Local Windows / Linux | Yes | Long polling |
| VPS (Ubuntu, Debian, etc.) | Yes | systemd + long polling |
| Docker | Yes | See compose file |
| Azure / Linode / most VMs | Yes | Same as VPS |
| Serverless (AWS Lambda, Cloudflare Workers, etc.) | No | No persistent process / FFmpeg / disk |
| Shared hosting without long-running processes | No | Need always-on process |

Minimum: ~100 MB disk, ability to run a persistent Python process, outbound HTTPS.

## Configuration reference

See `.env.example`. Important variables:

- `TELEGRAM_BOT_TOKEN` (required)
- `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` (required for metadata)
- `MAX_FILE_SIZE_MIB` (default 45)
- `DEFAULT_AUDIO_BITRATE` (default 320k – only applied when conversion is possible)
- `DATA_DIR` (default `./data`)

## Project layout

```
song-loader/                  # https://github.com/arehsman1/song-loader
  bot.py
  config.py
  keyboards.py
  states.py
  handlers/
  services/
  database/
  utils/
  tests/
  Dockerfile
  docker-compose.yml
  requirements.txt
  .env.example
  README.md
```

## Legal / ethical

This software is provided for legitimate use only. Do not use it to infringe copyright.  
The authors accept no responsibility for misuse.

## License

MIT – see `LICENSE`.
