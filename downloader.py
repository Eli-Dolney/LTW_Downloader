
import os
import re
import json
import sys
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from yt_dlp import YoutubeDL
import html
import warnings
import glob

# ----------------- Save folder -----------------
CONFIG_PATH = os.path.expanduser("~/.ltw_downloader.json")

# Default folders (relative to app directory — users can change in the UI)
downloads_folder = os.path.join(os.getcwd(), "downloads")
music_folder = os.path.join(os.getcwd(), "music")
save_folder = downloads_folder

# Create folders if they don't exist
os.makedirs(downloads_folder, exist_ok=True)
os.makedirs(music_folder, exist_ok=True)

# State tracked across the session
last_downloaded_path = ""  # absolute path to the most recent file
URL_PLACEHOLDER = "Paste URLs (YouTube, TikTok, Twitch, web) — one per line for batch downloads"
url_has_placeholder = True
# Populated in GUI section (multiline URL entry)
url_text = None
# URL field colors (set before any placeholder callbacks run)
URL_FG_PLACEHOLDER = "#777777"
URL_FG_NORMAL = "#111111"
URL_INSERT = "#111111"

# Streaming services that are DRM-protected and not supported by yt-dlp
UNSUPPORTED_DRM_DOMAINS = (
    "netflix.com",
    "disneyplus.com",
    "hulu.com",
    "primevideo.com",
    "amazonprimevideo.com",
    "max.com",  # HBO Max
    "hbomax.com",
    "tv.apple.com",
    "paramountplus.com",
    "peacocktv.com",
    "starz.com",
    "showtime.com",
    "crunchyroll.com",
    "funimation.com",
    "vrv.co",
    "tubitv.com",
    "plutotv.com",
    "kanopy.org",
    "hoopla.com",
    "kanal5play.se",
    "mtvplay.tv",
)

# Supported platforms with special configurations
SUPPORTED_PLATFORMS = {
    "youtube.com": {"name": "YouTube", "max_quality": "8K", "features": ["4K", "HDR", "subs", "playlist"]},
    "youtu.be": {"name": "YouTube", "max_quality": "8K", "features": ["4K", "HDR", "subs", "playlist"]},
    "music.youtube.com": {"name": "YouTube Music", "max_quality": "audio", "features": ["HQ", "playlist"]},
    "tiktok.com": {"name": "TikTok", "max_quality": "1080p", "features": ["HD", "subs"]},
    "instagram.com": {"name": "Instagram", "max_quality": "1080p", "features": ["HD", "stories", "reels"]},
    "twitter.com": {"name": "Twitter/X", "max_quality": "1080p", "features": ["HD", "spaces"]},
    "x.com": {"name": "Twitter/X", "max_quality": "1080p", "features": ["HD", "spaces"]},
    "soundcloud.com": {"name": "SoundCloud", "max_quality": "audio", "features": ["HQ", "playlist"]},
    "bandcamp.com": {"name": "Bandcamp", "max_quality": "audio", "features": ["HQ", "album"]},
    "vimeo.com": {"name": "Vimeo", "max_quality": "4K", "features": ["4K", "subs"]},
    "dailymotion.com": {"name": "Dailymotion", "max_quality": "1080p", "features": ["HD"]},
    "twitch.tv": {"name": "Twitch", "max_quality": "1080p", "features": ["live", "clips", "vod"]},
    "reddit.com": {"name": "Reddit", "max_quality": "1080p", "features": ["HD"]},
    "pornhub.com": {"name": "Pornhub", "max_quality": "4K", "features": ["4K", "HD"]},
    "xvideos.com": {"name": "Xvideos", "max_quality": "1080p", "features": ["HD"]},
    "xhamster.com": {"name": "xHamster", "max_quality": "1080p", "features": ["HD"]},
}

# ----------------- Helpers -----------------
def open_folder(path):
    if sys.platform.startswith("darwin"):
        subprocess.call(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.call(["xdg-open", path])

def reveal_in_finder(path):
    """Reveal a file in the system file explorer if possible."""
    if not path:
        return
    if sys.platform.startswith("darwin"):
        subprocess.call(["open", "-R", path])
    elif os.name == "nt":
        subprocess.call(["explorer", "/select,", path])
    else:
        subprocess.call(["xdg-open", os.path.dirname(path)])

def _youtube_strip_playlist_params(url: str) -> str:
    """Remove list/index context from YouTube watch URLs so yt-dlp fetches one video only."""
    if not url or not isinstance(url, str):
        return url
    try:
        p = urlparse(url.strip())
        host = (p.netloc or "").lower()
        path = (p.path or "").lower()
        q = parse_qs(p.query, keep_blank_values=True)
        if host.endswith("youtu.be"):
            for k in ("list", "index", "start_radio", "pp"):
                q.pop(k, None)
            new_q = urlencode(q, doseq=True)
            return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
        if "youtube.com" in host or "youtube-nocookie.com" in host:
            if "/watch" not in path and "/live/" not in path:
                return url
            if not q.get("v") or not (q.get("v")[0] if q.get("v") else ""):
                return url
            for k in ("list", "index", "start_radio", "pp"):
                q.pop(k, None)
            new_q = urlencode(q, doseq=True)
            return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
        return url
    except Exception:
        return url


def _js_runtime_options():
    """Prefer Node.js for yt-dlp EJS; fall back to deno if installed."""
    node = shutil.which("node")
    if node:
        return {"node": {"path": node}}
    deno = shutil.which("deno")
    if deno:
        return {"deno": {"path": deno}}
    return {"deno": {}}


def detect_platform(url):
    """Detect the platform from URL for platform-specific optimizations."""
    if not url:
        return "unknown"
    try:
        domain = urlparse(url).netloc.lower()
        for platform_domain in SUPPORTED_PLATFORMS:
            if platform_domain in domain:
                return platform_domain
        return "unknown"
    except:
        return "unknown"


# Video quality presets (order shown in UI)
VIDEO_QUALITY_OPTIONS = [
    "Best Available",
    "4K / 2160p",
    "4K HDR",
    "8K",
    "1440p",
    "1080p",
    "720p",
    "Social / Fast",
    "480p",
    "360p",
]

CREATOR_PRESET_OPTIONS = [
    "Auto-detect",
    "YouTube / webdev",
    "YouTube Shorts",
    "TikTok / Reels",
    "Twitch clips / VOD",
    "General web",
]

# Map legacy / saved labels to current preset names
QUALITY_LEGACY_ALIASES = {
    "Ultra 4K": "4K / 2160p",
    "Best": "Best Available",
    "4K": "4K / 2160p",
}

AUDIO_QUALITY_OPTIONS = [
    "Best (original)",
    "320kbps",
    "256kbps",
    "192kbps",
    "128kbps",
    "96kbps",
    "64kbps",
]

AUDIO_QUALITY_LEGACY_ALIASES = {
    "Best": "Best (original)",
}

COOKIES_BROWSER_OPTIONS = [
    "None",
    "Chrome",
    "Safari",
    "Firefox",
    "Edge",
    "Brave",
]


def normalize_video_quality(label: str) -> str:
    if not label:
        return "Best Available"
    mapped = QUALITY_LEGACY_ALIASES.get(label, label)
    if mapped not in VIDEO_QUALITY_OPTIONS:
        return "Best Available"
    return mapped


def _height_cap_for_quality(label: str):
    """Return max height int or None for uncapped."""
    caps = {
        "Best Available": None,
        "4K / 2160p": 2160,
        "4K HDR": 2160,
        "8K": 4320,
        "1440p": 1440,
        "1080p": 1080,
        "720p": 720,
        "Social / Fast": 720,
        "480p": 480,
        "360p": 360,
    }
    return caps.get(label)


def normalize_audio_quality(label: str) -> str:
    if not label:
        return "Best (original)"
    mapped = AUDIO_QUALITY_LEGACY_ALIASES.get(label, label)
    if mapped not in AUDIO_QUALITY_OPTIONS:
        return "Best (original)"
    return mapped


def is_original_audio_quality(label: str) -> bool:
    return normalize_audio_quality(label) == "Best (original)"


def format_sort_for_video(label, url=""):
    """Return yt-dlp format_sort fields that prefer max quality within the preset cap."""
    label = normalize_video_quality(label)
    sorts = []
    if label == "4K HDR":
        sorts.extend(["dynamic_range:hdr", "res:2160"])
    elif label == "8K":
        sorts.append("res:4320")
    elif label == "4K / 2160p":
        sorts.append("res:2160")
    elif label == "1440p":
        sorts.append("res:1440")
    elif label == "1080p":
        sorts.append("res:1080")
    elif label in ("720p", "Social / Fast"):
        sorts.append("res:720")
    elif label == "480p":
        sorts.append("res:480")
    elif label == "360p":
        sorts.append("res:360")
    sorts.extend(["fps", "hdr", "vcodec:vp9.2", "vcodec:av1", "vcodec:vp9", "acodec", "channels"])
    return sorts


def format_for_video(label, url=""):
    """Return a yt-dlp format selector with progressive fallback via bestvideo*."""
    label = normalize_video_quality(label)
    if label == "4K HDR":
        return (
            "bestvideo*[dynamic_range!=SDR]+bestaudio*/"
            "bestvideo*+bestaudio/best"
        )
    return "bestvideo*+bestaudio/best"


def _youtube_max_available_height(url, base_opts):
    """Probe available formats and return the highest reported video height."""
    probe_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": base_opts.get("noplaylist", True),
        "js_runtimes": base_opts.get("js_runtimes") or _js_runtime_options(),
    }
    for key in ("cookiefile", "cookiesfrombrowser"):
        if key in base_opts:
            probe_opts[key] = base_opts[key]
    try:
        with YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        heights = [f.get("height") or 0 for f in (info.get("formats") or [])]
        return max(heights) if heights else 0
    except Exception as exc:
        print(f"[YouTube probe] Could not inspect formats: {exc}")
        return 0


def _apply_youtube_fallback_clients(ydl_opts):
    """Retry path when YouTube only exposes low-tier formats."""
    extractor_args = dict(ydl_opts.get("extractor_args") or {})
    extractor_args["youtube"] = {
        "player_client": ["tv_downgraded", "android_vr"],
        "comment_sort": ["top"],
        "max_comments": [0],
    }
    ydl_opts["extractor_args"] = extractor_args
    print("[YouTube] Retrying with tv_downgraded,android_vr player clients for higher quality.")


