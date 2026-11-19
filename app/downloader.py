from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yt_dlp


BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
JOBS_FILE = DOWNLOADS_DIR / "jobs_history.json"


def find_ffmpeg_dir() -> Optional[str]:
    """Locate ffmpeg/ffprobe directory, preferring bundled portable binaries."""
    bundled_dirs = [
        BASE_DIR / "runtime" / "ffmpeg",
        BASE_DIR / "runtime" / "bin",
    ]
    for candidate in bundled_dirs:
        if (candidate / "ffmpeg.exe").exists() or (candidate / "ffmpeg").exists():
            return str(candidate)

    env_dir = os.environ.get("FFMPEG_DIR")
    if env_dir and Path(env_dir).exists():
        return env_dir

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return str(Path(which_ffmpeg).resolve().parent)

    candidates = [
        Path(r"C:\pinokio\bin\miniforge\Library\bin"),
        Path(r"C:\pinokio\bin\miniconda\Library\bin"),
        Path.home() / "scoop" / "shims",
        Path(r"C:\ProgramData\chocolatey\bin"),
    ]
    for candidate in candidates:
        if (candidate / "ffmpeg.exe").exists() or (candidate / "ffmpeg").exists():
            return str(candidate)
    return None


def find_deno_exe() -> Optional[str]:
    """Locate deno executable for yt-dlp EJS, preferring bundled portable binaries."""
    bundled_bins = [
        BASE_DIR / "runtime" / "bin" / "deno.exe",
        BASE_DIR / "runtime" / "ffmpeg" / "deno.exe",
        BASE_DIR / "runtime" / "python" / "Scripts" / "deno.exe",
    ]
    for candidate in bundled_bins:
        if candidate.exists():
            return str(candidate)

    env_deno = os.environ.get("DENO_EXE")
    if env_deno and Path(env_deno).exists():
        return env_deno

    which_deno = shutil.which("deno")
    if which_deno:
        return str(Path(which_deno).resolve())
    return None


def format_bytes(num_bytes: Optional[float]) -> str:
    if not num_bytes or num_bytes <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    val = float(num_bytes)
    for unit in units:
        if val < 1024.0 or unit == units[-1]:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.1f} GB"


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "Live / Unknown"
    total = int(round(seconds))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def parse_timestamp_to_seconds(ts: Optional[str]) -> Optional[float]:
    """Parse 'MM:SS' or 'HH:MM:SS' or seconds string into float seconds."""
    if not ts or not ts.strip():
        return None
    raw = ts.strip()
    if not re.match(r"^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$", raw):
        raise ValueError(f"Invalid timestamp format: '{raw}'. Use MM:SS or HH:MM:SS.")
    parts = raw.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Invalid timestamp format: '{raw}'.")


