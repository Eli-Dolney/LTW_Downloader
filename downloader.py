import os
import re
import json
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from urllib.parse import urlparse
from yt_dlp import YoutubeDL

# ----------------- Save folder -----------------
CONFIG_PATH = os.path.expanduser("~/.ltw_downloader.json")

save_folder = os.path.join(os.getcwd(), "downloads")
os.makedirs(save_folder, exist_ok=True)

# State tracked across the session
cookies_path = ""  # optional cookie file for sites like TikTok
last_downloaded_path = ""  # absolute path to the most recent file
URL_PLACEHOLDER = "Paste a video URL (YouTube, TikTok, etc.)"
url_has_placeholder = True

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
)

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

def format_for_video(label):
    """Return a yt-dlp format selector that prefers H.264/AAC MP4 for QuickTime.

    Falls back gracefully if MP4/H.264 isn't available, but we'll also recode
    to MP4 in that case to maximize compatibility.
    """
    height_caps = {"Best": None, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
    h = height_caps.get(label)
    height_filter = f"[height<={h}]" if h else ""
    # Prefer separate best video/audio that are already MP4/H.264 + M4A/AAC
    preferred = f"bestvideo[ext=mp4][vcodec*=avc]{height_filter}+bestaudio[ext=m4a][acodec*=mp4a]"
    # Fallback to a single MP4 if available, then anything else as last resort
    fallback1 = f"/best[ext=mp4]{height_filter}"
    fallback2 = f"/best{height_filter}"
    return preferred + fallback1 + fallback2

# ----------------- Settings Persistence -----------------
def load_settings():
    global save_folder, cookies_path
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("save_folder"), str) and data.get("save_folder"):
            save_folder_candidate = data["save_folder"]
            if os.path.isdir(save_folder_candidate):
                save_folder = save_folder_candidate
        if isinstance(data.get("cookies_path"), str):
            cookies_path = data.get("cookies_path") or ""
        # Defer UI variable assignment until after widgets are built
        return data
    except Exception:
        return {}

def save_settings(extra: dict | None = None):
    try:
        data = {
            "save_folder": save_folder,
            "cookies_path": cookies_path,
            "auto_open": int(auto_open_var.get()) if 'auto_open_var' in globals() else 0,
            "auto_detect_clipboard": int(auto_detect_clipboard_var.get()) if 'auto_detect_clipboard_var' in globals() else 1,
            "mode": mode_var.get() if 'mode_var' in globals() else 'audio',
            "quality": quality_var.get() if 'quality_var' in globals() else 'Best',
            "playlist": int(playlist_var.get()) if 'playlist_var' in globals() else 0,
            "subtitles": int(subs_var.get()) if 'subs_var' in globals() else 0,
        }
        if extra:
            data.update(extra)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# ----------------- Download -----------------
def start_download():
    # Guard placeholder text
    url = url_var.get().strip()
    if url_has_placeholder or not url:
        status_var.set("❌ Paste a video URL.")
        return
    if not url:
        status_var.set("❌ Paste a video URL.")
        return

    # Early block for DRM platforms to avoid confusing partial downloads
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        netloc = ""
    if any(d in netloc for d in UNSUPPORTED_DRM_DOMAINS):
        status_var.set("⚠️ This site uses DRM (e.g., Netflix/Disney+/Prime). Full downloads are not supported.")
        return

    mode = mode_var.get()
    quality = quality_var.get()
    allow_playlist = playlist_var.get()

    ydl_opts = {
        "quiet": True,
        # Prefix filename with platform and uploader for easy attribution
        # Example: "YouTube - ChannelName - Video Title.mp4"
        # For TikTok: "TikTok - uploader - Title.mp4"
        "outtmpl": os.path.join(save_folder, "%(extractor_key)s - %(uploader)s - %(title)s.%(ext)s"),
        # Use a safe placeholder if some metadata is missing
        "outtmpl_na_placeholder": "unknown",
        "noplaylist": not allow_playlist,
        "progress_hooks": [progress_hook],
        # Be resilient to flaky connections
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "socket_timeout": 20,
    }
    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    if mode == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        ydl_opts["format"] = format_for_video(quality)
        # Ensure QuickTime-compatible MP4 output
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["recode_video"] = "mp4"  # force recode to MP4 if needed
        ydl_opts["postprocessor_args"] = [
            "-movflags", "+faststart",  # better playback/start on macOS
            "-pix_fmt", "yuv420p",       # wide compatibility
        ]
        if subs_var.get() == 1:
            # Save subtitles alongside and try to embed when possible
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitlesformat"] = "srt"
            ydl_opts["embedsubtitles"] = True

    toggle_ui(False)
    status_var.set("⬇️ Starting download...")
    try:
        set_progress(0)
    except Exception:
        pass
    percent_var.set("0%")

    def run_download():
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            status_var.set(f"✅ Done! Saved to:\n{save_folder}")
            if auto_open_var.get():
                try:
                    open_folder(save_folder)
                except Exception:
                    pass
            save_settings()
        except Exception as e:
            status_var.set("❌ Error. Check terminal.")
            print(e)
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

