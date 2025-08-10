import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from yt_dlp import YoutubeDL

# ----------------- Save folder -----------------
save_folder = os.path.join(os.getcwd(), "downloads")
os.makedirs(save_folder, exist_ok=True)

# ----------------- Helpers -----------------
def open_folder(path):
    if sys.platform.startswith("darwin"):
        subprocess.call(["open", path])
    elif os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.call(["xdg-open", path])

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

# ----------------- Download -----------------
def start_download():
    url = url_var.get().strip()
    if not url:
        status_var.set("❌ Paste a YouTube URL.")
        return

    mode = mode_var.get()
    quality = quality_var.get()
    allow_playlist = playlist_var.get()

    ydl_opts = {
        "quiet": True,
        "outtmpl": os.path.join(save_folder, "%(title)s.%(ext)s"),
        "noplaylist": not allow_playlist,
        "progress_hooks": [progress_hook],
    }

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
    open_btn.config(state=ui_state)
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
        url_var.set(text)

# ----------------- GUI -----------------
root = tk.Tk()
root.title("LTW YouTube Downloader")
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

# URL Entry
tk.Label(url_row, text="YouTube URL:", bg=BG, fg=FG, font=FONT_BOLD).grid(row=0, column=0, sticky="w", padx=(0,8))
url_entry = tk.Entry(url_row, textvariable=url_var, width=60, bg="#ffffff", fg="#111111", insertbackground="#111111", relief="groove")
url_entry.grid(row=0, column=1, sticky="ew")
url_entry.bind('<Return>', lambda e: start_download())
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

# Progress (canvas bar)
progress_frame = tk.Frame(frm, bg=BG)
progress_frame.grid(row=4, column=0, columnspan=3, sticky="ew")
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
button_frame.grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 6))
download_btn = tk.Button(button_frame, text="Download", command=start_download, font=FONT_BOLD)
download_btn.grid(row=0, column=0)
open_btn = tk.Button(button_frame, text="Open Folder", command=lambda: open_folder(save_folder), font=FONT_REG)
open_btn.grid(row=0, column=1, padx=(8, 0))

# Keyboard shortcut: Cmd+V to paste, Enter to download
root.bind_all('<Command-v>', lambda e: paste_from_clipboard())
root.bind_all('<Control-v>', lambda e: paste_from_clipboard())
root.bind_all('<Return>', lambda e: start_download())

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

root.mainloop()
