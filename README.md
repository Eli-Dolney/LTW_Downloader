## LTW Video Downloader

A tiny desktop app to download audio (MP3) or video (MP4) from sites supported by yt-dlp (YouTube, TikTok, and many more) with a clean, simple UI. Built with Python and yt-dlp.

## Features

- **Audio (MP3)** or **Video (MP4)** downloads
- **Quality** selection for video (Best/1080p/720p/480p/360p)
- **Playlist** support (toggle to grab a full playlist when available)
- **Choose save folder** (defaults to `downloads/` inside the app directory)
- **Progress + ETA** while downloading
- **QuickTime-friendly** MP4 output on macOS (H.264/AAC with faststart)
- **Auto-detect URL from clipboard** (toggleable) and one-tap **Paste**
- **“Open folder when finished”** option
- **Filename template**: `Platform - Uploader - Title.ext` for easy attribution
- **Cookies loader** for sites like TikTok/private videos (optional)
- **Open File** button to reveal the last downloaded file
- **Optional subtitles** download/embedding (SRT when available)
- **Persistent settings** in `~/.ltw_downloader.json`
- **Cmd+Shift+V / Ctrl+Shift+V**: Paste from clipboard and start download immediately

## Requirements

- **Python 3.9+** (3.10+ recommended)
- **FFmpeg** (needed for audio extraction/merging and MP4 compatibility)
- **yt-dlp** (installed via pip below)

Install FFmpeg:

- macOS (Homebrew):
  ```bash
  brew install ffmpeg
  ```
- Windows (winget or choco):
  ```powershell
  winget install --id Gyan.FFmpeg -e
  # or
  choco install ffmpeg
  ```
- Ubuntu/Debian:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- Fedora:
  ```bash
  sudo dnf install -y ffmpeg
  ```

## Setup

1) Download or clone this repo, then open a terminal and **cd into the project folder**:

```bash
cd "<path to>/LTW_Downloader"
```

2) (Optional but recommended) Create/activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
```

3) Install dependencies:

```bash
python3 -m pip install --upgrade pip yt-dlp
```

Keep `yt-dlp` up to date as sites change frequently:

```bash
python3 -m pip install --upgrade yt-dlp
```

## Run

Run the app from the project directory:

```bash
python3 downloader.py
```

On macOS you may see a Tk deprecation warning; it’s harmless. If you want to hide it:

```bash
TK_SILENCE_DEPRECATION=1 python3 downloader.py
```

## Usage

- Copy a supported link (YouTube, TikTok, etc.) and click **Paste** (or use **Cmd+V/Ctrl+V**). If auto-detect is on, the URL appears automatically when the app gains focus.
- Choose **Audio (MP3)** or **Video (MP4)**. If Video, pick a **Quality**.
- Optionally enable **Download full playlist**.
- Click **Download**. Watch the progress and ETA in the status line.
- Click **Open Folder** to view results or **Open File** to reveal the exact file.

Keyboard shortcuts:

- **Enter**: Start download
- **Cmd+V / Ctrl+V**: Paste URL
- **Cmd+Shift+V / Ctrl+Shift+V**: Paste and start download immediately

## Subtitles

Enable the “Download subtitles (if available)” toggle for videos to save and embed SRT subtitles when supported.

## Cookies (TikTok/private)

Use the **Load Cookies…** button to select a `cookies.txt` exported from your browser (e.g., using browser extensions that export cookies). The app won’t upload cookies; they are read locally to authenticate requests.

## Troubleshooting

- **No UI / all gray on macOS**: Resize the window once. If you’re on very old macOS system Tk, the app uses plain Tk widgets to avoid blank rendering.
- **No progress bar**: Try resizing the window once to force a layout; the bar initializes after the first layout.
- **QuickTime warning on MP4**: The app targets MP4 (H.264/AAC) with faststart. If you still see a warning for a specific video, try a lower quality or re-open the file after macOS finishes indexing. You can also re-encode externally with HandBrake.
- **FFmpeg not found**: Install it (see Requirements) and make sure it’s on your PATH. Verify with `ffmpeg -version`.

- **DRM streaming (Netflix, Disney+, Prime, etc.)**: Not supported. The app blocks these early; partial previews may be unencrypted, but full streams are protected.

## Security & Privacy

- The app can **read your clipboard** when “Auto-detect URL from clipboard” is enabled, solely to prefill the URL field. Nothing is sent anywhere.
- Settings are saved locally in `~/.ltw_downloader.json`.
- If you load a `cookies.txt`, it is used locally by yt-dlp and is not uploaded. Do not commit your cookies file to source control.
- Output files are written to your chosen folder; no telemetry or analytics.

## Notes

- Use this tool responsibly and only download content when you have the rights to do so.

Some sites and content are protected by DRM and are not supported.


