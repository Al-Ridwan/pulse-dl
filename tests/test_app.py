from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.downloader import MediaDownloadManager, format_duration, parse_timestamp_to_seconds
from app.main import create_app


class FakeYoutubeDL:
    """Deterministic fake yt-dlp client for fast, offline unit & integration tests."""

    recorded_opts: list[Dict[str, Any]] = []

    def __init__(self, opts: Dict[str, Any]) -> None:
        self.opts = opts
        FakeYoutubeDL.recorded_opts.append(opts)

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def extract_info(self, url: str, download: bool = False) -> Dict[str, Any]:
        info = {
            "id": "demo123",
            "title": "Synthwave Midnight Drive",
            "uploader": "RetroWave Studio",
            "extractor_key": "Youtube",
            "duration": 215,
            "thumbnail": "https://i.ytimg.com/vi/demo123/maxresdefault.jpg",
            "webpage_url": url,
            "view_count": 42000,
            "formats": [
                {"vcodec": "none", "acodec": "opus", "abr": 160, "filesize": 3_800_000},
                {"vcodec": "avc1", "acodec": "none", "height": 720, "fps": 30, "filesize": 18_500_000},
                {"vcodec": "avc1", "acodec": "none", "height": 1080, "fps": 60, "filesize": 45_200_000},
                {"vcodec": "vp9", "acodec": "none", "height": 2160, "fps": 60, "filesize": 140_000_000},
            ],
        }
        if download:
            for hook in self.opts.get("progress_hooks", []):
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": 2_000_000,
                        "total_bytes": 4_000_000,
                        "speed": 5_200_000,
                        "eta": 1,
                    }
                )
                hook({"status": "finished"})

            outtmpl = self.opts.get("outtmpl", "")
            # Determine target extension based on postprocessors or merge_output_format
            ext = self.opts.get("merge_output_format", "mp4")
            for pp in self.opts.get("postprocessors", []):
                if pp.get("key") == "FFmpegExtractAudio":
                    ext = pp.get("preferredcodec", "mp3")

            out_path = Path(
                outtmpl.replace("%(title).100B", "Synthwave Midnight Drive").replace("%(ext)s", ext)
            )
            out_path.write_bytes(b"FAKE_MEDIA_BINARY_CONTENT_" * 64)
        return info


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200
        data = res.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.05)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


def test_helpers():
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"
    assert parse_timestamp_to_seconds("1:30") == 90.0
    assert parse_timestamp_to_seconds("01:02:03") == 3723.0


def test_probe_and_both_modules(tmp_path: Path):
    manager = MediaDownloadManager(
        downloads_dir=tmp_path,
        ffmpeg_dir=str(tmp_path),
        ydl_factory=FakeYoutubeDL,
    )
    client = TestClient(create_app(manager=manager))

    # 1. Health & UI root
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    index = client.get("/")
    assert index.status_code == 200
    assert "PulseDL" in index.text

    # 2. Probe endpoint
    probe = client.post("/api/probe", json={"url": "https://www.youtube.com/watch?v=demo123"})
    assert probe.status_code == 200
    pdata = probe.json()
    assert pdata["title"] == "Synthwave Midnight Drive"
    assert pdata["duration_text"] == "3:35"
    assert [r["height"] for r in pdata["resolutions"]] == [2160, 1080, 720]

    # 3. Module 1: High-quality MP3 extraction
    mp3_res = client.post(
        "/api/download/mp3",
        json={
            "url": "https://www.youtube.com/watch?v=demo123",
            "bitrate": "320",
            "embed_thumbnail": True,
            "embed_metadata": True,
            "trim_start": "0:10",
            "trim_end": "2:00",
        },
    )
    assert mp3_res.status_code == 200
    mp3_job = _wait_for_job(client, mp3_res.json()["id"])
    assert mp3_job["status"] == "completed"
    assert mp3_job["filename"].endswith(".mp3")

    dl_mp3 = client.get(f"/api/files/{mp3_job['filename']}")
    assert dl_mp3.status_code == 200
    assert len(dl_mp3.content) > 100

    # 4. Module 2: Universal Video download
    vid_res = client.post(
        "/api/download/video",
        json={
            "url": "https://vimeo.com/999888777",
            "resolution": "1080",
            "container": "mp4",
            "custom_title": "Custom Video Clip",
        },
    )
    assert vid_res.status_code == 200
    vid_job = _wait_for_job(client, vid_res.json()["id"])
    assert vid_job["status"] == "completed"
    assert vid_job["filename"] == "Custom Video Clip.mp4"

    # 5. Delete job
    del_res = client.delete(f"/api/jobs/{vid_job['id']}?delete_file=true")
    assert del_res.status_code == 200
    assert not (tmp_path / "Custom Video Clip.mp4").exists()


