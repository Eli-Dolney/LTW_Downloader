## LearningTheWires Downloader

A **LearningTheWires**-themed desktop app to grab **audio** or **video** at the best available quality from sites supported by **yt-dlp** (YouTube 4K/8K/HDR, YouTube Music, SoundCloud, TikTok, Twitch, Vimeo, and many more). Built with Python, Tkinter, yt-dlp, FFmpeg, and the bgutil PO Token provider for reliable YouTube extraction.

## Features

- **LearningTheWires UI** — dark theme, creator-focused layout, batch URLs (one per line)
- **Max-quality video** — **Best Available**, **4K / 2160p**, **4K HDR**, **8K**, and lower presets using `bestvideo*+bestaudio` + smart format sorting (VP9/AV1 preserved, no forced H.264)
- **Original-quality audio** — **Best (original)** keeps the source codec (Opus/M4A/FLAC) with embedded metadata and cover art; MP3 bitrates still available
- **YouTube Music & SoundCloud** — audio saves to your **Music folder**; playlists get organized subfolders
- **Containers** — **Auto**: high-quality YouTube → **MKV** merge without re-encoding; **MP4** for QuickTime-friendly remux
- **Cookies** — load `cookies.txt` **or** pull cookies directly from **Chrome / Safari / Firefox / Edge / Brave**
- **Update yt-dlp** — one-click upgrade button in the app
- **Quality feedback** — shows actual resolution/codec after download; warns if below your preset
- **Playlists** — optional full playlist/album when the site supports it
- **Progress** — status line with speed/ETA while downloading
- **Check formats** — runs `yt-dlp --list-formats` for the first URL (details in the terminal)
- **Subtitles** — optional download + embed when supported
- **Persistent settings** — `~/.ltw_downloader.json`

## Requirements

- **Python 3.12+** (Homebrew: `brew install python@3.12`)
- **FFmpeg** (merge DASH video+audio, remux, metadata/thumbnail embed)
- **Node.js** (used by bgutil PO Token provider for YouTube; you likely already have it)
- **yt-dlp** + **bgutil-ytdlp-pot-provider** (installed via `requirements.txt`)

Install FFmpeg (examples):

- macOS (Homebrew): `brew install ffmpeg`
- Windows: `winget install --id Gyan.FFmpeg -e` or `choco install ffmpeg`
- Ubuntu/Debian: `sudo apt update && sudo apt install -y ffmpeg`

## Setup

```bash
cd "<path to>/LTW_Downloader"
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Or use the launch script (creates the venv automatically on first run):

```bash
chmod +x run.sh
./run.sh
```

Upgrade yt-dlp regularly (or use the **Update yt-dlp** button in the app):

```bash
.venv/bin/python -m pip install --upgrade -r requirements.txt
```

## Run

```bash
./run.sh
```

Or manually:

```bash
source .venv/bin/activate
TK_SILENCE_DEPRECATION=1 python downloader.py
```

## Usage

1. Paste one or more `http(s)` URLs (batch: one URL per line) or use **Paste** / clipboard auto-detect.
2. Pick a **Creator preset** if you want on-screen hints tuned for that workflow (optional).
3. Choose **Audio** or **Video**, then **Quality** and **Container** (video).
4. Set your **Download folder** (video) and **Music folder** (audio).
5. Toggle playlist, subtitles, cookies, and “open folder when finished” as needed.
6. **Download**. Use **Check formats** if a format error appears (see terminal output).

**Shortcuts**

- **Cmd+V / Ctrl+V** — paste into URL field
- **Cmd+Shift+V / Ctrl+Shift+V** — paste and start download
- **Cmd+Return / Ctrl+Return** — start download (when focus is in the URL box)

## YouTube: one video vs playlist in the address bar

Playlist links often look like `watch?v=VIDEO_ID&list=PLAYLIST_ID&index=…`.

- **“Download full playlist” off (default):** the app removes `list` / `index` from the URL and tells yt-dlp **not** to expand the playlist, so you get **only that one video**.
- **On:** yt-dlp downloads the **entire playlist** when the URL is treated as a playlist, and uses the playlist folder layout when metadata is available.

## YouTube 4K / 8K / HDR notes

- **Best Available** and resolution presets use **`bestvideo*+bestaudio`** with format sorting so DASH 4K/8K (VP9, AV1, HDR) is preferred over lower H.264 tiers.
- **4K HDR** prefers streams where yt-dlp reports non-SDR `dynamic_range`; falls back to best 2160p SDR.
- **Auto** container on YouTube for high tiers merges to **MKV** without re-encoding.
- If formats are capped at ≤720p, the app automatically retries with `tv_downgraded` + `android_vr` player clients.
- The **bgutil PO Token provider** plugin is bundled to help with YouTube bot checks (requires Node.js on PATH).

## Audio: YouTube Music / SoundCloud

- **Best (original)** is the default — keeps the source audio codec and embeds metadata + cover art.
- Audio downloads save to your **Music folder** (set via **Browse music**).
- MP3 bitrate presets (320/256/192/128/96/64 kbps) are still available when you need compatibility.
- **SoundCloud Go+ / HQ** tracks may require cookies from your logged-in browser.

## Cookies (optional)

Two options:

1. **Browser dropdown** — select Chrome, Safari, Firefox, Edge, or Brave to use `cookies-from-browser` (easiest for age-gated, Premium, or SoundCloud Go+ content).
2. **Load cookies…** — pick a Netscape-format `cookies.txt` exported from your browser.

Cookies are read **only on your machine** by yt-dlp; do not commit them to git.

## Troubleshooting

- **YouTube “SABR” / few formats / 403** — click **Update yt-dlp** or run `pip install --upgrade -r requirements.txt`. Try **Browser cookies** or a `cookies.txt`. Ensure Node.js is installed for the PO Token provider.
- **“Requested format is not available”** — update yt-dlp and try **Check formats**.
- **Downloaded lower than expected** — check the status line after download; try cookies or a different quality preset.
- **FFmpeg not found** — install FFmpeg and ensure `ffmpeg -version` works on your PATH.
- **DRM (Netflix, Disney+, Prime Video, Spotify, etc.)** — not supported; the app blocks many DRM streaming domains early.
- **SoundCloud** — if you see stuck `.part` fragments, upgrade yt-dlp/FFmpeg and try browser cookies for Go+ tracks.
- **No progress bar** — resize the window once to refresh layout.

## Security & privacy

- Clipboard is read only when you paste or when **auto-detect URL** is enabled, to fill the URL field. Nothing is uploaded by this app.
- Settings and optional cookie path are stored in **`~/.ltw_downloader.json`** (do not share that file if it contains a cookie path you consider sensitive).
- Browser cookie access is local only via yt-dlp.
- Output files are written only to folders you choose.

## Notes

Use this tool only when you have the right to download the content. Some sites use DRM; those streams are not supported here.