def _ffprobe_stream_info(filepath):
    """Return basic video stream metadata from ffprobe."""
    if not filepath or not os.path.isfile(filepath):
        return None
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "v:0",
            filepath,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        return {
            "width": stream.get("width"),
            "height": stream.get("height"),
            "codec": stream.get("codec_name"),
            "fps": stream.get("r_frame_rate"),
            "pix_fmt": stream.get("pix_fmt"),
        }
    except Exception:
        return None


def _report_download_quality(filepath, requested_label, mode):
    """Log actual downloaded quality and return a short UI summary."""
    if mode != "video":
        return ""
    info = _ffprobe_stream_info(filepath)
    if not info:
        return ""
    height = info.get("height") or 0
    width = info.get("width") or 0
    codec = info.get("codec") or "unknown"
    fps = info.get("fps") or "?"
    stream_msg = f"{width}x{height} {codec} @ {fps}"
    print(f"[Quality] Stream: {stream_msg}")

    requested = normalize_video_quality(requested_label)
    cap = _height_cap_for_quality(requested)
    if cap and height and height < int(cap * 0.85):
        warn = f"Downloaded {height}p but preset was {requested}."
        print(f"[Quality warning] {warn}")
        return f"⚠️ {warn}"
    return f"📊 {stream_msg}"


def apply_video_output_options(ydl_opts, quality_label, video_format_choice, platform, url):
    """Configure merge/remux for video: avoid unnecessary re-encoding; MKV for high-quality YouTube."""
    q = normalize_video_quality(quality_label)
    is_youtube = platform in ("youtube.com", "youtu.be")
    high_youtube_mkv = frozenset({"Best Available", "4K / 2160p", "4K HDR", "8K"})
    merger_basic = {
        "FFmpegMerger": ["-y"],
        "FFmpegVideoRemuxer": ["-y"],
        "FFmpegEmbedSubtitle": ["-y"],
    }
    merger_mp4 = {
        "FFmpegMerger": ["-y", "-movflags", "+faststart"],
        "FFmpegVideoRemuxer": ["-y", "-movflags", "+faststart"],
        "FFmpegEmbedSubtitle": ["-y"],
    }
    vf = (video_format_choice or "Auto").strip()

    if vf == "Auto":
        if is_youtube and q in high_youtube_mkv:
            ydl_opts["merge_output_format"] = "mkv"
            ydl_opts["recode_video"] = None
            ydl_opts["postprocessor_args"] = dict(merger_basic)
        elif platform == "vimeo.com":
            ydl_opts["merge_output_format"] = "webm"
            ydl_opts["recode_video"] = None
            ydl_opts["postprocessor_args"] = dict(merger_basic)
        else:
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["recode_video"] = None
            ydl_opts["postprocessor_args"] = dict(merger_mp4)
    elif vf == "MP4":
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["recode_video"] = None
        ydl_opts["postprocessor_args"] = dict(merger_mp4)
    elif vf == "MKV":
        ydl_opts["merge_output_format"] = "mkv"
        ydl_opts["recode_video"] = None
        ydl_opts["postprocessor_args"] = dict(merger_basic)
    elif vf == "WebM":
        ydl_opts["merge_output_format"] = "webm"
        ydl_opts["recode_video"] = None
        ydl_opts["postprocessor_args"] = dict(merger_basic)
    else:
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["recode_video"] = None
        ydl_opts["postprocessor_args"] = dict(merger_mp4)


def creator_preset_hint(preset: str, url: str) -> str:
    """Short UI hint for the selected creator preset (does not change yt-dlp unless URL implies Shorts)."""
    u = (url or "").lower()
    preset = (preset or "Auto-detect").strip()
    if preset == "Auto-detect":
        if "/shorts/" in u and ("youtube.com" in u or "youtu.be" in u):
            return "Context: YouTube Shorts — vertical clip; 1080p is often the max."
        if "tiktok.com" in u or "instagram.com" in u:
            return "Context: short-form — server max is often 1080p; Social / Fast works well."
        if "clips.twitch.tv" in u or "/clip/" in u:
            return "Context: Twitch clip — grab highest transcode available."
        if "twitch.tv" in u:
            return "Context: Twitch VOD/live — quality depends on the stream."
        return ""
    hints = {
        "YouTube / webdev": "Preset: long-form YouTube — use 4K / 2160p or Best Available for tutorials.",
        "YouTube Shorts": "Preset: Shorts — vertical; Best Available or 1080p is usually enough.",
        "TikTok / Reels": "Preset: short vertical — best available from server (often ≤1080p).",
        "Twitch clips / VOD": "Preset: Twitch — clips and VODs use different pipelines; Best Available.",
        "General web": "Preset: any yt-dlp-supported page — quality varies by host.",
    }
    return hints.get(preset, "")

# ----------------- Settings Persistence -----------------
def load_settings():
    global save_folder, music_folder
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("save_folder"), str) and data.get("save_folder"):
            save_folder_candidate = data["save_folder"]
            if os.path.isdir(save_folder_candidate):
                save_folder = save_folder_candidate
        if isinstance(data.get("music_folder"), str) and data.get("music_folder"):
            music_folder_candidate = data["music_folder"]
            if os.path.isdir(music_folder_candidate):
                music_folder = music_folder_candidate
        # Defer UI variable assignment until after widgets are built
        return data
    except Exception:
        return {}

def save_settings(extra = None):
    try:
        data = {
            "save_folder": save_folder,
            "music_folder": music_folder,
            "auto_open": int(auto_open_var.get()) if 'auto_open_var' in globals() else 0,
            "auto_detect_clipboard": int(auto_detect_clipboard_var.get()) if 'auto_detect_clipboard_var' in globals() else 1,
            "mode": mode_var.get() if 'mode_var' in globals() else 'audio',
            "quality": quality_var.get() if 'quality_var' in globals() else 'Best Available',
            "audio_quality": audio_quality_var.get() if 'audio_quality_var' in globals() else 'Best (original)',
            "format": format_var.get() if 'format_var' in globals() else 'Auto',
            "playlist": int(playlist_var.get()) if 'playlist_var' in globals() else 0,
            "subtitles": int(subs_var.get()) if 'subs_var' in globals() else 0,
            "source_preset": source_preset_var.get() if 'source_preset_var' in globals() else 'Auto-detect',
            "cookie_file": (cookie_file_var.get() if 'cookie_file_var' in globals() else "").strip(),
            "cookies_browser": cookies_browser_var.get() if 'cookies_browser_var' in globals() else 'None',
        }
        if extra:
            data.update(extra)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# ----------------- Download -----------------
def _safe_component(name: str) -> str:
    """Return a filesystem-safe folder/file component."""
    if not isinstance(name, str):
        name = str(name)
    # Replace invalid filename characters on major OSes
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    # Strip leading/trailing whitespace and dots
    name = name.strip().strip(".")
    # Collapse duplicate underscores/spaces
    name = re.sub(r"[\s_]+", " ", name).strip()
    return name or "unknown"


def _srt_to_plain_text(srt_content: str) -> str:
    """Convert SRT content to plain text by removing indices, timestamps, and markup."""
    # Normalize line endings
    text = srt_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        line = raw.strip("\ufeff ")  # remove BOM and trim spaces
        # Skip index lines (a single number) and timestamp lines
        if re.fullmatch(r"\d+", line):
            continue
        if "-->" in line:
            continue
        # Remove simple HTML tags often present in subtitles
        line = re.sub(r"<[^>]+>", "", line)
        # Unescape HTML entities
        line = html.unescape(line)
        lines.append(line)

    # Collapse blocks separated by blank lines; join lines within a block with spaces
    paragraphs = []
    block = []
    for line in lines:
        if line:
            block.append(line)
        else:
            if block:
                paragraphs.append(" ".join(block))
                block = []
    if block:
        paragraphs.append(" ".join(block))
    # Join paragraphs with blank line between
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())


def _convert_srt_file_to_txt(srt_path: str):
    """Create a .txt transcript next to the .srt file. Returns txt path or None on failure."""
    try:
        with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        plain = _srt_to_plain_text(content)
        txt_path = os.path.splitext(srt_path)[0] + ".txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(plain.strip() + "\n")
        return txt_path
    except Exception:
        return None


def _convert_vtt_to_plain_text(vtt_content: str) -> str:
    """Convert VTT content to plain text by removing timestamps and markup."""
    # Normalize line endings
    text = vtt_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        # Skip VTT header
        if line == "WEBVTT" or line.startswith("WEBVTT"):
            continue
        # Skip index lines (a single number)
        if re.fullmatch(r"\d+", line):
            continue
        # Skip timestamp lines (VTT format: 00:00:00.000 --> 00:00:00.000)
        if "-->" in line or re.match(r"\d{2}:\d{2}:\d{2}", line):
            continue
        # Skip style/cue settings
        if line.startswith("STYLE") or line.startswith("NOTE") or line.startswith("::"):
            continue
        # Remove simple HTML tags often present in subtitles
        line = re.sub(r"<[^>]+>", "", line)
        # Remove VTT-specific markup like <c>, </c>, etc.
        line = re.sub(r"</?c[^>]*>", "", line)
        # Unescape HTML entities
        line = html.unescape(line)
        if line:
            lines.append(line)

    # Collapse blocks separated by blank lines; join lines within a block with spaces
    paragraphs = []
    block = []
    for line in lines:
        if line:
            block.append(line)
        else:
            if block:
                paragraphs.append(" ".join(block))
                block = []
    if block:
        paragraphs.append(" ".join(block))
    # Join paragraphs with blank line between
    return "\n\n".join(p.strip() for p in paragraphs if p.strip())