def test_health_and_deno_js_runtimes(tmp_path: Path):
    FakeYoutubeDL.recorded_opts = []
    fake_deno = tmp_path / "deno.exe"
    fake_deno.write_bytes(b"")

    manager = MediaDownloadManager(
        downloads_dir=tmp_path,
        ffmpeg_dir=str(tmp_path),
        deno_exe=str(fake_deno),
        ydl_factory=FakeYoutubeDL,
    )
    client = TestClient(create_app(manager=manager))

    health = client.get("/api/health")
    assert health.status_code == 200
    hdata = health.json()
    assert hdata["has_ffmpeg"] is True
    assert hdata["has_deno"] is True
    assert "portable" in hdata
    assert hdata["downloads_dir"] == str(tmp_path)

    # Probe should include js_runtimes
    probe = client.post("/api/probe", json={"url": "https://www.youtube.com/watch?v=demo123"})
    assert probe.status_code == 200

    # MP3 should include js_runtimes
    mp3_res = client.post(
        "/api/download/mp3",
        json={"url": "https://www.youtube.com/watch?v=demo123", "bitrate": "320"},
    )
    assert mp3_res.status_code == 200
    mp3_job = _wait_for_job(client, mp3_res.json()["id"])
    assert mp3_job["status"] == "completed"

    # Video should include js_runtimes
    vid_res = client.post(
        "/api/download/video",
        json={"url": "https://www.youtube.com/watch?v=demo123", "resolution": "1080"},
    )
    assert vid_res.status_code == 200
    vid_job = _wait_for_job(client, vid_res.json()["id"])
    assert vid_job["status"] == "completed"

    assert len(FakeYoutubeDL.recorded_opts) == 3
    for opts in FakeYoutubeDL.recorded_opts:
        assert opts["js_runtimes"] == {"deno": {"path": str(fake_deno)}}
        assert opts["ffmpeg_location"] == str(tmp_path)


def test_bundled_runtime_detection_priority(tmp_path: Path, monkeypatch):
    import app.downloader as dl

    bundled_ffmpeg = tmp_path / "runtime" / "ffmpeg"
    bundled_bin = tmp_path / "runtime" / "bin"
    env_ffmpeg = tmp_path / "external_ffmpeg"
    env_deno_dir = tmp_path / "external_deno"
    bundled_ffmpeg.mkdir(parents=True)
    bundled_bin.mkdir(parents=True)
    env_ffmpeg.mkdir(parents=True)
    env_deno_dir.mkdir(parents=True)

    (bundled_ffmpeg / "ffmpeg.exe").write_bytes(b"")
    (bundled_bin / "deno.exe").write_bytes(b"")
    (env_ffmpeg / "ffmpeg.exe").write_bytes(b"")
    ext_deno = env_deno_dir / "deno.exe"
    ext_deno.write_bytes(b"")

    monkeypatch.setattr(dl, "BASE_DIR", tmp_path)
    monkeypatch.setenv("FFMPEG_DIR", str(env_ffmpeg))
    monkeypatch.setenv("DENO_EXE", str(ext_deno))

    assert dl.find_ffmpeg_dir() == str(bundled_ffmpeg)
    assert dl.find_deno_exe() == str(bundled_bin / "deno.exe")


