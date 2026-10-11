# Spotify Public Playlist Telegram Bot

A portable Python Telegram bot that:

- Accepts **public** Spotify playlist / track links
- Retrieves **metadata only** via the official Spotify Web API (Client Credentials)
- Lets users preview, select tracks, request individual files or ZIP archives
- Obtains audio **only** from an authorized provider interface
- **Never** rips protected Spotify streams or circumvents DRM

By design, the default audio provider reports every commercial track as unavailable.  
Public playlist visibility does **not** grant download rights.

## Architecture (Stage 1 summary)

| Component | Role |
|-----------|------|
| `playlist_reader.py` | Public metadata via spotipy (optional Client ID/Secret) |
| `audio_sources.py` | Provider interface + `UnavailableProvider` (default) |
| `download_manager.py` | Ordered jobs, cancellation, concurrency limits |
| `database.py` | SQLite for settings, jobs, track status, selections |
| `handlers/*` | aiogram 3 routers for every menu button |
| `config.py` | Environment-driven, pathlib-based, cross-platform |

**Audio limitation:** There is no legitimate free source that supplies the exact commercial Spotify catalogue for bulk download. The bot therefore never pretends a download succeeded. You can register additional providers in `audio_sources.py` if you have licensed or user-owned content.

## Requirements

- Python 3.11+
- FFmpeg / FFprobe (optional; only needed if a real provider supplies non-MP3 files)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Optional: Spotify Developer app (Client ID + Secret) for metadata

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

# 3. Project setup
cd path\to\spotify_playlist_bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

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
sudo apt install -y python3 python3-venv python3-pip ffmpeg

sudo useradd -m -s /bin/bash spotifybot   # non-root user
sudo mkdir -p /opt/spotify_playlist_bot
sudo chown spotifybot:spotifybot /opt/spotify_playlist_bot

# As spotifybot (or copy files then chown)
cd /opt/spotify_playlist_bot
# place project files here
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

Create `/etc/systemd/system/spotify-playlist-bot.service`:

```ini
[Unit]
Description=Spotify Playlist Telegram Bot
After=network.target

[Service]
Type=simple
User=spotifybot
WorkingDirectory=/opt/spotify_playlist_bot
EnvironmentFile=/opt/spotify_playlist_bot/.env
ExecStart=/opt/spotify_playlist_bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-playlist-bot
sudo systemctl status spotify-playlist-bot
journalctl -u spotify-playlist-bot -f
```

Backup database:

```bash
cp /opt/spotify_playlist_bot/data/bot.db /path/to/backup/bot-$(date +%F).db
```

## Docker

```bash
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
spotify_playlist_bot/
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