def choose_folder():
    global save_folder
    folder = filedialog.askdirectory()
    if folder:
        save_folder = folder
        folder_var.set(f"Save to: {save_folder}")
        save_settings()

def on_mode_change():
    try:
        quality_menu.config(state="normal" if mode_var.get() == "video" else "disabled")
    except Exception:
        pass

def paste_from_clipboard():
    try:
        text = root.clipboard_get().strip()
    except Exception:
        text = ""
    if text:
        clear_url_placeholder()
        url_var.set(text)
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
    try:
        clip = root.clipboard_get().strip()
    except Exception:
        return
    if not is_probable_url(clip):
        return
    current = url_var.get().strip()
    if only_if_empty and (current and not url_has_placeholder):
        return
    clear_url_placeholder()
    url_var.set(clip)
    status_var.set("🔎 Detected URL from clipboard.")
    update_download_btn_state()

def update_download_btn_state(*_args):
    url_text = url_var.get().strip()
    is_valid = bool(is_probable_url(url_text) and not url_has_placeholder)
    download_btn.config(state="normal" if is_valid else "disabled")

def clear_url_placeholder(_event=None):
    global url_has_placeholder
    if url_has_placeholder:
        url_entry.delete(0, "end")
        url_entry.config(fg="#111111")
        url_has_placeholder = False

def set_url_placeholder():
    global url_has_placeholder
    if not url_var.get().strip():
        url_has_placeholder = True
        url_entry.delete(0, "end")
        url_entry.insert(0, URL_PLACEHOLDER)
        url_entry.config(fg="#777777")

# ----------------- GUI -----------------
root = tk.Tk()
root.title("LTW Video Downloader")
root.geometry("760x520")
root.resizable(True, True)

# Use plain Tk widgets for macOS Tk 8.5 reliability
BG = "#2b2b2b" if os.getenv("LTW_DARK", "1") == "1" else "#f5f5f7"
FG = "#f5f5f5" if BG == "#2b2b2b" else "#111111"
ACCENT = "#4caf50"
FONT_REG = ("Helvetica", 13)
FONT_BOLD = ("Helvetica", 13, "bold")
root.configure(bg=BG)

frm = tk.Frame(root, bg=BG)
frm.pack(fill="both", expand=True, padx=18, pady=18)

# --- Top: URL row ---
url_row = tk.Frame(frm, bg=BG)
url_row.grid(row=0, column=0, columnspan=3, sticky="ew")
url_row.grid_columnconfigure(1, weight=1)

# Variables
url_var = tk.StringVar()
folder_var = tk.StringVar(value=f"Save to: {save_folder}")
status_var = tk.StringVar()
percent_var = tk.StringVar(value="0%")
mode_var = tk.StringVar(value="audio")
quality_var = tk.StringVar(value="Best")
playlist_var = tk.IntVar(value=0)
auto_open_var = tk.IntVar(value=0)
auto_detect_clipboard_var = tk.IntVar(value=1)
cookies_label_var = tk.StringVar(value="No cookies loaded")
subs_var = tk.IntVar(value=0)

# URL Entry
tk.Label(url_row, text="Video URL:", bg=BG, fg=FG, font=FONT_BOLD).grid(row=0, column=0, sticky="w", padx=(0,8))
url_entry = tk.Entry(url_row, textvariable=url_var, width=60, bg="#ffffff", fg="#777777", insertbackground="#111111", relief="groove")
url_entry.grid(row=0, column=1, sticky="ew")
url_entry.bind('<Return>', lambda e: start_download())
url_entry.bind('<FocusIn>', clear_url_placeholder)
url_entry.bind('<FocusOut>', lambda e: (set_url_placeholder(), update_download_btn_state()))
url_entry.focus()

paste_btn = tk.Button(url_row, text="Paste", command=paste_from_clipboard)
paste_btn.grid(row=0, column=2, padx=(10, 0))

