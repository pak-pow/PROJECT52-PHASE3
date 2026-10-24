"""Integration tests for PulseStream REST API endpoints."""

import io
from pathlib import Path
from unittest.mock import patch

from flask.testing import FlaskClient

from app.db.connection import get_db_connection
from app.models.category import CategoryModel
from app.models.video import VideoModel
from app.services.storage_service import StorageService
from tests.helpers import generate_sample_mp4


def test_list_categories_endpoint(client: FlaskClient, test_db_path: Path) -> None:
    """Verify /api/categories returns seeded or added categories."""
    conn = get_db_connection(test_db_path)
    try:
        CategoryModel.create(conn, "Gaming", "gaming", "Gaming content")
    finally:
        conn.close()

    resp = client.get("/api/categories")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "categories" in data
    assert any(c["slug"] == "gaming" for c in data["categories"])


def test_upload_video_validation_errors(client: FlaskClient) -> None:
    """Verify 400 Bad Request on missing file or unsupported formats."""
    # Missing file parameter
    resp_empty = client.post("/api/videos/upload", data={})
    assert resp_empty.status_code == 400
    assert "Missing video file" in resp_empty.get_json()["error"]

    # Empty filename
    dummy_empty = (io.BytesIO(b""), "")
    resp_no_name = client.post(
        "/api/videos/upload",
        data={"video": dummy_empty},
        content_type="multipart/form-data",
    )
    assert resp_no_name.status_code == 400
    assert "No file selected" in resp_no_name.get_json()["error"]

    # Unsupported format
    dummy_data = (io.BytesIO(b"binary"), "malware.exe")
    resp_bad_ext = client.post(
        "/api/videos/upload",
        data={"video": dummy_data, "title": "Bad File"},
        content_type="multipart/form-data",
    )
    assert resp_bad_ext.status_code == 400
    assert "Unsupported format" in resp_bad_ext.get_json()["error"]


