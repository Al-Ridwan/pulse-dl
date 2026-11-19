# PulseDL — Studio MP3 Extractor & Universal Video Downloader

A fast, ad-free local web app with two dedicated modules powered by `yt-dlp` and `FFmpeg`:

1. **Module 1: Studio MP3 Extractor** — Convert YouTube or any video URL into high-quality MP3 audio (`320 kbps`, `256 kbps`, `192 kbps`, `128 kbps`) with embedded album cover art, ID3 artist/title metadata, and optional start/end timestamp clipping.
2. **Module 2: Universal Video Downloader** — Download videos from YouTube, TikTok, X/Twitter, Instagram, Reddit, Vimeo, Twitch, and 1,000+ other sites in up to `4K (2160p)` or `1080p Full HD` MP4.

## Quick Start

Double-click `start.bat` or run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000** in your browser.

