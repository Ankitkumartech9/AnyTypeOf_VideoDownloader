"""
Universal Video Downloader
--------------------------
Paste a YouTube / Instagram / Facebook link (single video or playlist),
choose MP4 (up to 4K / Full HD) or MP3 (and other audio formats), and download.

Built with Flask + yt-dlp. Requires ffmpeg for merging video+audio and for MP3.
"""

import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
import yt_dlp

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

# job_id -> state dict
JOBS = {}
JOBS_LOCK = threading.Lock()

TEMP_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def base_opts(cookies_browser: str = "", cookies_file: str = "") -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "restrictfilenames": False,
        "windowsfilenames": True,
    }
    if cookies_browser:
        # e.g. chrome, firefox, edge, brave, safari
        opts["cookiesfrombrowser"] = (cookies_browser,)
    elif cookies_file and Path(cookies_file).is_file():
        opts["cookiefile"] = cookies_file
    return opts


def build_format_opts(mode: str, quality: str, audio_format: str, audio_bitrate: str) -> dict:
    """Return yt-dlp options for the chosen mode/quality."""
    if mode == "audio":
        codec = audio_format if audio_format in ("mp3", "m4a", "wav", "flac", "opus") else "mp3"
        return {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": codec,
                    "preferredquality": audio_bitrate or "320",
                }
            ],
        }

    # Video mode
    if quality == "best":
        fmt = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
    else:
        h = int(quality)
        fmt = (
            f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={h}]+ba/"
            f"b[height<={h}]/b"
        )
    return {"format": fmt, "merge_output_format": "mp4"}


def set_job(job_id: str, **kwargs):
    with JOBS_LOCK:
        JOBS[job_id].update(kwargs)


def run_download(job_id: str, params: dict):
    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            info = d.get("info_dict", {}) or {}
            set_job(
                job_id,
                status="downloading",
                percent=round(pct, 1),
                speed=d.get("_speed_str", "").strip(),
                eta=d.get("_eta_str", "").strip(),
                current_title=info.get("title", ""),
                current_index=info.get("playlist_index") or 1,
                total_items=info.get("n_entries") or info.get("playlist_count") or 1,
            )
        elif d["status"] == "finished":
            set_job(job_id, status="processing", percent=100.0)

    try:
        opts = base_opts(params["cookies_browser"], params["cookies_file"])
        opts.update(
            build_format_opts(
                params["mode"], params["quality"], params["audio_format"], params["audio_bitrate"]
            )
        )
        opts["progress_hooks"] = [hook]
        opts["noplaylist"] = not params["playlist"]
        if params["playlist"]:
            opts["outtmpl"] = str(job_dir / "%(playlist_index)03d - %(title).150B.%(ext)s")
        else:
            opts["outtmpl"] = str(job_dir / "%(title).150B.%(ext)s")

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([params["url"]])

        files = sorted(
            p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith(TEMP_SUFFIXES)
        )
        if not files:
            raise RuntimeError("Nothing was downloaded. The link may be private or unsupported.")

        if len(files) == 1:
            final = files[0]
        else:
            final = job_dir / "playlist.zip"
            with zipfile.ZipFile(final, "w", zipfile.ZIP_STORED) as zf:
                for f in files:
                    zf.write(f, f.name)

        set_job(
            job_id,
            status="done",
            percent=100.0,
            file=str(final),
            filename=final.name,
            count=len(files),
            saved_in=str(job_dir),
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        # Strip ANSI colour codes yt-dlp sometimes adds
        for code in ("\x1b[0;31m", "\x1b[0m", "\x1b[1;31m"):
            msg = msg.replace(code, "")
        set_job(job_id, status="error", error=msg)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", ffmpeg=ffmpeg_available())


@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(error="Please paste a valid http(s) link."), 400

    opts = base_opts(data.get("cookies_browser", ""), data.get("cookies_file", ""))
    opts.update({"skip_download": True, "extract_flat": "in_playlist"})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 400

    is_playlist = info.get("_type") == "playlist" or "entries" in info
    heights = sorted(
        {f.get("height") for f in info.get("formats", []) if f.get("height")}, reverse=True
    )
    entries = list(info.get("entries") or []) if is_playlist else []
    return jsonify(
        title=info.get("title"),
        uploader=info.get("uploader") or info.get("channel"),
        thumbnail=info.get("thumbnail") or (entries[0].get("thumbnails", [{}])[-1].get("url") if entries and entries[0].get("thumbnails") else None),
        duration=info.get("duration"),
        is_playlist=is_playlist,
        playlist_count=len(entries) if is_playlist else 0,
        heights=heights,
        site=info.get("extractor_key"),
    )


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(error="Please paste a valid http(s) link."), 400

    mode = data.get("mode", "video")
    if not ffmpeg_available():
        return jsonify(
            error="ffmpeg is not installed. It is required for MP3 and for Full HD+ merging. "
            "See the README for install steps."
        ), 400

    params = {
        "url": url,
        "mode": "audio" if mode == "audio" else "video",
        "quality": str(data.get("quality", "1080")),
        "audio_format": data.get("audio_format", "mp3"),
        "audio_bitrate": str(data.get("audio_bitrate", "320")),
        "playlist": bool(data.get("playlist", False)),
        "cookies_browser": data.get("cookies_browser", ""),
        "cookies_file": data.get("cookies_file", ""),
    }

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "starting",
            "percent": 0.0,
            "created": time.time(),
        }
    threading.Thread(target=run_download, args=(job_id, params), daemon=True).start()
    return jsonify(job_id=job_id)


@app.route("/api/progress/<job_id>")
def api_progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify(error="Unknown job"), 404
        return jsonify({k: v for k, v in job.items() if k != "file"})


@app.route("/api/file/<job_id>")
def api_file(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify(error="File not ready"), 404
    return send_file(job["file"], as_attachment=True, download_name=job["filename"])


def find_free_port(preferred):
    """Return the first bindable port, trying the preferred one then a few others.

    On Windows, some ports (e.g. 5000) can be reserved by the system, which
    raises WinError 10013, so we test-bind before starting Flask.
    """
    import socket

    candidates = [preferred, 5001, 8000, 8080, 8888, 5050, 9000]
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # Let the OS pick any free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    port = find_free_port(int(os.environ.get("PORT", "5000")))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Video Downloader running -> {url}\n")
    if not ffmpeg_available():
        print("  WARNING: ffmpeg not found. Install it (see README) for MP3 / Full HD.\n")
    try:
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    except Exception:  # noqa: BLE001
        pass
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
