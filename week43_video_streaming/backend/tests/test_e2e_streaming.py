"""End-to-end stress, concurrency, and chaos test suite for PulseStream.

Validates high-concurrency byte-range seeking, simultaneous HLS segment delivery,
malformed range request resilience, disk missing asset chaos, and queue safety.
"""

import io
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from flask.testing import FlaskClient

from app.db.connection import get_db_connection
from app.models.category import CategoryModel
from app.models.video import VideoModel
from app.services.storage_service import StorageService
from tests.helpers import generate_sample_mp4


@pytest.fixture
def seeded_e2e_video(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> Dict[str, Any]:
    """Create and seed a synthetic MP4 video asset with HLS renditions for testing."""
    storage = StorageService(media_dir=temp_dir / "media")
    video_id = "e2e-bench-video"
    raw_filename = f"{video_id}.mp4"

    raw_path = storage.get_raw_video_path(raw_filename)
    generate_sample_mp4(raw_path, duration_seconds=10.0)
    raw_size = raw_path.stat().st_size

    # Create HLS master and variant chunks
    hls_dir = storage.get_video_hls_dir(video_id)
    master_content = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,NAME="720p"\n'
        "stream_720p.m3u8\n"
    )
    (hls_dir / "master.m3u8").write_text(master_content, encoding="utf-8")

    ts_chunk = b"\x47\x40\x00\x10" + b"\xff" * 184
    variant_content = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:4\n"
        "#EXTINF:4.000000,\n"
        "seg_000.ts\n"
        "#EXTINF:4.000000,\n"
        "seg_001.ts\n"
        "#EXT-X-ENDLIST\n"
    )
    (hls_dir / "stream_720p.m3u8").write_text(variant_content, encoding="utf-8")
    (hls_dir / "seg_000.ts").write_bytes(ts_chunk * 10)
    (hls_dir / "seg_001.ts").write_bytes(ts_chunk * 10)

    conn = get_db_connection(test_db_path)
    try:
        cat = CategoryModel.create(conn, "Stress Benchmarks", "stress-benchmarks")
        video = VideoModel.create(
            conn=conn,
            title="E2E Streaming Benchmark Video",
            filename=raw_filename,
            category_id=cat["id"],
            duration=10.0,
            size_bytes=raw_size,
            mime_type="video/mp4",
            video_id=video_id,
            status="ready",
        )
        return video
    finally:
        conn.close()


def test_concurrent_byte_range_seeking(
    client: FlaskClient, seeded_e2e_video: Dict[str, Any], temp_dir: Path
) -> None:
    """Stress test high-concurrency byte-range seeking across threads."""
    video_id = seeded_e2e_video["id"]
    storage = StorageService(media_dir=temp_dir / "media")
    raw_path = storage.get_raw_video_path(seeded_e2e_video["filename"])
    full_bytes = raw_path.read_bytes()
    total_size = len(full_bytes)

    assert total_size > 500

    def request_range(start: int, end: int) -> Tuple[int, bytes, str]:
        headers = {"Range": f"bytes={start}-{end}"}
        resp = client.get(f"/api/videos/{video_id}/stream", headers=headers)
        return resp.status_code, resp.data, resp.headers.get("Content-Range", "")

    # Generate 25 randomized range intervals
    ranges: List[Tuple[int, int]] = []
    for _ in range(25):
        s = random.randint(0, total_size - 100)
        e = random.randint(s + 20, min(total_size - 1, s + 300))
        ranges.append((s, e))

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_range = {
            executor.submit(request_range, s, e): (s, e) for s, e in ranges
        }
        for future in as_completed(future_to_range):
            s, e = future_to_range[future]
            status_code, data, content_range = future.result()

            assert status_code == 206
            expected_range = f"bytes {s}-{e}/{total_size}"
            assert content_range == expected_range
            assert len(data) == (e - s + 1)
            end_idx = e + 1
            assert data == full_bytes[s:end_idx]


def test_concurrent_hls_chunk_requests(
    client: FlaskClient, seeded_e2e_video: Dict[str, Any]
) -> None:
    """Verify concurrent HLS playlist and transport stream segment delivery."""
    video_id = seeded_e2e_video["id"]

    # First fetch master playlist
    resp_master = client.get(f"/api/videos/{video_id}/hls/master.m3u8")
    assert resp_master.status_code == 200
    assert "stream_720p.m3u8" in resp_master.get_data(as_text=True)

    # Concurrently fetch variant playlist and multiple TS segments
    def fetch_asset(asset_name: str) -> Tuple[int, bytes, str]:
        resp = client.get(f"/api/videos/{video_id}/hls/{asset_name}")
        return resp.status_code, resp.data, resp.headers.get("Content-Type", "")

    assets = [
        "stream_720p.m3u8",
        "seg_000.ts",
        "seg_001.ts",
        "seg_000.ts",
        "seg_001.ts",
        "stream_720p.m3u8",
    ]

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch_asset, assets))

    for status_code, data, content_type in results:
        assert status_code == 200
        assert len(data) > 0
        is_hls = "application/vnd.apple.mpegurl" in content_type
        is_ts = "video/mp2t" in content_type
        assert is_hls or is_ts