def test_upload_video_success_and_fallback_title(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify multipart upload, disk saving, and fallback title generation."""
    sample_mp4_bytes = temp_dir / "sample_src.mp4"
    generate_sample_mp4(sample_mp4_bytes, duration_seconds=5.0)
    raw_bytes = sample_mp4_bytes.read_bytes()

    conn = get_db_connection(test_db_path)
    try:
        cat = CategoryModel.create(conn, "AI", "ai")
    finally:
        conn.close()

    # Upload without title parameter, should derive title from filename
    upload_data = {
        "video": (io.BytesIO(raw_bytes), "neural_networks.mp4"),
        "category_id": str(cat["id"]),
    }
    resp = client.post(
        "/api/videos/upload",
        data=upload_data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    data = resp.get_json()

    assert "video" in data
    assert "job" in data
    assert data["video"]["title"] == "neural_networks"
    assert data["video"]["status"] == "pending"
    assert data["video"]["stream_url"].startswith("/api/videos/")
    assert data["video"]["hls_url"].endswith("/hls/master.m3u8")
    assert data["job"]["status"] == "queued"

    # Verify file saved on disk
    storage = StorageService(media_dir=temp_dir / "media")
    saved_file = storage.get_raw_video_path(data["video"]["filename"])
    assert saved_file.exists()


def test_list_videos_and_query_filters(client: FlaskClient, test_db_path: Path) -> None:
    """Verify video catalog listing with search and category filtering."""
    conn = get_db_connection(test_db_path)
    try:
        cat1 = CategoryModel.create(conn, "Science", "science")
        cat2 = CategoryModel.create(conn, "Art", "art")

        v1 = VideoModel.create(
            conn,
            title="Astrophysics Deep Dive",
            filename="astro.mp4",
            category_id=cat1["id"],
            status="ready",
        )
        v2 = VideoModel.create(
            conn,
            title="Oil Painting Workshop",
            filename="art.mp4",
            category_id=cat2["id"],
            status="ready",
        )
    finally:
        conn.close()

    # List all
    resp_all = client.get("/api/videos")
    assert resp_all.status_code == 200
    assert resp_all.get_json()["count"] >= 2

    # Filter by category
    resp_cat = client.get(f"/api/videos?category_id={cat1['id']}")
    assert resp_cat.status_code == 200
    videos_cat = resp_cat.get_json()["videos"]
    assert len(videos_cat) == 1
    assert videos_cat[0]["id"] == v1["id"]

    # Filter by search term
    resp_search = client.get("/api/videos?search=Painting")
    assert resp_search.status_code == 200
    videos_search = resp_search.get_json()["videos"]
    assert len(videos_search) == 1
    assert videos_search[0]["id"] == v2["id"]


def test_get_video_details_and_view_increment(
    client: FlaskClient, test_db_path: Path
) -> None:
    """Verify video retrieval, rendition listing, and atomic view incrementing."""
    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(
            conn,
            title="Views Increment Test",
            filename="views.mp4",
            status="ready",
        )
        VideoModel.add_rendition(
            conn,
            video_id=video["id"],
            resolution="720p",
            width=1280,
            height=720,
            bitrate_kbps=2500,
            playlist_path=f"hls/{video['id']}/stream_720p.m3u8",
        )
    finally:
        conn.close()

    # Initial view count is 0, fetching video should increment to 1
    resp = client.get(f"/api/videos/{video['id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["video"]["views_count"] == 1
    assert len(data["renditions"]) == 1
    assert data["renditions"][0]["resolution"] == "720p"

    # Second fetch increments to 2
    resp2 = client.get(f"/api/videos/{video['id']}")
    assert resp2.get_json()["video"]["views_count"] == 2

    # Nonexistent video returns 404
    resp_404 = client.get("/api/videos/nonexistent-id")
    assert resp_404.status_code == 404


def test_stream_video_endpoint(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify /api/videos/<id>/stream serves RFC 7233 partial content."""
    storage = StorageService(media_dir=temp_dir / "media")
    raw_file = storage.get_raw_video_path("stream_test.mp4")
    raw_payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 40  # 1040 bytes
    raw_file.write_bytes(raw_payload)

    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(
            conn,
            title="Stream Route Test",
            filename="stream_test.mp4",
            size_bytes=len(raw_payload),
            status="ready",
        )
    finally:
        conn.close()

    # Request range 10-29 (20 bytes)
    headers = {"Range": "bytes=10-29"}
    resp = client.get(f"/api/videos/{video['id']}/stream", headers=headers)
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == f"bytes 10-29/{len(raw_payload)}"
    assert resp.headers["Content-Length"] == "20"
    assert resp.data == raw_payload[10:30]

    # Nonexistent video returns 404
    resp_missing = client.get("/api/videos/unknown/stream")
    assert resp_missing.status_code == 404


def test_serve_hls_assets(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify serving master.m3u8, variant playlists, and .ts segment chunks."""
    storage = StorageService(media_dir=temp_dir / "media")
    hls_dir = storage.get_video_hls_dir("vid-hls-1")

    master_path = hls_dir / "master.m3u8"
    master_path.write_text("#EXTM3U\n#EXT-X-VERSION:3\n", encoding="utf-8")

    segment_path = hls_dir / "720p_seg_000.ts"
    segment_path.write_bytes(b"\x47" * 188)

    # Fetch master manifest
    resp_master = client.get("/api/videos/vid-hls-1/hls/master.m3u8")
    assert resp_master.status_code == 200
    assert "application/vnd.apple.mpegurl" in resp_master.headers["Content-Type"]
    assert b"#EXTM3U" in resp_master.data

    # Fetch segment chunk
    resp_seg = client.get("/api/videos/vid-hls-1/hls/720p_seg_000.ts")
    assert resp_seg.status_code == 200
    assert "video/mp2t" in resp_seg.headers["Content-Type"]
    assert resp_seg.data == b"\x47" * 188

    # Nonexistent HLS asset returns 404
    resp_missing = client.get("/api/videos/vid-hls-1/hls/missing.ts")
    assert resp_missing.status_code == 404

    # Path traversal returns 403 or 404
    resp_traversal = client.get("/api/videos/vid-hls-1/hls/../../passwords.txt")
    assert resp_traversal.status_code in (403, 404)


def test_serve_thumbnails_and_delete_video(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify thumbnail serving and cascading deletion of records and media."""
    storage = StorageService(media_dir=temp_dir / "media")

    thumb_file = storage.get_thumbnail_path("test_thumb.jpg")
    thumb_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    raw_file = storage.get_raw_video_path("del_clip.mp4")
    raw_file.write_bytes(b"delete me")

    hls_dir = storage.get_video_hls_dir("vid-del-1")
    (hls_dir / "master.m3u8").write_text("#EXTM3U", encoding="utf-8")

    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(
            conn,
            title="Video To Delete",
            filename="del_clip.mp4",
            poster_path="test_thumb.jpg",
            video_id="vid-del-1",
        )
    finally:
        conn.close()

    # Check thumbnail serving
    resp_thumb = client.get("/api/thumbnails/test_thumb.jpg")
    assert resp_thumb.status_code == 200
    assert "image/jpeg" in resp_thumb.headers["Content-Type"]

    # Missing thumbnail returns 404
    resp_no_thumb = client.get("/api/thumbnails/missing.jpg")
    assert resp_no_thumb.status_code == 404

    # Delete video
    resp_del = client.delete(f"/api/videos/{video['id']}")
    assert resp_del.status_code == 200

    # Verify database record gone
    conn = get_db_connection(test_db_path)
    try:
        assert VideoModel.get_by_id(conn, video["id"]) is None
    finally:
        conn.close()

    # Verify files removed from disk
    assert not raw_file.exists()
    assert not hls_dir.exists()
    assert not thumb_file.exists()

    # Deleting again returns 404
    resp_del_404 = client.delete(f"/api/videos/{video['id']}")
    assert resp_del_404.status_code == 404


def test_job_status_endpoints(
    client: FlaskClient, temp_dir: Path, test_db_path: Path
) -> None:
    """Verify /api/jobs/:id and /api/jobs/active polling endpoints."""
    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(conn, title="Job Polling Test", filename="f.mp4")
    finally:
        conn.close()

    # Enqueue job via client app
    t_queue = client.application.transcoding_queue
    job = t_queue.enqueue(video["id"])

    # Query job status by ID
    resp = client.get(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    job_data = resp.get_json()["job"]
    assert job_data["id"] == job["id"]
    assert job_data["status"] == "queued"
    assert job_data["video_title"] == "Job Polling Test"

    # Query job status by video ID
    resp_by_vid = client.get(f"/api/jobs/video/{video['id']}")
    assert resp_by_vid.status_code == 200
    assert resp_by_vid.get_json()["job"]["id"] == job["id"]

    # Query active jobs
    resp_active = client.get("/api/jobs/active")
    assert resp_active.status_code == 200
    active_jobs = resp_active.get_json()["jobs"]
    assert any(j["id"] == job["id"] for j in active_jobs)

    # Nonexistent job returns 404
    resp_missing = client.get("/api/jobs/unknown-id")
    assert resp_missing.status_code == 404

    resp_missing_vid = client.get("/api/jobs/video/unknown-video-id")
    assert resp_missing_vid.status_code == 404

    # Test active jobs fallback path when current_app.transcoding_queue is None
    with patch.object(client.application, "transcoding_queue", None):
        resp_fallback = client.get("/api/jobs/active")
        assert resp_fallback.status_code == 200
        assert resp_fallback.get_json()["count"] >= 1
