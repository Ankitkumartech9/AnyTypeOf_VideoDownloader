# Video Downloader (YouTube · Instagram · Facebook)

A local web app built with **Python, Flask and yt-dlp**.
Paste a link (single video or playlist), choose MP4 (up to 4K / Full HD) or audio (MP3, M4A, WAV, FLAC, OPUS), and download.

## What you need to install

1. **Python 3.9 or newer** — https://www.python.org/downloads/
   (On Windows, tick **"Add Python to PATH"** during install.)
2. **ffmpeg** (required for MP3 and for merging Full HD video + audio)
   - Windows: `winget install Gyan.FFmpeg`  (or `choco install ffmpeg`)
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - Check it works: `ffmpeg -version`
3. **Python packages** (listed in `requirements.txt`: Flask and yt-dlp)

## Run it

```bash
cd video-downloader

# optional but recommended: virtual environment
python -m venv venv
# Windows:   venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt
python app.py
```

The app picks a free port automatically and opens your browser (check the terminal for the address, e.g. http://127.0.0.1:5000 or 5001).

Files are saved in the `downloads/` folder inside the project, and the page also gives you a Save button.

## How to use

1. Paste the link and click **Check** (shows title, thumbnail, and whether it is a playlist).
2. Pick **Video (MP4)** and a resolution (Full HD 1080p is the default), or **Audio** and a format/bitrate.
3. For playlists, keep "Download the whole playlist" ticked — you get a `.zip`.
4. Click **Download**, watch the progress bar, then click **Save**.

## Tips and troubleshooting

- **Keep yt-dlp updated** — sites change often. If downloads fail, run:
  `pip install -U yt-dlp`
- **Instagram / Facebook / private or age-restricted videos** usually need you to be logged in.
  Open "Advanced" in the app and pick the browser you are logged in with (cookies are read locally),
  or export a `cookies.txt` and paste its path.
- Chosen resolution is a *maximum*: if a video has no 1080p version, you get the best lower one.
- Windows "ffmpeg not found" after install → close and reopen the terminal so PATH refreshes.
- Chrome cookie reading may need Chrome closed on some systems; Firefox is often easiest.

## Legal note

Only download content you own, that is licensed for download, or that you have permission to save.
Downloading may violate a platform's terms of service or copyright law in your country.