def _convert_vtt_file_to_txt(vtt_path: str):
    """Create a .txt transcript next to the .vtt file. Returns txt path or None on failure."""
    try:
        with open(vtt_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        plain = _convert_vtt_to_plain_text(content)
        txt_path = os.path.splitext(vtt_path)[0] + ".txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(plain.strip() + "\n")
        return txt_path
    except Exception:
        return None

def _convert_srts_in_directory(base_dir: str):
    """Find all .srt and .vtt files in base_dir and ensure fresh .txt transcripts exist next to each."""
    for root_dir, _dirs, files in os.walk(base_dir):
        for filename in files:
            file_path = os.path.join(root_dir, filename)
            txt_path = None
            
            if filename.lower().endswith(".srt"):
                txt_path = os.path.splitext(file_path)[0] + ".txt"
                try:
                    if not os.path.exists(txt_path) or os.path.getmtime(txt_path) < os.path.getmtime(file_path):
                        _convert_srt_file_to_txt(file_path)
                except Exception:
                    pass
            
            elif filename.lower().endswith(".vtt"):
                txt_path = os.path.splitext(file_path)[0] + ".txt"
                try:
                    if not os.path.exists(txt_path) or os.path.getmtime(txt_path) < os.path.getmtime(file_path):
                        _convert_vtt_file_to_txt(file_path)
                except Exception:
                    pass

def _organize_video_downloads(base_dir: str):
    """Organize video downloads: ensure MP4, VTT, SRT, and TXT files are all in the same video folder."""
    try:
        import shutil
        # Walk through all directories and files
        for root_dir, dirs, files in os.walk(base_dir):
            # Look for video files (MP4, MKV, WebM, etc.)
            video_files = [f for f in files if f.lower().endswith(('.mp4', '.mkv', '.webm', '.m4v', '.avi', '.mov'))]
            
            for video_file in video_files:
                video_path = os.path.join(root_dir, video_file)
                video_basename = os.path.splitext(video_file)[0]
                
                # Extract clean basename (remove language codes like .en-US if present)
                clean_basename = video_basename.split('.')[0] if '.' in video_basename else video_basename
                
                # Determine target video folder
                current_folder_name = os.path.basename(root_dir)
                
                # Check if we're already in a video-specific folder
                # (match if folder name starts with video name, allowing for slight variations)
                is_in_video_folder = (clean_basename[:40].lower() in current_folder_name.lower() or 
                                     current_folder_name[:40].lower() in clean_basename.lower())
                
                if not is_in_video_folder:
                    # Create a folder for this video using clean basename
                    video_folder = os.path.join(root_dir, clean_basename)
                    os.makedirs(video_folder, exist_ok=True)
                    video_dir = video_folder
                    
                    # Move video file to its folder
                    new_video_path = os.path.join(video_dir, video_file)
                    if os.path.exists(video_path) and video_path != new_video_path and not os.path.exists(new_video_path):
                        try:
                            shutil.move(video_path, new_video_path)
                        except Exception as e:
                            print(f"Could not move video {video_file}: {e}")
                else:
                    video_dir = root_dir
                
                # Find and move related subtitle and transcript files
                # Look for files that match the video basename (with variations)
                for file in files:
                    file_lower = file.lower()
                    file_basename_lower = os.path.splitext(file)[0].lower()
                    
                    # Check if this file belongs to this video
                    matches_video = (file_basename_lower.startswith(clean_basename.lower()[:30]) or
                                    clean_basename.lower()[:30] in file_basename_lower or
                                    file_basename_lower == video_basename.lower())
                    
                    if matches_video and file != video_file:
                        file_ext = os.path.splitext(file)[1].lower()
                        
                        if file_ext in ['.srt', '.vtt', '.txt']:
                            source_path = os.path.join(root_dir, file)
                            dest_path = os.path.join(video_dir, file)
                            
                            if source_path != dest_path and os.path.exists(source_path):
                                try:
                                    if os.path.exists(dest_path):
                                        # If file already exists in destination, skip
                                        continue
                                    shutil.move(source_path, dest_path)
                                except Exception as e:
                                    print(f"Could not move {file}: {e}")
                
                # Convert SRT/VTT to TXT after organizing
                video_dir_files = os.listdir(video_dir) if os.path.isdir(video_dir) else []
                for file in video_dir_files:
                    if file.lower().endswith('.srt'):
                        srt_path = os.path.join(video_dir, file)
                        txt_path = os.path.splitext(srt_path)[0] + ".txt"
                        if not os.path.exists(txt_path) or os.path.getmtime(txt_path) < os.path.getmtime(srt_path):
                            _convert_srt_file_to_txt(srt_path)
                    
                    elif file.lower().endswith('.vtt'):
                        vtt_path = os.path.join(video_dir, file)
                        txt_path = os.path.splitext(vtt_path)[0] + ".txt"
                        if not os.path.exists(txt_path) or os.path.getmtime(txt_path) < os.path.getmtime(vtt_path):
                            _convert_vtt_file_to_txt(vtt_path)

    except Exception as e:
        print(f"Error organizing video downloads: {e}")

def _create_playlist_info_file(playlist_dir: str, title: str, uploader: str, playlist_type: str, source_url: str):
    """Create a playlist info file for music library organization."""
    from datetime import datetime
    try:
        info_path = os.path.join(playlist_dir, "playlist_info.txt")

        # Count audio files
        audio_files = []
        for file in os.listdir(playlist_dir):
            if file.lower().endswith(('.mp3', '.flac', '.m4a', '.opus', '.wav')):
                audio_files.append(file)

        # Format playlist type nicely
        type_display = {
            "youtube_music": "YouTube Music Playlist",
            "soundcloud_playlist": "SoundCloud Playlist",
            "youtube_playlist": "YouTube Playlist",
            "bandcamp_album": "Bandcamp Album",
            "album": "Album",
            "generic_playlist": "Playlist"
        }.get(playlist_type, playlist_type.replace('_', ' ').title())

        download_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        info_content = f"""PLAYLIST INFORMATION
==================

Title: {title}
Uploader: {uploader or 'Unknown'}
Type: {type_display}
Source URL: {source_url}
Download Date: {download_date}
Location: {playlist_dir}

Files: {len(audio_files)} audio tracks

This playlist was downloaded using LTW Downloader.
Perfect for importing into local music libraries!

==================
"""

        try:
            with open(info_path, 'w', encoding='utf-8') as f:
                f.write(info_content)
        except Exception:
            pass  # Silently fail if we can't create info file
    except Exception:
        pass  # Silently fail if we can't create info file


def _pre_delete_temp_files(base_dir: str):
    """Remove temporary/partial files that can cause ffmpeg EEXIST (183)."""
    try:
        patterns = ["*.part", "*.temp", "*.ytdl", "*.partial", "*.tmp"]
        for patt in patterns:
            for path in glob.glob(os.path.join(base_dir, patt)):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass


def _pre_delete_existing_outputs(target_dir: str, base_name: str):
    """Delete common final/intermediate files for a specific base to avoid ffmpeg 183."""
    try:
        patterns = [
            f"{base_name}.mp3",
            f"{base_name}.m4a",
            f"{base_name}.opus",
            f"{base_name}.webm",
            f"{base_name}.mp4",
            f"{base_name}.mkv",
            f"{base_name}.m4v",
            f"{base_name}.part",
            f"{base_name}.temp",
            f"{base_name}.ytdl",
        ]
        for patt in patterns:
            for path in glob.glob(os.path.join(target_dir, patt)):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass

def get_save_folder_for_mode(mode):
    """Return the appropriate save folder based on download mode."""
    if mode == "audio":
        return music_folder if music_folder else save_folder
    return save_folder


def _apply_cookie_options(ydl_opts):
    """Apply cookies from browser export file or cookies-from-browser selection."""
    browser = ""
    try:
        browser = (cookies_browser_var.get() or "None").strip()
    except Exception:
        browser = "None"
    if browser and browser.lower() != "none":
        ydl_opts["cookiesfrombrowser"] = (browser.lower(),)
        return
    try:
        cf = (cookie_file_var.get() or "").strip()
    except Exception:
        cf = ""
    if cf and os.path.isfile(cf):
        ydl_opts["cookiefile"] = cf


def _audio_postprocessors(audio_quality, platform):
    """Build audio postprocessors for original-quality or MP3 targets."""
    if is_original_audio_quality(audio_quality):
        postprocessors = [
            {"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True},
            {"key": "EmbedThumbnail"},
        ]
        if platform == "bandcamp.com":
            postprocessors.insert(0, {"key": "FFmpegExtractAudio", "preferredcodec": "flac", "preferredquality": "0"})
        return postprocessors

    target_quality = audio_quality.replace("kbps", "") if "kbps" in audio_quality else "192"
    preferredcodec = "flac" if platform == "bandcamp.com" and audio_quality == "Best (original)" else "mp3"
    return [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": preferredcodec,
        "preferredquality": target_quality,
    }]


def configure_audio_download(ydl_opts, audio_quality, platform, is_soundcloud):
    """Configure yt-dlp options for audio downloads."""
    audio_quality = normalize_audio_quality(audio_quality)
    if is_original_audio_quality(audio_quality):
        if is_soundcloud:
            ydl_opts["format"] = "bestaudio*/ba/b"
        elif platform == "bandcamp.com":
            ydl_opts["format"] = "bestaudio*/best"
        else:
            ydl_opts["format"] = "bestaudio*/bestaudio/best"
        ydl_opts["writethumbnail"] = True
        ydl_opts["embedthumbnail"] = True
        ydl_opts["postprocessors"] = _audio_postprocessors(audio_quality, platform)
        ydl_opts["postprocessor_args"] = {
            "FFmpegMetadata": ["-y"],
            "EmbedThumbnail": ["-y"],
            "FFmpegExtractAudio": ["-y"],
        }
        ydl_opts["keepvideo"] = False
        ydl_opts["prefer_ffmpeg"] = True
        if is_soundcloud:
            ydl_opts["hls_prefer_native"] = False
            ydl_opts["external_downloader"] = {"default": "ffmpeg"}
            ydl_opts["external_downloader_args"] = {
                "ffmpeg": ["-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
            }
            ydl_opts["sleep_interval"] = 2
            ydl_opts["max_sleep_interval"] = 10
            ydl_opts["sleep_interval_requests"] = 1
            ydl_opts["retries"] = 15
            ydl_opts["fragment_retries"] = 10
        return

    audio_format_map = {
        "320kbps": "bestaudio[abr<=320]/bestaudio[abr>=256]/best",
        "256kbps": "bestaudio[abr<=256]/bestaudio[abr>=192]/best",
        "192kbps": "bestaudio[abr<=192]/bestaudio[abr>=128]/best",
        "128kbps": "bestaudio[abr<=128]/bestaudio[abr>=96]/best",
        "96kbps": "bestaudio[abr<=96]/bestaudio[abr>=64]/best",
        "64kbps": "bestaudio[abr<=64]/best",
    }
    ydl_opts["format"] = audio_format_map.get(audio_quality, "bestaudio/best")
    ydl_opts["postprocessors"] = _audio_postprocessors(audio_quality, platform)
    ydl_opts["postprocessor_args"] = {
        "FFmpegExtractAudio": ["-y"],
        "FFmpegMerger": ["-y"],
        "FFmpegVideoRemuxer": ["-y"],
    }
    ydl_opts["keepvideo"] = False
    ydl_opts["prefer_ffmpeg"] = True
    if is_soundcloud:
        ydl_opts["hls_prefer_native"] = False
        ydl_opts["external_downloader"] = {"default": "ffmpeg"}
        ydl_opts["external_downloader_args"] = {
            "ffmpeg": ["-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        }
        ydl_opts["sleep_interval"] = 2
        ydl_opts["max_sleep_interval"] = 10
        ydl_opts["sleep_interval_requests"] = 1
        ydl_opts["retries"] = 15
        ydl_opts["fragment_retries"] = 10


def get_url_input():
    """Return URL field contents (batch: one URL per line). Empty if placeholder."""
    w = globals().get("url_text")
    if w is None:
        return ""
    raw = w.get("1.0", "end").strip()
    if url_has_placeholder:
        return ""
    return raw


def start_download():
    # Guard placeholder text
    urls_text = get_url_input()
    if not urls_text:
        status_var.set("❌ Paste URL(s).")
        return

    # Split by newlines and filter empty lines
    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
    if not urls:
        status_var.set("❌ Paste URL(s).")
        return

    # For batch downloads, use the first URL for platform detection
    url = urls[0]
    try:
        allow_playlist = bool(int(playlist_var.get()))
    except (TypeError, ValueError, tk.TclError):
        allow_playlist = bool(playlist_var.get())
    download_urls = [
        _youtube_strip_playlist_params(u) if not allow_playlist else u
        for u in urls
    ]
    download_url = download_urls[0]
    if not allow_playlist and download_url != url:
        print("[YouTube] Single-video mode: removed playlist params from the URL (only this video will download).")

    # Suppress impersonation warnings
    warnings.filterwarnings("ignore", message=".*impersonation.*")

    # Early block for DRM platforms to avoid confusing partial downloads
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        netloc = ""
    if any(d in netloc for d in UNSUPPORTED_DRM_DOMAINS):
        status_var.set("⚠️ This site uses DRM (e.g., Netflix/Disney+/Prime). Full downloads are not supported.")
        return

    # Detect and show platform info
    platform = detect_platform(download_url)
    hint = ""
    try:
        hint = creator_preset_hint(source_preset_var.get(), url)
    except Exception:
        pass
    if platform in SUPPORTED_PLATFORMS:
        platform_name = SUPPORTED_PLATFORMS[platform]["name"]
        features = ", ".join(SUPPORTED_PLATFORMS[platform]["features"])
        base = f"🎯 Detected {platform_name} — {features}"
        status_var.set(base + (f"  |  {hint}" if hint else ""))
    else:
        status_var.set("🔍 URL detected — attempting download..." + (f"  |  {hint}" if hint else ""))

    mode = mode_var.get()
    quality = quality_var.get()
    audio_quality = audio_quality_var.get()
    video_format = format_var.get()
    download_subs = subs_var.get() if 'subs_var' in globals() else False

    # Base options; output template is finalized inside the worker after probing
    ydl_opts = {
        "quiet": True,
        # Use a safe placeholder if some metadata is missing
        "outtmpl_na_placeholder": "unknown",
        "noplaylist": not allow_playlist,
        "progress_hooks": [progress_hook],
        # Be resilient to flaky connections
        "retries": 5,  # Increased retries for reliability
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
        "socket_timeout": 30,  # Increased timeout for slow connections
        # Balanced download settings
        "concurrent_fragment_downloads": 3,  # Balanced parallel downloads
        "http_chunk_size": 2097152,  # 2MB chunks for better performance
        # More reliable download settings
        "no_check_certificate": True,
        "prefer_insecure": True,
        "sleep_interval": 2,  # Slight delay to avoid rate limiting
        "max_sleep_interval": 10,  # Allow longer waits if rate limited
        # Better handling of HLS streams (SoundCloud, etc.)
        "hls_use_mpegts": False,
        "hls_prefer_native": False,
        # Use built-in downloader with conservative settings
        "external_downloader": None,
        "external_downloader_args": None,
        # Suppress impersonation warnings (not critical for functionality)
        "no_warnings": False,
        # Continue playlist even if some entries fail and prefer web client for better compatibility
        "ignoreerrors": "only_download",
        # Force overwrite to avoid ffmpeg EEXIST (code 183)
        "overwrites": True,
        "extractor_args": {
            "youtube": {
                # Let yt-dlp defaults + bgutil POT provider handle client selection.
                # Fallback to tv_downgraded/android_vr is applied at download time if formats are capped.
                "comment_sort": ["top"],
                "max_comments": [0],
            },
            "tiktok": {
                "webpage_download": True,
                "api_hostname": "api-h2.tiktokv.com",
                "app_version": "29.0.0",
                "manifest_app_version": "29.0.0",
            },
            "instagram": {
                "api_hostname": "i.instagram.com",
            },
            "twitter": {
                "api_hostname": "api.twitter.com",
            },
            "soundcloud": {
                "max_comments": [0],
            },
        },
        # Try to bypass some restrictions - use recent browser user agent
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "js_runtimes": _js_runtime_options(),
    }

    _apply_cookie_options(ydl_opts)

    # Add TikTok-specific headers to avoid 403 errors
    if "tiktok.com" in download_url.lower():
        ydl_opts["http_headers"] = {
            "Referer": "https://www.tiktok.com/",
            "Origin": "https://www.tiktok.com",
        }

    # Special-case SoundCloud to avoid any ffmpeg conversion/rename collisions
    is_soundcloud = False
    try:
        url_lower = (download_url or "").lower()
        is_soundcloud = "soundcloud.com" in url_lower or "on.soundcloud.com" in url_lower
    except Exception:
        pass

    if mode == "audio":
        configure_audio_download(ydl_opts, audio_quality, platform, is_soundcloud)
    else:
        ydl_opts["format"] = format_for_video(quality, download_url)
        ydl_opts["format_sort"] = format_sort_for_video(quality, download_url)
        apply_video_output_options(ydl_opts, quality, video_format, platform, download_url)

    # Download subtitles only if checkbox is checked
    if download_subs:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        if mode == "video":
            # Download VTT format (web standard, preferred) and SRT (backup/compatibility)
            # yt-dlp will try to get both if available
            # Download English subtitles (all variants)
            ydl_opts["subtitleslangs"] = ["en", "en-US", "en-GB", "en-AU"]
            ydl_opts["subtitlesformat"] = "vtt"  # Prefer VTT format (web standard)
            # Also embed into MP4 when possible (external .vtt/.srt will still be saved)
            ydl_opts["embedsubtitles"] = True
        else:
            ydl_opts["subtitlesformat"] = "srt"  # Just SRT for audio mode
    else:
        # Subtitles disabled - explicitly set to False and don't set subtitleslangs
        ydl_opts["writesubtitles"] = False
        ydl_opts["writeautomaticsub"] = False
        ydl_opts["embedsubtitles"] = False
        # Don't set subtitleslangs when disabled to avoid any regex issues
        if "subtitleslangs" in ydl_opts:
            del ydl_opts["subtitleslangs"]
        if "subtitlesformat" in ydl_opts:
            del ydl_opts["subtitlesformat"]

    toggle_ui(False)
    
    # Quick check if URL is a playlist for better status message
    detected_playlist = False
    detected_playlist_title = None
    detected_playlist_type = "unknown"
    
    if len(urls) == 1:
        # Match yt-dlp behavior: when "download playlist" is off, watch?v=…&list=… is one video only
        try:
            probe_opts = {"quiet": True, "noplaylist": not allow_playlist}
            with YoutubeDL(probe_opts) as probe:
                info = probe.extract_info(download_urls[0], download=False)
            info_type = info.get("_type", "")
            detected_playlist = bool(allow_playlist and info_type in ("playlist", "multi_video"))
            if detected_playlist:
                detected_playlist_title = info.get("title") or info.get("playlist_title")
                url_lower = url.lower()
                if "music.youtube.com" in url_lower:
                    detected_playlist_type = "youtube_music"
                elif ("soundcloud.com" in url_lower or "on.soundcloud.com" in url_lower) and (
                    info_type == "playlist" or "sets" in url_lower or "/playlist" in url_lower
                ):
                    detected_playlist_type = "soundcloud_playlist"
                elif "youtube.com" in url_lower and "list=" in url_lower:
                    detected_playlist_type = "youtube_playlist"
        except Exception:
            pass  # Ignore probe errors, will handle in thread

    if len(urls) > 1:
        status_var.set(f"⬇️ Starting batch download ({len(urls)} URLs)...")
    elif detected_playlist and detected_playlist_title:
        platform = detect_platform(download_url)
        platform_name = SUPPORTED_PLATFORMS.get(platform, {}).get("name", "Unknown")
        playlist_type_desc = {
            "youtube_music": "YouTube Music Playlist",
            "soundcloud_playlist": "SoundCloud Playlist",
            "album": "Album",
            "bandcamp_album": "Bandcamp Album",
            "youtube_playlist": "YouTube Playlist"
        }.get(detected_playlist_type, "Playlist")
        status_var.set(f"🎵 Downloading {playlist_type_desc}: {detected_playlist_title[:50]}{'...' if len(detected_playlist_title) > 50 else ''}")
    else:
        platform = detect_platform(download_url)
        if platform in SUPPORTED_PLATFORMS:
            platform_name = SUPPORTED_PLATFORMS[platform]["name"]
            status_var.set(f"⬇️ Starting {platform_name} download...")
        else:
            status_var.set("⬇️ Starting download...")
    try:
        set_progress(0)
    except Exception:
        pass
    percent_var.set("0%")

    def run_download():
        try:
            # Enhanced playlist detection and metadata extraction
            playlist_title = None
            playlist_uploader = None
            is_playlist = False
            playlist_type = "unknown"
            url_lower = url.lower()

            # Pre-detect playlist from URL structure (before yt-dlp probe)
            is_url_playlist = "list=" in url or "/playlist" in url_lower or "/sets/" in url_lower

            # Extract playlist ID from URL for fallback naming
            playlist_id_from_url = None
            if "list=" in url:
                try:
                    import re
                    match = re.search(r'list=([a-zA-Z0-9_-]+)', url)
                    if match:
                        playlist_id_from_url = match.group(1)[:20]  # First 20 chars
                except:
                    pass

            try:
                probe_opts = {"quiet": True, "noplaylist": not allow_playlist}
                probe_url = download_urls[0]
                with YoutubeDL(probe_opts) as probe:
                    info = probe.extract_info(probe_url, download=False)

                info_type = info.get("_type", "")
                is_playlist = info_type in ("playlist", "multi_video")
                if is_playlist and not info.get("entries"):
                    is_playlist = False

                if is_playlist:
                    playlist_title = (
                        info.get("title")
                        or info.get("playlist_title")
                        or info.get("album")
                        or info.get("playlist")
                        or info.get("name")
                        or (info.get("description") or "")[:50]
                        or None
                    )
                    playlist_uploader = (
                        info.get("uploader")
                        or info.get("playlist_uploader")
                        or info.get("channel")
                        or info.get("artist")
                        or info.get("creator")
                        or None
                    )

                    if "music.youtube.com" in url_lower:
                        playlist_type = "youtube_music"
                    elif ("soundcloud.com" in url_lower or "on.soundcloud.com" in url_lower) and (
                        "sets" in url_lower or "/playlist" in url_lower or info_type == "playlist"
                    ):
                        playlist_type = "soundcloud_playlist"
                    elif "youtube.com" in url_lower and "list=" in url_lower:
                        if playlist_title and any(
                            word in playlist_title.lower() for word in ["album", "ep", "mixtape"]
                        ):
                            playlist_type = "album"
                        else:
                            playlist_type = "youtube_playlist"
                    elif "bandcamp.com" in url_lower and "album" in url_lower:
                        playlist_type = "bandcamp_album"
                    else:
                        playlist_type = "generic_playlist"

                if info_type == "video" and not allow_playlist:
                    is_playlist = False
                    playlist_title = None

                print(
                    f"[Playlist Detection] is_playlist={is_playlist}, type={playlist_type}, "
                    f"title={playlist_title}, uploader={playlist_uploader}, noplaylist={not allow_playlist}"
                )

            except Exception as e:
                print(f"Playlist detection warning: {e}")

            # GUARANTEED FALLBACK: If URL looks like playlist and checkbox is on, force playlist mode
            if is_url_playlist and allow_playlist:
                is_playlist = True
                if not playlist_title:
                    # Generate fallback title based on platform
                    if "music.youtube.com" in url_lower:
                        playlist_type = "youtube_music"
                        playlist_title = f"YouTube Music Playlist ({playlist_id_from_url or 'Unknown'})"
                    elif "youtube.com" in url_lower:
                        playlist_type = "youtube_playlist"
                        playlist_title = f"YouTube Playlist ({playlist_id_from_url or 'Unknown'})"
                    elif "soundcloud.com" in url_lower:
                        playlist_type = "soundcloud_playlist"
                        playlist_title = "SoundCloud Playlist"
                    else:
                        playlist_type = "generic_playlist"
                        playlist_title = f"Playlist ({playlist_id_from_url or 'Unknown'})"
                    print(f"[Fallback] Using generated playlist title: {playlist_title}")

            # Determine the appropriate save folder based on mode
            mode_specific_folder = get_save_folder_for_mode(mode)
            
            # Warn if playlist detected but checkbox not enabled
            if is_playlist and playlist_title and not allow_playlist:
                status_var.set(f"⚠️ Playlist detected but checkbox unchecked. Files will go to main folder.")
                print(f"[Warning] Playlist '{playlist_title}' detected but 'Download playlist' checkbox is OFF")
            
            # Enhanced playlist folder organization for music library
            target_root_dir = mode_specific_folder
            if allow_playlist and is_playlist and playlist_title:
                status_var.set(f"📁 Creating playlist folder: {playlist_title[:40]}...")
                # Create organized folder structure based on playlist type
                safe_playlist_name = _safe_component(playlist_title)
                if len(safe_playlist_name) > 80:  # Allow longer names for playlists
                    safe_playlist_name = safe_playlist_name[:77] + "..."

                if playlist_type == "youtube_music":
                    # YouTube Music playlists: Artist - Playlist Name
                    if playlist_uploader:
                        safe_uploader = _safe_component(playlist_uploader)
                        folder_name = f"{safe_uploader} - {safe_playlist_name}"
                    else:
                        folder_name = f"YouTube Music - {safe_playlist_name}"
                    pl_dir = os.path.join(mode_specific_folder, "YouTube Music Playlists", folder_name)

                elif playlist_type == "soundcloud_playlist":
                    # SoundCloud playlists: Use simple Playlists folder (matches YouTube structure)
                    pl_dir = os.path.join(mode_specific_folder, "Playlists", safe_playlist_name)

                elif playlist_type == "album":
                    # Albums: Artist - Album Name
                    if playlist_uploader:
                        safe_uploader = _safe_component(playlist_uploader)
                        folder_name = f"{safe_uploader} - {safe_playlist_name}"
                    else:
                        folder_name = safe_playlist_name
                    pl_dir = os.path.join(mode_specific_folder, "Albums", folder_name)

                elif playlist_type == "bandcamp_album":
                    # Bandcamp albums: Artist - Album Name
                    if playlist_uploader:
                        safe_uploader = _safe_component(playlist_uploader)
                        folder_name = f"{safe_uploader} - {safe_playlist_name}"
                    else:
                        folder_name = safe_playlist_name
                    pl_dir = os.path.join(mode_specific_folder, "Bandcamp Albums", folder_name)

                else:
                    # Generic playlists
                    pl_dir = os.path.join(mode_specific_folder, "Playlists", safe_playlist_name)

                # Create output template based on mode
                if mode == "audio":
                    outtmpl = os.path.join(pl_dir, "%(title)s - %(artist)s [%(id)s].%(ext)s")
                else:
                    # For video playlists, create per-video folders
                    outtmpl = os.path.join(pl_dir, "%(title)s [%(id)s]", "%(title)s [%(id)s].%(ext)s")

                ydl_opts["outtmpl"] = outtmpl
                target_root_dir = pl_dir
                print(f"[Playlist Folder] Creating: {pl_dir}")
            else:
                if mode == "audio":
                    outtmpl = os.path.join(mode_specific_folder, "%(title)s [%(id)s].%(ext)s")
                else:
                    # For video mode, create per-video folders with all files organized
                    outtmpl = os.path.join(mode_specific_folder, "%(title)s [%(id)s]", "%(title)s [%(id)s].%(ext)s")
                ydl_opts["outtmpl"] = outtmpl
                target_root_dir = mode_specific_folder
                print(f"[No Playlist Folder] Files will go to: {mode_specific_folder}")
                print(f"  Reason: allow_playlist={allow_playlist}, is_playlist={is_playlist}, playlist_title={playlist_title}")

            ydl_opts["noplaylist"] = not (allow_playlist and is_playlist)

            # Pre-clean temp/partial files to avoid collisions
            try:
                os.makedirs(target_root_dir, exist_ok=True)
                _pre_delete_temp_files(target_root_dir)
            except Exception:
                pass

            # Best-effort: pre-delete exact target base files for this download
            try:
                def _cleanup_for(title: str, vid: str):
                    base_name = _safe_component(f"{title} [{vid}]")
                    _pre_delete_existing_outputs(target_root_dir, base_name)

                if 'info' in locals() and isinstance(info, dict):
                    if is_playlist and info.get("entries"):
                        for entry in info.get("entries") or []:
                            if isinstance(entry, dict):
                                t = entry.get("title") or "unknown"
                                v = entry.get("id") or "unknown"
                                _cleanup_for(t, v)
                    else:
                        t = info.get("title") or "unknown"
                        v = info.get("id") or "unknown"
                        _cleanup_for(t, v)
            except Exception:
                pass

            youtube_fallback_applied = False
            if mode == "video" and detect_platform(download_urls[0]) in ("youtube.com", "youtu.be"):
                requested_cap = _height_cap_for_quality(normalize_video_quality(quality))
                if requested_cap and requested_cap > 720:
                    max_h = _youtube_max_available_height(download_urls[0], ydl_opts)
                    print(f"[YouTube] Max available height before download: {max_h}p (requested cap: {requested_cap}p)")
                    if max_h and max_h <= 720:
                        _apply_youtube_fallback_clients(ydl_opts)
                        youtube_fallback_applied = True

            def _run_ytdlp_download(urls_to_fetch):
                if len(urls_to_fetch) > 3:
                    status_var.set(f"🚀 Starting concurrent batch download ({len(urls_to_fetch)} URLs)...")
                    batch_size = 3
                    for i in range(0, len(urls_to_fetch), batch_size):
                        batch_urls = urls_to_fetch[i : i + batch_size]
                        status_var.set(
                            f"📦 Processing batch {i//batch_size + 1}/{(len(urls_to_fetch) + batch_size - 1)//batch_size}..."
                        )
                        with YoutubeDL(ydl_opts) as ydl:
                            ydl.download(batch_urls)
                else:
                    with YoutubeDL(ydl_opts) as ydl:
                        ydl.download(urls_to_fetch)

            try:
                _run_ytdlp_download(download_urls)
            except Exception as first_err:
                if (
                    not youtube_fallback_applied
                    and mode == "video"
                    and detect_platform(download_urls[0]) in ("youtube.com", "youtu.be")
                ):
                    _apply_youtube_fallback_clients(ydl_opts)
                    youtube_fallback_applied = True
                    print(f"[YouTube] Retrying after error: {first_err}")
                    _run_ytdlp_download(download_urls)
                else:
                    raise

            # Create playlist info file for music library organization
            if is_playlist and playlist_title and mode == "audio":
                try:
                    _create_playlist_info_file(target_root_dir, playlist_title, playlist_uploader, playlist_type, urls[0])
                except Exception as e:
                    print(f"Warning: Could not create playlist info file: {e}")

            # Organize video downloads: convert SRT to TXT, ensure all files in video folders
            if mode == "video":
                try:
                    _organize_video_downloads(target_root_dir)
                except Exception as e:
                    print(f"Warning: Could not organize video files: {e}")

            # After download, convert any SRTs found to clean TXT for easy reading
            try:
                _convert_srts_in_directory(target_root_dir)
            except Exception:
                pass
            quality_note = ""
            if last_downloaded_path and os.path.isfile(last_downloaded_path):
                quality_note = _report_download_quality(last_downloaded_path, quality, mode)

            if len(urls) > 1:
                done_msg = f"✅ Batch download complete! ({len(urls)} files)\nSaved to: {target_root_dir}"
            else:
                done_msg = f"✅ Done! Saved to:\n{target_root_dir}"
            if quality_note:
                done_msg = f"{done_msg}\n{quality_note}"
            status_var.set(done_msg)
            if auto_open_var.get():
                try:
                    open_folder(target_root_dir)
                except Exception:
                    pass
            save_settings()
        except Exception as e:
            error_msg = str(e)
            import traceback
            print(f"Full error traceback:\n{traceback.format_exc()}")
            
            # Platform-specific error messages (check both URL and error message)
            is_tiktok_error = "tiktok" in url.lower() or "tiktok" in error_msg.lower()
            
            if is_tiktok_error:
                if "403" in error_msg or "Forbidden" in error_msg:
                    status_var.set("🔒 TikTok blocked the request (403). Try updating yt-dlp: pip install --upgrade yt-dlp")
                elif "signature" in error_msg.lower() or "extractor" in error_msg.lower() or "Unable to extract" in error_msg:
                    status_var.set("⚠️ TikTok extractor issue. Try updating yt-dlp: pip install --upgrade yt-dlp")
                elif "private" in error_msg.lower() or "not available" in error_msg.lower():
                    status_var.set("🔒 TikTok video is private or unavailable.")
                elif "age" in error_msg.lower() or "restricted" in error_msg.lower():
                    status_var.set("🔒 TikTok video is age-restricted or unavailable.")
                elif "HTTP Error 429" in error_msg or "rate limit" in error_msg.lower():
                    status_var.set("⏱️ TikTok rate limited. Wait a few minutes and try again.")
                else:
                    status_var.set("❌ TikTok download failed. Check terminal for details.")
            elif "403" in error_msg or "Forbidden" in error_msg:
                status_var.set("🔒 Access forbidden (403). The site may be blocking downloads. Try updating yt-dlp.")
            elif "HTTP Error 429" in error_msg or "rate limit" in error_msg.lower():
                status_var.set("⏱️ Rate limited. Try again in a few minutes.")
            elif "not available" in error_msg.lower() or "private" in error_msg.lower():
                status_var.set("🔒 Content not available (private/removed).")
            elif "unsupported" in error_msg.lower():
                status_var.set("⚠️ Format not supported by this platform.")
            elif "network" in error_msg.lower():
                status_var.set("🌐 Network error. Check connection.")
            else:
                status_var.set("❌ Download failed. Check terminal for details.")
            print(f"Download error: {error_msg}")
        finally:
            toggle_ui(True)

    threading.Thread(target=run_download, daemon=True).start()

# ----------------- UI Thread-safe Updates -----------------
def progress_hook(d):
    if d.get("status") == "downloading":
        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        if total > 0:
            pct = int(downloaded * 100 / total)
            root.after(0, update_progress, pct, d.get("speed"), d.get("eta"))
    elif d.get("status") in ("finished", "postprocessing"):
        # Remember the final path when available
        global last_downloaded_path
        filename = d.get("filename") or ""
        if filename:
            last_downloaded_path = os.path.abspath(filename)
            try:
                root.after(0, lambda: open_file_btn.config(state="normal"))
            except Exception:
                pass
        root.after(0, update_progress, 100, None, None)

def format_eta(eta_seconds):
    if not eta_seconds:
        return "—"
    try:
        eta_seconds = int(eta_seconds)
    except Exception:
        return "—"
    m, s = divmod(eta_seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}h {m:02d}m {s:02d}s"
    if m:
        return f"{m:d}m {s:02d}s"
    return f"{s:d}s"

def update_progress(pct, speed, eta):
    percent_var.set(f"{pct}%")
    try:
        set_progress(pct)  # draw custom progress if available
    except Exception:
        pass
    if speed:
        mbps = f"{(speed or 0)/1_000_000:.2f} MB/s"
        eta_str = format_eta(eta)
        status_var.set(f"⬇️ Downloading... {mbps}  ETA {eta_str}")

def toggle_ui(state: bool):
    ui_state = "normal" if state else "disabled"
    download_btn.config(state=ui_state)
    browse_btn.config(state=ui_state)
    paste_btn.config(state=ui_state)
    # Keep Open Folder available during downloads to reduce confusion
    open_btn.config(state="normal")
    playlist_check.config(state=ui_state)
    audio_rb.config(state=ui_state)
    video_rb.config(state=ui_state)
    quality_menu.config(state="normal" if mode_var.get() == "video" and state else "disabled")
    try:
        check_formats_btn.config(state=ui_state)
        playlist_help_btn.config(state=ui_state)
        source_preset_menu.config(state=ui_state)
        format_menu.config(state=ui_state if mode_var.get() == "video" else "disabled")
        audio_quality_menu.config(state=ui_state if mode_var.get() == "audio" else "disabled")
        cookies_load_btn.config(state=ui_state)
        cookies_clear_btn.config(state=ui_state)
        cookies_browser_menu.config(state=ui_state)
        update_ytdlp_btn.config(state=ui_state)
    except Exception:
        pass

def choose_folder():
    global save_folder
    folder = filedialog.askdirectory()
    if folder:
        save_folder = folder
        folder_var.set(f"Download folder: {save_folder}")
        save_settings()

def choose_music_folder():
    global music_folder
    folder = filedialog.askdirectory()
    if folder:
        music_folder = folder
        music_folder_var.set(f"Music: {music_folder}")
        save_settings()

def on_mode_change():
    try:
        quality_menu.config(state="normal" if mode_var.get() == "video" else "disabled")
    except Exception:
        pass

def paste_from_clipboard():
    wt = globals().get("url_text")
    if wt is None:
        return
    try:
        text = root.clipboard_get().strip()
    except Exception:
        text = ""
    if text:
        clear_url_placeholder()
        wt.delete("1.0", "end")
        wt.insert("1.0", text)
        status_var.set("📋 Pasted from clipboard.")
        update_download_btn_state()


def is_probable_url(text: str) -> bool:
    if not text:
        return False
    if text == URL_PLACEHOLDER:
        return False
    try:
        parsed = urlparse(text)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def maybe_autopaste_url(only_if_empty: bool = True):
    """If the clipboard holds a URL, prefill the entry.

    When only_if_empty is True, only fill when the entry has no user text.
    """
    wt = globals().get("url_text")
    if wt is None:
        return
    try:
        clip = root.clipboard_get().strip()
    except Exception:
        return
    if not is_probable_url(clip):
        return
    raw = wt.get("1.0", "end").strip()
    if only_if_empty and raw and not url_has_placeholder:
        return
    clear_url_placeholder()
    wt.delete("1.0", "end")
    wt.insert("1.0", clip)
    status_var.set("🔎 Detected URL from clipboard.")
    update_download_btn_state()


def update_download_btn_state(*_args):
    urls_text = get_url_input()
    if not urls_text:
        try:
            download_btn.config(state="disabled")
        except Exception:
            pass
        return

    # Check if at least one valid URL exists
    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
    has_valid_url = any(is_probable_url(url) for url in urls)
    try:
        download_btn.config(state="normal" if has_valid_url else "disabled")
    except Exception:
        pass


def update_ytdlp():
    """Upgrade yt-dlp and the POT provider plugin in the active venv."""
    update_ytdlp_btn.config(state="disabled")
    status_var.set("⬆️ Updating yt-dlp...")

    def run_update():
        try:
            cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "yt-dlp[default]",
                "bgutil-ytdlp-pot-provider",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if result.returncode == 0:
                import importlib
                import yt_dlp

                importlib.reload(yt_dlp)
                version = yt_dlp.version.__version__
                root.after(0, lambda: status_var.set(f"✅ yt-dlp updated to {version}"))
                print(result.stdout)
            else:
                root.after(0, lambda: status_var.set("❌ yt-dlp update failed — see terminal"))
                print(result.stderr or result.stdout)
        except Exception as exc:
            root.after(0, lambda: status_var.set(f"❌ Update error: {exc}"))
        finally:
            root.after(0, lambda: update_ytdlp_btn.config(state="normal"))

    threading.Thread(target=run_update, daemon=True).start()


def check_available_formats():
    """Check and display available formats for the current URL."""
    url_src = get_url_input()
    if not url_src:
        status_var.set("❌ Enter a URL first.")
        return

    urls = [u.strip() for u in url_src.split('\n') if u.strip()]
    if not urls:
        status_var.set("❌ Enter a URL first.")
        return

    url = urls[0]  # Check first URL

    # Disable UI during format check
    check_formats_btn.config(state="disabled")
    status_var.set("🔍 Checking available formats...")

    def run_format_check():
        try:
            import subprocess
            import sys

            cmd = [sys.executable, "-m", "yt_dlp", "--list-formats"]
            browser = ""
            try:
                browser = (cookies_browser_var.get() or "None").strip()
            except Exception:
                browser = "None"
            if browser and browser.lower() != "none":
                cmd.extend(["--cookies-from-browser", browser.lower()])
            else:
                try:
                    cf = (cookie_file_var.get() or "").strip()
                except Exception:
                    cf = ""
                if cf and os.path.isfile(cf):
                    cmd.extend(["--cookies", cf])
            cmd.append(url)
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                # Extract format info from output
                lines = result.stdout.split('\n')
                format_lines = [line for line in lines if line.strip() and not line.startswith('[youtube')]

                # Show summary
                res_tokens = ['1080', '720', '480', '360', '1440', '2160', '4320']
                video_formats = [line for line in format_lines if any(res in line.lower() for res in res_tokens)]
                if video_formats:
                    status_var.set(f"📋 Found {len(video_formats)} video formats — see terminal for full list.")
                    print("Available formats:")
                    print(result.stdout)
                else:
                    status_var.set("⚠️ No obvious resolution rows — see terminal for full yt-dlp output.")
                    print("Format check output:")
                    print(result.stdout)
            else:
                status_var.set("❌ Format check failed. URL may be invalid.")
                print("Format check error:")
                print(result.stderr)

        except Exception as e:
            status_var.set("❌ Format check error.")
            print(f"Format check exception: {e}")
        finally:
            check_formats_btn.config(state="normal")

    threading.Thread(target=run_format_check, daemon=True).start()

def show_playlist_help():
    """Show help for finding playlist URLs from different platforms."""
    help_text = """🎵 PLAYLIST URL HELP

YouTube Music Playlists:
• Go to music.youtube.com
• Find your playlist or liked songs
• Copy the URL from browser address bar
• Should look like: https://music.youtube.com/playlist?list=...

SoundCloud Playlists/Sets:
• Go to soundcloud.com
• Find user profile → Sets/Playlists
• Copy the playlist URL
• Should look like: https://soundcloud.com/user/sets/playlist-name

Bandcamp Albums:
• Go to bandcamp.com
• Find album page
• Copy the album URL
• Should look like: https://artist.bandcamp.com/album/album-name

Regular YouTube Playlists:
• Go to youtube.com
• Find playlist
• Copy URL with ?list= parameter
• Should look like: https://youtube.com/playlist?list=...

Spotify: ❌ NOT SUPPORTED (DRM-protected)

Your downloader will automatically:
• Detect playlist type
• Create organized folder structure
• Download all tracks (original quality by default, or MP3 if selected)
• Create playlist_info.txt file
• Perfect for local music libraries!

💡 Pro Tip: Enable "Download playlist/album" checkbox for playlist downloads."""

    # Create a simple help window
    help_window = tk.Toplevel(root)
    help_window.title("Playlist URL Help")
    help_window.geometry("600x400")
    help_window.configure(bg=BG)

    help_label = tk.Label(help_window, text=help_text, bg=BG, fg=FG, font=FONT_REG, justify="left", wraplength=580)
    help_label.pack(padx=20, pady=20)

    close_btn = tk.Button(help_window, text="Got it!", command=help_window.destroy, bg=ACCENT, fg="#111111")
    close_btn.pack(pady=(0, 20))

def clear_url_placeholder(_event=None):
    global url_has_placeholder
    wt = globals().get("url_text")
    if wt is None:
        return
    if url_has_placeholder:
        wt.delete("1.0", "end")
        wt.config(fg=URL_FG_NORMAL, insertbackground=URL_INSERT)
        url_has_placeholder = False


def set_url_placeholder():
    global url_has_placeholder
    wt = globals().get("url_text")
    if wt is None:
        return
    if not wt.get("1.0", "end").strip():
        url_has_placeholder = True
        wt.delete("1.0", "end")
        wt.insert("1.0", URL_PLACEHOLDER)
        wt.config(fg=URL_FG_PLACEHOLDER, insertbackground=URL_INSERT)

# ----------------- GUI -----------------
root = tk.Tk()
root.title("LearningTheWires Downloader")
root.geometry("900x660")
root.resizable(True, True)

# Plain Tk widgets for macOS Tk 8.5 reliability; LTW-inspired palette
BG = "#16181d" if os.getenv("LTW_DARK", "1") == "1" else "#f0f2f5"
PANEL = "#1e2229" if BG == "#16181d" else "#ffffff"
FG = "#e8eaed" if BG == "#16181d" else "#1a1a1a"
FG_MUTED = "#9aa0a6" if BG == "#16181d" else "#5f6368"
ACCENT = "#f5a623"
ACCENT_COOL = "#4a9eff"
FONT_REG = ("Helvetica", 13)
FONT_BOLD = ("Helvetica", 13, "bold")
FONT_TITLE = ("Helvetica", 20, "bold")
FONT_SUB = ("Helvetica", 11)
FONT_SMALL = ("Helvetica", 11)
root.configure(bg=BG)

frm = tk.Frame(root, bg=BG)
frm.pack(fill="both", expand=True, padx=20, pady=16)

# --- Header ---
header = tk.Frame(frm, bg=BG)
header.pack(fill="x", pady=(0, 14))
tk.Label(
    header,
    text="LearningTheWires",
    bg=BG,
    fg=ACCENT,
    font=FONT_TITLE,
).pack(anchor="w")
tk.Label(
    header,
    text="Downloader — YouTube 4K/8K/HDR, YouTube Music, SoundCloud, TikTok, and more",
    bg=BG,
    fg=FG_MUTED,
    font=FONT_SUB,
    wraplength=820,
    justify="left",
).pack(anchor="w", pady=(2, 0))

body = tk.Frame(frm, bg=PANEL, highlightthickness=1, highlightbackground="#2d333b")
body.pack(fill="both", expand=True, padx=0, pady=0)
inner = tk.Frame(body, bg=PANEL)
inner.pack(fill="both", expand=True, padx=16, pady=16)

# Variables (no StringVar for URL — multiline Text widget)
folder_var = tk.StringVar(value=f"Download folder: {save_folder}")
music_folder_var = tk.StringVar(value=f"Music: {music_folder}")
status_var = tk.StringVar()
percent_var = tk.StringVar(value="0%")
mode_var = tk.StringVar(value="audio")
quality_var = tk.StringVar(value="Best Available")
audio_quality_var = tk.StringVar(value="Best (original)")
format_var = tk.StringVar(value="Auto")
playlist_var = tk.IntVar(value=0)
auto_open_var = tk.IntVar(value=0)
auto_detect_clipboard_var = tk.IntVar(value=1)
subs_var = tk.IntVar(value=1)
source_preset_var = tk.StringVar(value="Auto-detect")
cookie_file_var = tk.StringVar(value="")
cookie_display_var = tk.StringVar(value="Cookies: none (optional)")
cookies_browser_var = tk.StringVar(value="None")


def choose_cookies_file():
    path = filedialog.askopenfilename(
        title="Select cookies.txt (browser export)",
        filetypes=[("cookies.txt", "*.txt"), ("All files", "*")],
    )
    if path and os.path.isfile(path):
        cookie_file_var.set(path)
        cookie_display_var.set(f"Cookies: {os.path.basename(path)}")
        save_settings()


def clear_cookies_file():
    cookie_file_var.set("")
    cookie_display_var.set("Cookies: none (optional)")
    save_settings()


# --- Source: URLs ---
src_lbl = tk.Label(inner, text="Source — paste URLs (batch: one per line)", bg=PANEL, fg=FG, font=FONT_BOLD)
src_lbl.pack(anchor="w", pady=(0, 6))

url_row = tk.Frame(inner, bg=PANEL)
# Do not use expand=True here: on macOS Tk it steals all vertical space and hides
# everything packed below (Download, progress, status).
url_row.pack(fill="x")
url_row.grid_columnconfigure(0, weight=1)

url_text = tk.Text(
    url_row,
    height=5,
    width=72,
    wrap="word",
    bg="#ffffff",
    fg=URL_FG_PLACEHOLDER,
    insertbackground=URL_INSERT,
    font=FONT_REG,
    relief="groove",
    highlightthickness=1,
    highlightbackground="#888888",
)
url_text.grid(row=0, column=0, sticky="ew")
url_text.insert("1.0", URL_PLACEHOLDER)
url_text.bind("<FocusIn>", clear_url_placeholder)
url_text.bind("<FocusOut>", lambda _e: (set_url_placeholder(), update_download_btn_state()))
url_text.bind("<KeyRelease>", lambda _e: update_download_btn_state())

def _download_shortcut(_event=None):
    start_download()
    return "break"


url_text.bind("<Command-Return>", _download_shortcut)
url_text.bind("<Control-Return>", _download_shortcut)

url_btns = tk.Frame(url_row, bg=PANEL)
url_btns.grid(row=0, column=1, sticky="nw", padx=(10, 0))
paste_btn = tk.Button(url_btns, text="Paste", command=paste_from_clipboard, font=FONT_REG)
paste_btn.pack(fill="x", pady=(0, 6))
check_formats_btn = tk.Button(url_btns, text="Check formats", command=lambda: check_available_formats(), font=FONT_REG)
check_formats_btn.pack(fill="x", pady=(0, 6))
playlist_help_btn = tk.Button(url_btns, text="Playlist help", command=lambda: show_playlist_help(), font=FONT_REG)
playlist_help_btn.pack(fill="x")

# Primary actions directly under the URL row so they are never scrolled off-screen
button_frame = tk.Frame(inner, bg=PANEL)
button_frame.pack(fill="x", pady=(12, 0))
download_btn = tk.Button(
    button_frame,
    text="Download",
    command=start_download,
    font=FONT_BOLD,
    fg="#111111",
    bg=ACCENT,
    padx=14,
    pady=6,
)
download_btn.grid(row=0, column=0, sticky="w")


def open_current_folder():
    current_mode = mode_var.get()
    folder_to_open = get_save_folder_for_mode(current_mode)
    open_folder(folder_to_open)


open_btn = tk.Button(button_frame, text="Open folder", command=open_current_folder, font=FONT_REG)
open_btn.grid(row=0, column=1, padx=(10, 0), sticky="w")


def open_last_file():
    if last_downloaded_path:
        reveal_in_finder(last_downloaded_path)


open_file_btn = tk.Button(button_frame, text="Open file", command=open_last_file, state="disabled", font=FONT_REG)
open_file_btn.grid(row=0, column=2, padx=(10, 0), sticky="w")
update_ytdlp_btn = tk.Button(button_frame, text="Update yt-dlp", command=update_ytdlp, font=FONT_REG)
update_ytdlp_btn.grid(row=0, column=3, padx=(10, 0), sticky="w")

tk.Label(
    inner,
    text="Tip: Cmd+Return (Mac) or Ctrl+Return (Win/Linux) starts download from the URL box.",
    bg=PANEL,
    fg=FG_MUTED,
    font=FONT_SMALL,
).pack(anchor="w", pady=(8, 0))

# --- Creator preset ---
preset_row = tk.Frame(inner, bg=PANEL)
preset_row.pack(fill="x", pady=(14, 0))
tk.Label(preset_row, text="Creator preset (hints in status):", bg=PANEL, fg=FG, font=FONT_BOLD).pack(side="left")
source_preset_menu = tk.OptionMenu(preset_row, source_preset_var, *CREATOR_PRESET_OPTIONS)
source_preset_menu.pack(side="left", padx=(10, 0))

# --- Folders ---
folder_row = tk.Frame(inner, bg=PANEL)
folder_row.pack(fill="x", pady=(14, 6))
folder_row.grid_columnconfigure(0, weight=1)
folder_label = tk.Label(folder_row, textvariable=folder_var, bg=PANEL, fg=FG, font=FONT_REG)
folder_label.grid(row=0, column=0, sticky="w")
browse_btn = tk.Button(folder_row, text="Choose folder", command=choose_folder, font=FONT_REG)
browse_btn.grid(row=0, column=1, padx=(12, 0))

music_folder_row = tk.Frame(inner, bg=PANEL)
music_folder_row.pack(fill="x", pady=(0, 10))
music_folder_row.grid_columnconfigure(0, weight=1)
music_folder_label = tk.Label(music_folder_row, textvariable=music_folder_var, bg=PANEL, fg=FG, font=FONT_REG)
music_folder_label.grid(row=0, column=0, sticky="w")
browse_music_btn = tk.Button(music_folder_row, text="Browse music", command=choose_music_folder, font=FONT_REG)
browse_music_btn.grid(row=0, column=1, padx=(12, 0))

# --- Download type & quality ---
opt_header = tk.Label(inner, text="Download type & quality", bg=PANEL, fg=FG, font=FONT_BOLD)
opt_header.pack(anchor="w", pady=(4, 6))

options_row = tk.Frame(inner, bg=PANEL)
options_row.pack(fill="x")
tk.Label(options_row, text="Mode:", bg=PANEL, fg=FG, font=FONT_BOLD).grid(row=0, column=0, sticky="w")
audio_rb = tk.Radiobutton(
    options_row,
    text="Audio",
    variable=mode_var,
    value="audio",
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    command=on_mode_change,
    font=FONT_REG,
)
video_rb = tk.Radiobutton(
    options_row,
    text="Video",
    variable=mode_var,
    value="video",
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    command=on_mode_change,
    font=FONT_REG,
)
audio_rb.grid(row=0, column=1, sticky="w", padx=(10, 20))
video_rb.grid(row=0, column=2, sticky="w")

tk.Label(options_row, text="Quality:", bg=PANEL, fg=FG, font=FONT_BOLD).grid(row=1, column=0, sticky="w", pady=(10, 0))
quality_menu = tk.OptionMenu(options_row, quality_var, *VIDEO_QUALITY_OPTIONS)
quality_menu.grid(row=1, column=1, sticky="w", pady=(10, 8))

audio_quality_menu = tk.OptionMenu(options_row, audio_quality_var, *AUDIO_QUALITY_OPTIONS)
audio_quality_menu.grid(row=1, column=2, sticky="w", pady=(10, 8), padx=(10, 0))

tk.Label(options_row, text="Container:", bg=PANEL, fg=FG, font=FONT_BOLD).grid(row=1, column=3, sticky="w", pady=(10, 0), padx=(18, 5))
video_format_options = ["Auto", "MP4", "MKV", "WebM"]
format_menu = tk.OptionMenu(options_row, format_var, *video_format_options)
format_menu.grid(row=1, column=4, sticky="w", pady=(10, 8))

tk.Label(
    options_row,
    text="Video: Auto uses MKV for YouTube 4K/8K/HDR (no re-encode). Audio: Best (original) keeps source codec + embeds art/tags.",
    bg=PANEL,
    fg=FG_MUTED,
    font=FONT_SMALL,
    wraplength=720,
    justify="left",
).grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 4))


def update_format_menu(*args):
    if mode_var.get() == "audio":
        format_menu.grid_remove()
    else:
        format_menu.grid(row=1, column=4, sticky="w", pady=(10, 8))


mode_var.trace_add("write", update_format_menu)
update_format_menu()


def update_quality_menus(*args):
    if mode_var.get() == "video":
        quality_menu.config(state="normal")
        audio_quality_menu.config(state="disabled")
        quality_menu["menu"].delete(0, "end")
        for option in VIDEO_QUALITY_OPTIONS:
            quality_menu["menu"].add_command(label=option, command=tk._setit(quality_var, option))
    else:
        quality_menu.config(state="disabled")
        audio_quality_menu.config(state="normal")
        audio_quality_menu["menu"].delete(0, "end")
        for option in AUDIO_QUALITY_OPTIONS:
            audio_quality_menu["menu"].add_command(label=option, command=tk._setit(audio_quality_var, option))


mode_var.trace_add("write", update_quality_menus)
update_quality_menus()

# --- Creator extras ---
extras_header = tk.Label(inner, text="Creator extras", bg=PANEL, fg=FG, font=FONT_BOLD)
extras_header.pack(anchor="w", pady=(8, 4))

playlist_check = tk.Checkbutton(
    inner,
    text="Download full playlist / album (on). Off = one video only, even if the link has &list= / &index=",
    variable=playlist_var,
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    font=FONT_REG,
)
playlist_check.pack(anchor="w", pady=(0, 6))

toggles_row = tk.Frame(inner, bg=PANEL)
toggles_row.pack(fill="x", pady=(4, 0))
auto_detect_cb = tk.Checkbutton(
    toggles_row,
    text="Auto-detect URL from clipboard",
    variable=auto_detect_clipboard_var,
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    font=FONT_REG,
)
auto_detect_cb.grid(row=0, column=0, padx=(0, 18), sticky="w")
auto_open_cb = tk.Checkbutton(
    toggles_row,
    text="Open folder when finished",
    variable=auto_open_var,
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    font=FONT_REG,
)
auto_open_cb.grid(row=0, column=1, sticky="w")
subs_cb = tk.Checkbutton(
    toggles_row,
    text="Subtitles + embed when possible (video)",
    variable=subs_var,
    bg=PANEL,
    fg=FG,
    selectcolor=PANEL,
    activebackground=PANEL,
    activeforeground=FG,
    font=FONT_REG,
)
subs_cb.grid(row=0, column=2, padx=(18, 0), sticky="w")

cookie_row = tk.Frame(inner, bg=PANEL)
cookie_row.pack(fill="x", pady=(12, 0))
tk.Label(cookie_row, textvariable=cookie_display_var, bg=PANEL, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=(0, 12))
cookies_load_btn = tk.Button(cookie_row, text="Load cookies…", command=choose_cookies_file, font=FONT_REG)
cookies_load_btn.pack(side="left")
cookies_clear_btn = tk.Button(cookie_row, text="Clear cookies", command=clear_cookies_file, font=FONT_REG)
cookies_clear_btn.pack(side="left", padx=(8, 0))
tk.Label(cookie_row, text="Browser:", bg=PANEL, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=(16, 6))
cookies_browser_menu = tk.OptionMenu(cookie_row, cookies_browser_var, *COOKIES_BROWSER_OPTIONS)
cookies_browser_menu.pack(side="left")

# --- Progress ---
progress_frame = tk.Frame(inner, bg=PANEL)
progress_frame.pack(fill="x", pady=(16, 0))
progress_bg = "#2d333b" if BG == "#16181d" else "#d0d0d0"
progress_canvas = tk.Canvas(
    progress_frame,
    height=22,
    bg=progress_bg,
    highlightthickness=1,
    highlightbackground="#444a55",
)
progress_canvas.pack(side="left", fill="x", expand=True)
tk.Label(progress_frame, textvariable=percent_var, width=5, bg=PANEL, fg=FG).pack(side="right", padx=(8, 0))


def set_progress(pct: int):
    pct = max(0, min(100, int(pct)))
    width = max(progress_canvas.winfo_width(), 1)
    height = max(progress_canvas.winfo_height(), 1)
    fill_w = int(width * pct / 100)
    progress_canvas.delete("bar")
    progress_canvas.create_rectangle(0, 0, fill_w, height, fill=ACCENT_COOL, width=0, tags=("bar",))
    progress_canvas.delete("txt")
    progress_canvas.create_text(width // 2, height // 2, text=f"{pct}%", fill="#ffffff", tags=("txt",))


def paste_and_download():
    paste_from_clipboard()
    try:
        if download_btn["state"] == "normal":
            start_download()
    except Exception:
        pass


root.bind_all("<Command-v>", lambda e: paste_from_clipboard())
root.bind_all("<Control-v>", lambda e: paste_from_clipboard())
root.bind_all("<Command-Shift-v>", lambda e: paste_and_download())
root.bind_all("<Control-Shift-v>", lambda e: paste_and_download())


def _on_focus_in(_event):
    if auto_detect_clipboard_var.get() == 1:
        maybe_autopaste_url(only_if_empty=True)


root.bind("<FocusIn>", _on_focus_in)

status_label = tk.Label(inner, textvariable=status_var, wraplength=820, bg=PANEL, fg=ACCENT, justify="left", font=FONT_REG)
status_label.pack(anchor="w", pady=(10, 0))

inner.grid_columnconfigure(0, weight=1)


def _on_resize(event):
    try:
        set_progress(int(percent_var.get().rstrip("%")) if percent_var.get().endswith("%") else 0)
    except Exception:
        pass


progress_canvas.bind("<Configure>", _on_resize)

root.update_idletasks()
root.minsize(880, 620)
progress_canvas.after(150, lambda: set_progress(0))

url_text.focus()

# Apply persisted settings now that the UI exists
_loaded = load_settings()
if _loaded:
    try:
        folder_var.set(f"Download folder: {save_folder}")
        music_folder_var.set(f"Music: {music_folder}")
        if "auto_open" in _loaded:
            auto_open_var.set(int(_loaded.get("auto_open", 0)))
        if "auto_detect_clipboard" in _loaded:
            auto_detect_clipboard_var.set(int(_loaded.get("auto_detect_clipboard", 1)))
        if "mode" in _loaded:
            mode_var.set(_loaded.get("mode", "audio"))
            on_mode_change()
        if "quality" in _loaded:
            quality_var.set(normalize_video_quality(_loaded.get("quality", "Best Available")))
        if "audio_quality" in _loaded:
            audio_quality_var.set(normalize_audio_quality(_loaded.get("audio_quality", "Best (original)")))
        if "cookies_browser" in _loaded:
            cb = _loaded.get("cookies_browser", "None")
            if cb in COOKIES_BROWSER_OPTIONS:
                cookies_browser_var.set(cb)
        if "format" in _loaded:
            format_var.set(_loaded.get("format", "Auto"))
        if "playlist" in _loaded:
            playlist_var.set(int(_loaded.get("playlist", 0)))
        if "subtitles" in _loaded:
            subs_var.set(int(_loaded.get("subtitles", 1)))
        sp = _loaded.get("source_preset", "Auto-detect")
        if sp in CREATOR_PRESET_OPTIONS:
            source_preset_var.set(sp)
        cf = (_loaded.get("cookie_file") or "").strip()
        if cf and os.path.isfile(cf):
            cookie_file_var.set(cf)
            cookie_display_var.set(f"Cookies: {os.path.basename(cf)}")
        else:
            cookie_file_var.set("")
            cookie_display_var.set("Cookies: none (optional)")
    except Exception:
        pass

auto_open_cb.config(command=lambda: save_settings())
auto_detect_cb.config(command=lambda: save_settings())
audio_rb.config(command=lambda: (on_mode_change(), save_settings()))
video_rb.config(command=lambda: (on_mode_change(), save_settings()))
playlist_check.config(command=lambda: save_settings())
subs_cb.config(command=lambda: save_settings())

try:
    source_preset_menu.config(command=lambda: save_settings())
except Exception:
    pass

try:
    quality_var.trace_add("write", lambda *_: save_settings())
    audio_quality_var.trace_add("write", lambda *_: save_settings())
    format_var.trace_add("write", lambda *_: save_settings())
    source_preset_var.trace_add("write", lambda *_: save_settings())
    cookies_browser_var.trace_add("write", lambda *_: save_settings())
except Exception:
    try:
        quality_var.trace("w", lambda *_: save_settings())
        audio_quality_var.trace("w", lambda *_: save_settings())
        format_var.trace("w", lambda *_: save_settings())
        source_preset_var.trace("w", lambda *_: save_settings())
        cookies_browser_var.trace("w", lambda *_: save_settings())
    except Exception:
        pass


def on_close():
    save_settings()
    try:
        root.destroy()
    except Exception:
        pass


root.protocol("WM_DELETE_WINDOW", on_close)

update_download_btn_state()
root.mainloop()