# Folder
folder_row = tk.Frame(frm, bg=BG)
folder_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 10))
folder_row.grid_columnconfigure(0, weight=1)
folder_label = tk.Label(folder_row, textvariable=folder_var, bg=BG, fg=FG, font=FONT_REG)
folder_label.grid(row=0, column=0, sticky="w")
browse_btn = tk.Button(folder_row, text="Browse Folder", command=choose_folder)
browse_btn.grid(row=0, column=1, padx=(12, 0))

options_row = tk.Frame(frm, bg=BG)
options_row.grid(row=2, column=0, columnspan=3, sticky="ew")
options_row.grid_columnconfigure(1, weight=1)
tk.Label(options_row, text="Mode:", bg=BG, fg=FG, font=FONT_BOLD).grid(row=0, column=0, sticky="w")
audio_rb = tk.Radiobutton(options_row, text="Audio (MP3)", variable=mode_var, value="audio", bg=BG, fg=FG, selectcolor=BG, command=on_mode_change, font=FONT_REG)
video_rb = tk.Radiobutton(options_row, text="Video (MP4)", variable=mode_var, value="video", bg=BG, fg=FG, selectcolor=BG, command=on_mode_change, font=FONT_REG)
audio_rb.grid(row=0, column=1, sticky="w", padx=(10, 20))
video_rb.grid(row=0, column=2, sticky="w")

# Quality dropdown using OptionMenu for Tk 8.5
tk.Label(options_row, text="Quality:", bg=BG, fg=FG, font=FONT_BOLD).grid(row=1, column=0, sticky="w", pady=(10, 0))
quality_options = ["Best", "1080p", "720p", "480p", "360p"]
quality_menu = tk.OptionMenu(options_row, quality_var, *quality_options)
quality_menu.grid(row=1, column=1, sticky="w", pady=(10, 10))
if mode_var.get() != "video":
    quality_menu.config(state="disabled")

# Playlist toggle
playlist_check = tk.Checkbutton(frm, text="Download full playlist (if available)", variable=playlist_var, bg=BG, fg=FG, selectcolor=BG, font=FONT_REG)
playlist_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 14))

# Convenience toggles
toggles_row = tk.Frame(frm, bg=BG)
toggles_row.grid(row=4, column=0, columnspan=3, sticky="w")
auto_detect_cb = tk.Checkbutton(toggles_row, text="Auto-detect URL from clipboard", variable=auto_detect_clipboard_var, bg=BG, fg=FG, selectcolor=BG, font=FONT_REG)
auto_detect_cb.grid(row=0, column=0, padx=(0, 18))
auto_open_cb = tk.Checkbutton(toggles_row, text="Open folder when finished", variable=auto_open_var, bg=BG, fg=FG, selectcolor=BG, font=FONT_REG)
auto_open_cb.grid(row=0, column=1)
subs_cb = tk.Checkbutton(toggles_row, text="Download subtitles (if available)", variable=subs_var, bg=BG, fg=FG, selectcolor=BG, font=FONT_REG)
subs_cb.grid(row=0, column=2, padx=(18, 0))

# Cookies loader for sites like TikTok/private videos
cookies_row = tk.Frame(frm, bg=BG)
cookies_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 6))
cookies_row.grid_columnconfigure(1, weight=1)
def load_cookies():
    global cookies_path
    path = filedialog.askopenfilename(title="Select cookies.txt", filetypes=[("Cookies file", "*.txt"), ("All files", "*.*")])
    if path:
        cookies_path = path
        cookies_label_var.set(f"Cookies: {os.path.basename(path)}")
    else:
        cookies_path = ""
        cookies_label_var.set("No cookies loaded")
    save_settings()
tk.Button(cookies_row, text="Load Cookies...", command=load_cookies).grid(row=0, column=0, sticky="w")
tk.Label(cookies_row, textvariable=cookies_label_var, bg=BG, fg=FG, font=FONT_REG).grid(row=0, column=1, sticky="w", padx=(8,0))

# Progress (canvas bar)
progress_frame = tk.Frame(frm, bg=BG)
progress_frame.grid(row=6, column=0, columnspan=3, sticky="ew")
progress_bg = "#3a3a3a" if BG == "#2b2b2b" else "#d0d0d0"
progress_canvas = tk.Canvas(progress_frame, height=20, bg=progress_bg, highlightthickness=1, highlightbackground="#666666")
progress_canvas.pack(side="left", fill="x", expand=True)
tk.Label(progress_frame, textvariable=percent_var, width=5, bg=BG, fg=FG).pack(side="right", padx=(8, 0))