def test_chaos_range_requests(
    client: FlaskClient, seeded_e2e_video: Dict[str, Any]
) -> None:
    """Verify robust handling of corrupt, inverted, or out-of-bounds byte ranges."""
    video_id = seeded_e2e_video["id"]

    # Range seeking past EOF returns 416 Range Not Satisfiable
    resp_past_eof = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=90000000-99999999"},
    )
    assert resp_past_eof.status_code == 416
    assert "bytes */" in resp_past_eof.headers.get("Content-Range", "")

    # Inverted range where start > end returns 416
    resp_inverted = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=500-200"},
    )
    assert resp_inverted.status_code == 416

    # Malformed range header syntax returns 416
    resp_malformed = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "bytes=not-a-number"},
    )
    assert resp_malformed.status_code == 416

    # Invalid unit returns 416
    resp_bad_unit = client.get(
        f"/api/videos/{video_id}/stream",
        headers={"Range": "items=0-100"},
    )
    assert resp_bad_unit.status_code == 416


def test_chaos_missing_file_during_stream(
    client: FlaskClient, seeded_e2e_video: Dict[str, Any], temp_dir: Path
) -> None:
    """Verify graceful 404 response when video record exists but file is missing."""
    video_id = seeded_e2e_video["id"]
    storage = StorageService(media_dir=temp_dir / "media")
    raw_path = storage.get_raw_video_path(seeded_e2e_video["filename"])

    # Remove the physical file on disk
    if raw_path.exists():
        raw_path.unlink()

    resp = client.get(f"/api/videos/{video_id}/stream")
    assert resp.status_code == 404
    assert "not found" in resp.get_data(as_text=True).lower()


def test_chaos_upload_rejections(client: FlaskClient) -> None:
    """Verify rejection of non-video payloads, empty files, and malformed requests."""
    # Rejection of executable/script extensions
    resp_bad_ext = client.post(
        "/api/videos/upload",
        data={
            "video": (io.BytesIO(b"#!/bin/bash\necho hack"), "malicious.sh"),
            "title": "Malicious Script",
        },
        content_type="multipart/form-data",
    )
    assert resp_bad_ext.status_code == 400
    assert "Unsupported format" in resp_bad_ext.get_json()["error"]

    # Rejection of PDF document upload
    resp_pdf = client.post(
        "/api/videos/upload",
        data={
            "video": (io.BytesIO(b"%PDF-1.4 dummy pdf"), "document.pdf"),
            "title": "Document",
        },
        content_type="multipart/form-data",
    )
    assert resp_pdf.status_code == 400
    assert "Unsupported format" in resp_pdf.get_json()["error"]

    # Rejection when file field is omitted
    resp_no_file = client.post(
        "/api/videos/upload",
        data={"title": "No File Provided"},
        content_type="multipart/form-data",
    )
    assert resp_no_file.status_code == 400
    assert "Missing video file" in resp_no_file.get_json()["error"]


def test_transcoding_queue_stress_concurrency(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify queue and worker handle multiple tasks without SQLite lock errors."""
    storage = StorageService(media_dir=temp_dir / "media")
    t_queue = client.application.transcoding_queue

    # Create 3 synthetic video files and database records
    video_ids = []
    for i in range(3):
        v_id = f"stress-vid-{i}"
        raw_path = storage.get_raw_video_path(f"{v_id}.mp4")
        generate_sample_mp4(raw_path, duration_seconds=2.0)

        conn = get_db_connection(test_db_path)
        try:
            VideoModel.create(
                conn=conn,
                title=f"Stress Task {i}",
                filename=f"{v_id}.mp4",
                duration=2.0,
                size_bytes=raw_path.stat().st_size,
                video_id=v_id,
                status="pending",
            )
        finally:
            conn.close()

        video_ids.append(v_id)

    # Concurrently enqueue all 3 tasks
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs = list(executor.map(t_queue.enqueue, video_ids))

    assert len(jobs) == 3
    assert all(j["status"] == "queued" for j in jobs)

    # Process all 3 sequentially through the queue engine
    for job in jobs:
        success = t_queue.process_single(job["id"])
        assert success is True
        job_state = t_queue.get_job_status(job["id"])
        assert job_state is not None
        assert job_state["status"] == "completed"
        assert job_state["progress"] == 100