def sanitize_filename(name: str) -> str:
    """Create a clean, filesystem-safe base filename."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:140] or "download"


@dataclass
class DownloadJob:
    id: str
    url: str
    mode: str  # "mp3" or "video"
    title: str = "Fetching media info..."
    uploader: str = ""
    thumbnail: str = ""
    site: str = ""
    duration_text: str = ""
    quality_label: str = ""
    status: str = "queued"  # queued, downloading, processing, completed, failed
    progress: float = 0.0
    speed_text: str = ""
    eta_text: str = ""
    downloaded_text: str = ""
    total_text: str = ""
    filename: str = ""
    file_size_bytes: int = 0
    file_size_text: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MediaDownloadManager:
    """Manages media probing, MP3 audio extraction, and universal video downloads."""

    def __init__(
        self,
        downloads_dir: Path = DOWNLOADS_DIR,
        ffmpeg_dir: Optional[str] = None,
        deno_exe: Optional[str] = None,
        ydl_factory: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> None:
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.downloads_dir / "jobs_history.json"
        self.ffmpeg_dir = ffmpeg_dir if ffmpeg_dir is not None else find_ffmpeg_dir()
        self.deno_exe = deno_exe if deno_exe is not None else find_deno_exe()
        self.ydl_factory = ydl_factory or yt_dlp.YoutubeDL
        self._lock = threading.Lock()
        self._jobs: Dict[str, DownloadJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="pulsedl")
        self._load_history()

    def _base_ydl_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {}
        if self.ffmpeg_dir:
            opts["ffmpeg_location"] = self.ffmpeg_dir
        if self.deno_exe:
            opts["js_runtimes"] = {"deno": {"path": self.deno_exe}}
        return opts

    def _load_history(self) -> None:
        if not self.jobs_file.exists():
            return
        try:
            data = json.loads(self.jobs_file.read_text(encoding="utf-8"))
            for item in data:
                job = DownloadJob(**item)
                if job.status in ("queued", "downloading", "processing"):
                    job.status = "failed"
                    job.error = "Interrupted by server restart"
                if job.filename and not (self.downloads_dir / job.filename).exists():
                    continue
                self._jobs[job.id] = job
        except Exception:
            pass

    def _save_history(self) -> None:
        try:
            items = [
                job.to_dict()
                for job in sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:100]
            ]
            self.jobs_file.write_text(json.dumps(items, indent=2), encoding="utf-8")
        except Exception:
            pass

    def probe_url(self, url: str) -> Dict[str, Any]:
        """Extract metadata, thumbnail, duration, and available video/audio formats."""
        opts: Dict[str, Any] = {
            **self._base_ydl_opts(),
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        with self.ydl_factory(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if info.get("_type") == "playlist" and info.get("entries"):
            entries = [e for e in info["entries"] if e]
            if entries:
                info = entries[0]

        formats = info.get("formats") or []
        resolutions_map: Dict[int, Dict[str, Any]] = {}
        best_audio_abr: float = 0.0

        for fmt in formats:
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            height = fmt.get("height")
            abr = fmt.get("abr") or 0
            if acodec and acodec != "none" and abr and abr > best_audio_abr:
                best_audio_abr = float(abr)

            if vcodec and vcodec != "none" and isinstance(height, int) and height >= 144:
                filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0
                fps = fmt.get("fps") or 30
                existing = resolutions_map.get(height)
                if not existing or filesize > existing.get("filesize", 0):
                    label_map = {
                        2160: "4K Ultra HD (2160p)",
                        1440: "2K QHD (1440p)",
                        1080: "Full HD (1080p)",
                        720: "HD (720p)",
                        480: "Standard (480p)",
                        360: "Medium (360p)",
                        240: "Low (240p)",
                    }
                    resolutions_map[height] = {
                        "height": height,
                        "label": label_map.get(height, f"{height}p"),
                        "fps": int(fps) if fps else 30,
                        "filesize": filesize,
                        "filesize_text": format_bytes(filesize) if filesize else "Auto",
                    }

        sorted_resolutions = sorted(
            resolutions_map.values(), key=lambda r: r["height"], reverse=True
        )
        duration = info.get("duration")

        return {
            "title": info.get("title") or "Untitled Media",
            "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key") or "Unknown Source",
            "site": info.get("extractor_key") or info.get("extractor") or "Web",
            "duration": duration,
            "duration_text": format_duration(duration),
            "thumbnail": info.get("thumbnail") or "",
            "webpage_url": info.get("webpage_url") or url,
            "view_count": info.get("view_count"),
            "best_audio_kbps": int(round(best_audio_abr)) if best_audio_abr else 160,
            "resolutions": sorted_resolutions,
            "has_ffmpeg": bool(self.ffmpeg_dir),
        }

    def start_mp3_job(
        self,
        url: str,
        bitrate: str = "320",
        embed_thumbnail: bool = True,
        embed_metadata: bool = True,
        trim_start: Optional[str] = None,
        trim_end: Optional[str] = None,
        custom_title: Optional[str] = None,
    ) -> DownloadJob:
        start_sec = parse_timestamp_to_seconds(trim_start)
        end_sec = parse_timestamp_to_seconds(trim_end)
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            raise ValueError("End timestamp must be greater than start timestamp.")

        job_id = uuid.uuid4().hex[:10]
        trim_badge = ""
        if start_sec is not None or end_sec is not None:
            trim_badge = f" (Clip {trim_start or '0:00'}→{trim_end or 'end'})"

        job = DownloadJob(
            id=job_id,
            url=url,
            mode="mp3",
            title=custom_title.strip() if custom_title and custom_title.strip() else "Fetching audio stream...",
            quality_label=f"MP3 • {bitrate} kbps{trim_badge}",
        )
        with self._lock:
            self._jobs[job_id] = job
            self._save_history()

        self._executor.submit(
            self._run_mp3_download,
            job_id,
            url,
            bitrate,
            embed_thumbnail,
            embed_metadata,
            start_sec,
            end_sec,
            custom_title,
        )
        return job

    def start_video_job(
        self,
        url: str,
        resolution: str = "best",
        container: str = "mp4",
        trim_start: Optional[str] = None,
        trim_end: Optional[str] = None,
        custom_title: Optional[str] = None,
    ) -> DownloadJob:
        start_sec = parse_timestamp_to_seconds(trim_start)
        end_sec = parse_timestamp_to_seconds(trim_end)
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            raise ValueError("End timestamp must be greater than start timestamp.")

        job_id = uuid.uuid4().hex[:10]
        res_label = "Best Quality" if resolution == "best" else f"{resolution}p"
        trim_badge = ""
        if start_sec is not None or end_sec is not None:
            trim_badge = f" (Clip {trim_start or '0:00'}→{trim_end or 'end'})"

        job = DownloadJob(
            id=job_id,
            url=url,
            mode="video",
            title=custom_title.strip() if custom_title and custom_title.strip() else "Fetching video stream...",
            quality_label=f"{container.upper()} • {res_label}{trim_badge}",
        )
        with self._lock:
            self._jobs[job_id] = job
            self._save_history()

        self._executor.submit(
            self._run_video_download,
            job_id,
            url,
            resolution,
            container,
            start_sec,
            end_sec,
            custom_title,
        )
        return job

    def _make_progress_hook(self, job_id: str) -> Callable[[Dict[str, Any]], None]:
        def hook(d: Dict[str, Any]) -> None:
            status = d.get("status")
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                if status == "downloading":
                    job.status = "downloading"
                    downloaded = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    if total > 0:
                        job.progress = round(min(99.0, (downloaded / total) * 100.0), 1)
                    job.downloaded_text = format_bytes(downloaded)
                    job.total_text = format_bytes(total) if total else ""
                    speed = d.get("speed")
                    job.speed_text = f"{format_bytes(speed)}/s" if speed else ""
                    eta = d.get("eta")
                    job.eta_text = format_duration(eta) if eta is not None else ""
                elif status == "finished":
                    job.progress = 99.0
                    job.status = "processing"
                    job.speed_text = "Finalizing with FFmpeg..."
                    job.eta_text = ""

        return hook

    def _populate_job_info(self, job_id: str, info: Dict[str, Any], custom_title: Optional[str]) -> str:
        title = (custom_title.strip() if custom_title and custom_title.strip() else None) or info.get("title") or "Media Download"
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.title = title
                job.uploader = info.get("uploader") or info.get("channel") or info.get("extractor_key") or ""
                job.thumbnail = info.get("thumbnail") or ""
                job.site = info.get("extractor_key") or info.get("extractor") or "Web"
                job.duration_text = format_duration(info.get("duration"))
        return sanitize_filename(title)

    def _run_mp3_download(
        self,
        job_id: str,
        url: str,
        bitrate: str,
        embed_thumbnail: bool,
        embed_metadata: bool,
        start_sec: Optional[float],
        end_sec: Optional[float],
        custom_title: Optional[str],
    ) -> None:
        try:
            temp_prefix = f"{job_id}_"
            outtmpl = str(self.downloads_dir / f"{temp_prefix}%(title).100B.%(ext)s")

            postprocessors: List[Dict[str, Any]] = []
            if embed_thumbnail:
                postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate),
                }
            )
            if embed_metadata:
                postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})
            if embed_thumbnail:
                postprocessors.append({"key": "EmbedThumbnail"})

            opts: Dict[str, Any] = {
                **self._base_ydl_opts(),
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "writethumbnail": embed_thumbnail,
                "postprocessors": postprocessors,
                "progress_hooks": [self._make_progress_hook(job_id)],
            }

            if start_sec is not None or end_sec is not None:
                ff_args: List[str] = []
                if start_sec is not None:
                    ff_args.extend(["-ss", str(start_sec)])
                if end_sec is not None:
                    ff_args.extend(["-to", str(end_sec)])
                opts["postprocessor_args"] = {"extractaudio": ff_args}

            with self.ydl_factory(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if info.get("_type") == "playlist" and info.get("entries"):
                info = [e for e in info["entries"] if e][0]

            clean_base = self._populate_job_info(job_id, info, custom_title)
            final_file = self._finalize_output_file(job_id, temp_prefix, clean_base, ".mp3")

            with self._lock:
                job = self._jobs[job_id]
                job.filename = final_file.name
                job.file_size_bytes = final_file.stat().st_size
                job.file_size_text = format_bytes(job.file_size_bytes)
                job.progress = 100.0
                job.status = "completed"
                job.speed_text = ""
                job.eta_text = ""
                self._save_history()

        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    job.speed_text = ""
                    self._save_history()

    def _run_video_download(
        self,
        job_id: str,
        url: str,
        resolution: str,
        container: str,
        start_sec: Optional[float],
        end_sec: Optional[float],
        custom_title: Optional[str],
    ) -> None:
        try:
            temp_prefix = f"{job_id}_"
            outtmpl = str(self.downloads_dir / f"{temp_prefix}%(title).100B.%(ext)s")

            if resolution != "best" and resolution.isdigit():
                h = int(resolution)
                fmt_str = (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={h}]+bestaudio/"
                    f"best[height<={h}]/best"
                )
            else:
                fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

            opts: Dict[str, Any] = {
                **self._base_ydl_opts(),
                "format": fmt_str,
                "merge_output_format": container,
                "outtmpl": outtmpl,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._make_progress_hook(job_id)],
            }

            if start_sec is not None or end_sec is not None:
                ff_args: List[str] = []
                if start_sec is not None:
                    ff_args.extend(["-ss", str(start_sec)])
                if end_sec is not None:
                    ff_args.extend(["-to", str(end_sec)])
                opts["postprocessor_args"] = {"merger": ff_args, "ffmpeg": ff_args}

            with self.ydl_factory(opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if info.get("_type") == "playlist" and info.get("entries"):
                info = [e for e in info["entries"] if e][0]

            clean_base = self._populate_job_info(job_id, info, custom_title)
            final_file = self._finalize_output_file(job_id, temp_prefix, clean_base, f".{container}")

            with self._lock:
                job = self._jobs[job_id]
                job.filename = final_file.name
                job.file_size_bytes = final_file.stat().st_size
                job.file_size_text = format_bytes(job.file_size_bytes)
                job.progress = 100.0
                job.status = "completed"
                job.speed_text = ""
                job.eta_text = ""
                self._save_history()

        except Exception as exc:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job.status = "failed"
                    job.error = str(exc)
                    job.speed_text = ""
                    self._save_history()

    def _finalize_output_file(
        self, job_id: str, temp_prefix: str, clean_base: str, preferred_ext: str
    ) -> Path:
        """Locate the downloaded file for job_id and rename it to a clean human-readable filename."""
        candidates = [
            p
            for p in self.downloads_dir.iterdir()
            if p.is_file()
            and p.name.startswith(temp_prefix)
            and not p.name.endswith((".part", ".ytdl", ".jpg", ".webp", ".png"))
        ]
        if not candidates:
            raise FileNotFoundError("Download completed but output file was not found on disk.")

        # Prefer file matching preferred_ext, otherwise largest file
        matching = [p for p in candidates if p.suffix.lower() == preferred_ext.lower()]
        chosen = matching[0] if matching else max(candidates, key=lambda p: p.stat().st_size)

        target_ext = chosen.suffix or preferred_ext
        target_path = self.downloads_dir / f"{clean_base}{target_ext}"
        counter = 1
        while target_path.exists() and target_path != chosen:
            target_path = self.downloads_dir / f"{clean_base} ({counter}){target_ext}"
            counter += 1

        chosen.rename(target_path)

        # Clean up any leftover temp thumbnail files for this job
        for leftover in self.downloads_dir.iterdir():
            if leftover.is_file() and leftover.name.startswith(temp_prefix) and leftover != target_path:
                try:
                    leftover.unlink()
                except OSError:
                    pass

        return target_path

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                job.to_dict()
                for job in sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            ]

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_dict() if job else None

    def delete_job(self, job_id: str, delete_file: bool = True) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return False
            if delete_file and job.filename:
                fpath = self.downloads_dir / job.filename
                if fpath.exists():
                    try:
                        fpath.unlink()
                    except OSError:
                        pass
            self._save_history()
            return True

