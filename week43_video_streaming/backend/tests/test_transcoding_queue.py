"""Unit and concurrency tests for TranscodingQueue and TranscodingWorker."""

import time
from pathlib import Path

from app.db.connection import get_db_connection
from app.models.category import CategoryModel
from app.models.video import VideoModel
from app.services.storage_service import StorageService
from app.services.transcoding_service import TranscodingQueue, TranscodingWorker
from tests.helpers import generate_sample_mp4


def test_transcoding_queue_direct_execution(temp_dir: Path, test_db_path: Path) -> None:
    """Verify end-to-end transcoding of a valid video via synchronous process_single."""
    media_dir = temp_dir / "media"
    storage = StorageService(media_dir=media_dir)

    conn = get_db_connection(test_db_path)
    try:
        cat = CategoryModel.create(conn, "Education", "education")
        video = VideoModel.create(
            conn=conn,
            title="Cell Division",
            filename="cell_div.mp4",
            category_id=cat["id"],
        )
    finally:
        conn.close()

    # Generate synthetic MP4 file in raw media directory
    raw_path = storage.get_raw_video_path("cell_div.mp4")
    generate_sample_mp4(raw_path, duration_seconds=8.0, width=1280, height=720)

    # Initialize queue without autostarting worker thread
    t_queue = TranscodingQueue(
        db_path=test_db_path,
        media_dir=media_dir,
        autostart_worker=False,
    )
    assert t_queue.is_worker_running is False

    # Enqueue job
    job = t_queue.enqueue(video["id"])
    assert job["status"] == "queued"
    assert job["progress"] == 0

    # Execute single job synchronously
    success = t_queue.process_single(job["id"])
    assert success is True

    # Verify completed status
    status = t_queue.get_job_status(job["id"])
    assert status["status"] == "completed"
    assert status["progress"] == 100

    # Verify updated video record
    conn = get_db_connection(test_db_path)
    try:
        updated_video = VideoModel.get_by_id(conn, video["id"])
        assert updated_video["status"] == "ready"
        assert updated_video["duration"] > 0
        assert updated_video["poster_path"] is not None

        # Verify renditions were registered
        renditions = VideoModel.get_renditions(conn, video["id"])
        assert len(renditions) >= 1
    finally:
        conn.close()

    # Verify HLS output artifacts on disk
    hls_dir = storage.get_video_hls_dir(video["id"])
    assert (hls_dir / "master.m3u8").exists()

    # Verify thumbnail on disk
    thumb_path = storage.get_thumbnail_path(f"{video['id']}_poster.jpg")
    assert thumb_path.exists()


def test_transcoding_missing_video_fails(temp_dir: Path, test_db_path: Path) -> None:
    """Verify failure handling when job references a nonexistent video ID."""
    media_dir = temp_dir / "media"
    worker = TranscodingWorker(db_path=test_db_path, media_dir=media_dir)

    dummy_job = {
        "id": "nonexistent-job-123",
        "video_id": "nonexistent-vid-456",
    }
    conn = get_db_connection(test_db_path)
    try:
        # Directly call _execute_job
        worker._execute_job(conn, dummy_job)
    finally:
        conn.close()

    # Calling process_single_job for nonexistent job ID returns False
    assert worker.process_single_job("unknown-id") is False


def test_transcoding_missing_raw_file_marks_failed(
    temp_dir: Path, test_db_path: Path
) -> None:
    """Verify job and video transition to failed when raw media is missing on disk."""
    media_dir = temp_dir / "media"
    t_queue = TranscodingQueue(
        db_path=test_db_path,
        media_dir=media_dir,
        autostart_worker=False,
    )

    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(
            conn=conn,
            title="Missing File Video",
            filename="does_not_exist.mp4",
        )
    finally:
        conn.close()

    job = t_queue.enqueue(video["id"])
    t_queue.process_single(job["id"])

    # Check job failed state
    status = t_queue.get_job_status(job["id"])
    assert status["status"] == "failed"
    assert "Raw media asset not found on disk" in status["error_message"]

    # Check video failed state
    conn = get_db_connection(test_db_path)
    try:
        failed_video = VideoModel.get_by_id(conn, video["id"])
        assert failed_video["status"] == "failed"
    finally:
        conn.close()


def test_transcoding_worker_background_thread(
    temp_dir: Path, test_db_path: Path
) -> None:
    """Verify background worker thread processes queued tasks asynchronously."""
    media_dir = temp_dir / "media"
    storage = StorageService(media_dir=media_dir)

    conn = get_db_connection(test_db_path)
    try:
        video = VideoModel.create(
            conn=conn,
            title="Async Process Video",
            filename="async_vid.mp4",
        )
    finally:
        conn.close()

    raw_path = storage.get_raw_video_path("async_vid.mp4")
    generate_sample_mp4(raw_path, duration_seconds=5.0, width=640, height=360)

    t_queue = TranscodingQueue(
        db_path=test_db_path,
        media_dir=media_dir,
        autostart_worker=False,
    )

    job = t_queue.enqueue(video["id"])
    assert t_queue.get_job_status(job["id"])["status"] == "queued"

    # Start worker and wait for background processing
    t_queue.start_worker()
    assert t_queue.is_worker_running is True

    # Calling start again when running should be safe
    t_queue.start_worker()

    # Poll until job completes or timeout (max 6 seconds)
    max_wait = 6.0
    start_time = time.time()
    finished = False
    while time.time() - start_time < max_wait:
        status = t_queue.get_job_status(job["id"])
        if status["status"] == "completed":
            finished = True
            break
        time.sleep(0.1)

    t_queue.stop_worker(timeout=2.0)
    assert finished is True
    assert t_queue.is_worker_running is False


def test_transcoding_queue_helpers(temp_dir: Path, test_db_path: Path) -> None:
    """Verify list_active_jobs and get_job_for_video helper queries."""
    media_dir = temp_dir / "media"
    t_queue = TranscodingQueue(
        db_path=test_db_path,
        media_dir=media_dir,
        autostart_worker=False,
    )

    conn = get_db_connection(test_db_path)
    try:
        vid1 = VideoModel.create(conn, title="Job Helper 1", filename="f1.mp4")
        vid2 = VideoModel.create(conn, title="Job Helper 2", filename="f2.mp4")
    finally:
        conn.close()

    job1 = t_queue.enqueue(vid1["id"])
    job2 = t_queue.enqueue(vid2["id"])

    # List active
    active = t_queue.list_active_jobs()
    active_ids = [j["id"] for j in active]
    assert job1["id"] in active_ids
    assert job2["id"] in active_ids

    # Get by video ID
    found_job = t_queue.get_job_for_video(vid1["id"])
    assert found_job is not None
    assert found_job["id"] == job1["id"]
