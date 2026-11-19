from __future__ import annotations

import mimetypes
import os
import subprocess
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.downloader import BASE_DIR, DOWNLOADS_DIR, MediaDownloadManager


STATIC_DIR = BASE_DIR / "static"


def validate_http_url(value: str) -> str:
    cleaned = (value or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Please enter a valid http:// or https:// URL.")
    return cleaned


class ProbeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return validate_http_url(v)


class Mp3DownloadRequest(BaseModel):
    url: str
    bitrate: Literal["320", "256", "192", "128"] = "320"
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    trim_start: Optional[str] = Field(default=None, description="Optional MM:SS or HH:MM:SS")
    trim_end: Optional[str] = Field(default=None, description="Optional MM:SS or HH:MM:SS")
    custom_title: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return validate_http_url(v)


class VideoDownloadRequest(BaseModel):
    url: str
    resolution: Literal["best", "2160", "1440", "1080", "720", "480", "360"] = "best"
    container: Literal["mp4", "mkv", "webm"] = "mp4"
    trim_start: Optional[str] = Field(default=None, description="Optional MM:SS or HH:MM:SS")
    trim_end: Optional[str] = Field(default=None, description="Optional MM:SS or HH:MM:SS")
    custom_title: Optional[str] = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return validate_http_url(v)


def create_app(manager: Optional[MediaDownloadManager] = None) -> FastAPI:
    app = FastAPI(
        title="PulseDL — Studio MP3 Extractor & Universal Video Downloader",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    dl_manager = manager or MediaDownloadManager(downloads_dir=DOWNLOADS_DIR)
    app.state.manager = dl_manager

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "has_ffmpeg": bool(dl_manager.ffmpeg_dir),
            "has_deno": bool(dl_manager.deno_exe),
            "portable": (BASE_DIR / "runtime" / "python" / "python.exe").exists(),
            "ffmpeg_dir": dl_manager.ffmpeg_dir,
            "deno_exe": dl_manager.deno_exe,
            "downloads_dir": str(dl_manager.downloads_dir),
        }

    @app.post("/api/probe")
    def probe_media(req: ProbeRequest) -> dict:
        try:
            return dl_manager.probe_url(req.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not inspect link: {exc}") from exc

    @app.post("/api/download/mp3")
    def start_mp3(req: Mp3DownloadRequest) -> dict:
        try:
            job = dl_manager.start_mp3_job(
                url=req.url,
                bitrate=req.bitrate,
                embed_thumbnail=req.embed_thumbnail,
                embed_metadata=req.embed_metadata,
                trim_start=req.trim_start,
                trim_end=req.trim_end,
                custom_title=req.custom_title,
            )
            return job.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/download/video")
    def start_video(req: VideoDownloadRequest) -> dict:
        try:
            job = dl_manager.start_video_job(
                url=req.url,
                resolution=req.resolution,
                container=req.container,
                trim_start=req.trim_start,
                trim_end=req.trim_end,
                custom_title=req.custom_title,
            )
            return job.to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        return {"jobs": dl_manager.list_jobs()}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = dl_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str, delete_file: bool = Query(default=True)) -> dict:
        ok = dl_manager.delete_job(job_id, delete_file=delete_file)
        if not ok:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"deleted": True, "id": job_id}

    @app.get("/api/files/{filename}")
    def download_file(filename: str, inline: bool = Query(default=False)):
        safe_name = Path(filename).name
        file_path = (dl_manager.downloads_dir / safe_name).resolve()
        if not file_path.exists() or file_path.parent != dl_manager.downloads_dir.resolve():
            raise HTTPException(status_code=404, detail="File not found")

        media_type, _ = mimetypes.guess_type(str(file_path))
        disposition = "inline" if inline else "attachment"
        return FileResponse(
            path=str(file_path),
            media_type=media_type or "application/octet-stream",
            filename=safe_name if not inline else None,
            content_disposition_type=disposition,
        )

    @app.post("/api/open-folder")
    def open_downloads_folder() -> dict:
        folder = str(dl_manager.downloads_dir.resolve())
        if os.name == "nt":
            try:
                os.startfile(folder)
            except OSError:
                subprocess.Popen(["explorer.exe", folder])
        return {"opened": folder}

    if STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


app = create_app()