def set_progress(pct: int):
    pct = max(0, min(100, int(pct)))
    width = max(progress_canvas.winfo_width(), 1)
    height = max(progress_canvas.winfo_height(), 1)
    fill_w = int(width * pct / 100)
    progress_canvas.delete("bar")
    progress_canvas.create_rectangle(0, 0, fill_w, height, fill="#4a90e2", width=0, tags=("bar",))
    # Optional percent text overlay for clarity
    progress_canvas.delete("txt")
    progress_canvas.create_text(width//2, height//2, text=f"{pct}%", fill="#ffffff", tags=("txt",))

# Buttons
button_frame = tk.Frame(frm, bg=BG)
button_frame.grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 6))
download_btn = tk.Button(button_frame, text="Download", command=start_download, font=FONT_BOLD)
download_btn.grid(row=0, column=0)
open_btn = tk.Button(button_frame, text="Open Folder", command=lambda: open_folder(save_folder), font=FONT_REG)
open_btn.grid(row=0, column=1, padx=(8, 0))

# Button to reveal the most recent file
def open_last_file():
    if last_downloaded_path:
        reveal_in_finder(last_downloaded_path)
open_file_btn = tk.Button(button_frame, text="Open File", command=open_last_file, state="disabled", font=FONT_REG)
open_file_btn.grid(row=0, column=2, padx=(8, 0))

# Quick action: Paste from clipboard and immediately start download
def paste_and_download():
    paste_from_clipboard()
    if download_btn["state"] == "normal":
        start_download()

# Keyboard shortcut: Cmd+V to paste, Enter to download
root.bind_all('<Command-v>', lambda e: paste_from_clipboard())
root.bind_all('<Control-v>', lambda e: paste_from_clipboard())
root.bind_all('<Return>', lambda e: start_download())
root.bind_all('<Command-Shift-v>', lambda e: paste_and_download())
root.bind_all('<Control-Shift-v>', lambda e: paste_and_download())
def _on_focus_in(_event):
    if auto_detect_clipboard_var.get() == 1:
        maybe_autopaste_url(only_if_empty=True)
root.bind('<FocusIn>', _on_focus_in)

# Status
status_label = tk.Label(frm, textvariable=status_var, wraplength=600, bg=BG, fg=ACCENT, justify="left", font=FONT_REG)
status_label.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 0))

# Grid weights
frm.grid_columnconfigure(0, weight=1)
frm.grid_columnconfigure(1, weight=0)
frm.grid_columnconfigure(2, weight=0)

def _on_resize(event):
    # update canvas bar when the frame resizes
    try:
        set_progress(int(percent_var.get().rstrip('%')) if percent_var.get().endswith('%') else 0)
    except Exception:
        pass
progress_canvas.bind("<Configure>", _on_resize)

# Minimum size
root.update_idletasks()
root.minsize(760, 520)
progress_canvas.after(150, lambda: set_progress(0))

# Apply persisted settings now that the UI exists
_loaded = load_settings()
if _loaded:
    try:
        folder_var.set(f"Save to: {save_folder}")
        if "auto_open" in _loaded:
            auto_open_var.set(int(_loaded.get("auto_open", 0)))
        if "auto_detect_clipboard" in _loaded:
            auto_detect_clipboard_var.set(int(_loaded.get("auto_detect_clipboard", 1)))
        if "mode" in _loaded:
            mode_var.set(_loaded.get("mode", "audio"))
            on_mode_change()
        if "quality" in _loaded:
            quality_var.set(_loaded.get("quality", "Best"))
        if "playlist" in _loaded:
            playlist_var.set(int(_loaded.get("playlist", 0)))
        if "subtitles" in _loaded:
            subs_var.set(int(_loaded.get("subtitles", 0)))
        if cookies_path:
            cookies_label_var.set(f"Cookies: {os.path.basename(cookies_path)}")
    except Exception:
        pass

# Save settings whenever key toggles change
auto_open_cb.config(command=lambda: save_settings())
auto_detect_cb.config(command=lambda: save_settings())
audio_rb.config(command=lambda: (on_mode_change(), save_settings()))
video_rb.config(command=lambda: (on_mode_change(), save_settings()))
quality_menu.config(command=lambda *_: save_settings())
playlist_check.config(command=lambda: save_settings())

def on_close():
    save_settings()
    try:
        root.destroy()
    except Exception:
        pass
root.protocol("WM_DELETE_WINDOW", on_close)

root.mainloop()

