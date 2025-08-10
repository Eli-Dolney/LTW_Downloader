## LTW YouTube Downloader

A tiny desktop app to download YouTube audio (MP3) or video (MP4) with a clean, simple UI. Built with Python and yt-dlp.

## Features

- **Audio (MP3)** or **Video (MP4)** downloads
- **Quality** selection for video (Best/1080p/720p/480p/360p)
- **Playlist** support (toggle to grab a full playlist when available)
- **Choose save folder** (defaults to `downloads/` inside the app directory)
- **Progress + ETA** while downloading
- **QuickTime-friendly** MP4 output on macOS (H.264/AAC with faststart)

## Requirements

- **Python 3.9+** (3.10+ recommended)
- **FFmpeg** (needed for audio extraction/merging and MP4 compatibility)

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

- Copy a YouTube link and click **Paste** (or use **Cmd+V/Ctrl+V**).
- Choose **Audio (MP3)** or **Video (MP4)**. If Video, pick a **Quality**.
- Optionally enable **Download full playlist**.
- Click **Download**. Watch the progress and ETA in the status line.
- Click **Open Folder** to view results.

Keyboard shortcuts:

- **Enter**: Start download
- **Cmd+V / Ctrl+V**: Paste URL

## Troubleshooting

- **No UI / all gray on macOS**: Resize the window once. If you’re on very old macOS system Tk, the app uses plain Tk widgets to avoid blank rendering.
- **No progress bar**: Try resizing the window once to force a layout; the bar initializes after the first layout.
- **QuickTime warning on MP4**: The app targets MP4 (H.264/AAC) with faststart. If you still see a warning for a specific video, try a lower quality or re-open the file after macOS finishes indexing. You can also re-encode externally with HandBrake.
- **FFmpeg not found**: Install it (see Requirements) and make sure it’s on your PATH. Verify with `ffmpeg -version`.

## Notes

- Use this tool responsibly and only download content when you have the rights to do so.


