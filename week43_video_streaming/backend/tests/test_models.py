"""Unit tests for category, video, and transcoding job database models."""

import sqlite3

from app.models.category import CategoryModel
from app.models.job import TranscodingJobModel
from app.models.video import VideoModel


def test_category_model_lifecycle(test_conn: sqlite3.Connection) -> None:
    """Verify category creation, retrieval by id/slug, listing, and deletion."""
    cat = CategoryModel.create(
        conn=test_conn,
        name="Tech",
        slug="tech",
        description="Technology content",
    )
    assert cat["id"] is not None
    assert cat["name"] == "Tech"
    assert cat["slug"] == "tech"
    assert cat["description"] == "Technology content"

    # Get by ID
    fetched_by_id = CategoryModel.get_by_id(test_conn, cat["id"])
    assert fetched_by_id is not None
    assert fetched_by_id["name"] == "Tech"

    # Get by slug
    fetched_by_slug = CategoryModel.get_by_slug(test_conn, "tech")
    assert fetched_by_slug is not None
    assert fetched_by_slug["id"] == cat["id"]

    # Nonexistent slug
    assert CategoryModel.get_by_slug(test_conn, "nonexistent") is None

    # List all
    all_cats = CategoryModel.list_all(test_conn)
    assert len(all_cats) == 1
    assert all_cats[0]["name"] == "Tech"

    # Delete
    deleted = CategoryModel.delete(test_conn, cat["id"])
    assert deleted is True
    assert CategoryModel.get_by_id(test_conn, cat["id"]) is None


def test_video_model_lifecycle(test_conn: sqlite3.Connection) -> None:
    """Verify video creation, updates, views increment, search, and renditions."""
    cat = CategoryModel.create(test_conn, "Entertainment", "entertainment")

    video = VideoModel.create(
        conn=test_conn,
        title="Sample Video",
        filename="sample.mp4",
        description="A test video sample",
        category_id=cat["id"],
        duration=120.5,
        size_bytes=5000000,
        mime_type="video/mp4",
    )

    assert video["id"] is not None
    assert video["title"] == "Sample Video"
    assert video["category_name"] == "Entertainment"
    assert video["status"] == "pending"
    assert video["views_count"] == 0

    # Retrieve by ID
    fetched = VideoModel.get_by_id(test_conn, video["id"])
    assert fetched is not None
    assert fetched["id"] == video["id"]

    # Increment views
    new_views = VideoModel.increment_views(test_conn, video["id"])
    assert new_views == 1
    new_views = VideoModel.increment_views(test_conn, video["id"])
    assert new_views == 2

    # Update status and duration
    updated = VideoModel.update_status(
        test_conn,
        video_id=video["id"],
        status="ready",
        duration=125.0,
        poster_path="thumb.jpg",
    )
    assert updated is True

    refetched = VideoModel.get_by_id(test_conn, video["id"])
    assert refetched["status"] == "ready"
    assert refetched["duration"] == 125.0
    assert refetched["poster_path"] == "thumb.jpg"

    # Add Renditions
    rend_720p = VideoModel.add_rendition(
        conn=test_conn,
        video_id=video["id"],
        resolution="720p",
        width=1280,
        height=720,
        bitrate_kbps=2500,
        playlist_path="hls/vid/stream_720p.m3u8",
        segment_count=30,
    )
    rend_1080p = VideoModel.add_rendition(
        conn=test_conn,
        video_id=video["id"],
        resolution="1080p",
        width=1920,
        height=1080,
        bitrate_kbps=4500,
        playlist_path="hls/vid/stream_1080p.m3u8",
        segment_count=30,
    )

    assert rend_720p["id"] is not None
    assert rend_1080p["id"] is not None

    renditions = VideoModel.get_renditions(test_conn, video["id"])
    assert len(renditions) == 2
    # Ordered by height descending
    assert renditions[0]["resolution"] == "1080p"
    assert renditions[1]["resolution"] == "720p"

    # List with search, category filter, and status filter
    matching = VideoModel.list_all(
        test_conn, category_id=cat["id"], status="ready", search="Sample"
    )
    assert len(matching) == 1
    nomatch = VideoModel.list_all(test_conn, search="Nonexistent")
    assert len(nomatch) == 0

    # Delete video cascades renditions
    deleted = VideoModel.delete(test_conn, video["id"])
    assert deleted is True
    assert VideoModel.get_by_id(test_conn, video["id"]) is None
    assert len(VideoModel.get_renditions(test_conn, video["id"])) == 0


def test_transcoding_job_lifecycle(test_conn: sqlite3.Connection) -> None:
    """Verify transcoding job queue transitions and progress tracking."""
    video = VideoModel.create(
        conn=test_conn,
        title="Transcoding Test",
        filename="test.mp4",
    )

    job = TranscodingJobModel.create(conn=test_conn, video_id=video["id"])
    assert job["id"] is not None
    assert job["status"] == "queued"
    assert job["progress"] == 0

    # Retrieve by video_id
    job_by_vid = TranscodingJobModel.get_by_video_id(test_conn, video["id"])
    assert job_by_vid is not None
    assert job_by_vid["id"] == job["id"]

    # List by status
    queued_jobs = TranscodingJobModel.list_by_status(test_conn, "queued")
    assert len(queued_jobs) >= 1

    # Update progress
    updated = TranscodingJobModel.update_progress(
        test_conn, job_id=job["id"], progress=45, current_stage="encoding_720p"
    )
    assert updated is True

    fetched = TranscodingJobModel.get_by_id(test_conn, job["id"])
    assert fetched["status"] == "processing"
    assert fetched["progress"] == 45
    assert fetched["current_stage"] == "encoding_720p"
    assert fetched["video_title"] == "Transcoding Test"

    # List all jobs
    all_jobs = TranscodingJobModel.list_all(test_conn)
    assert len(all_jobs) >= 1

    # Mark completed
    completed = TranscodingJobModel.mark_completed(test_conn, job["id"])
    assert completed is True

    final_job = TranscodingJobModel.get_by_id(test_conn, job["id"])
    assert final_job["status"] == "completed"
    assert final_job["progress"] == 100
    assert final_job["completed_at"] is not None

    # Test failure marking on another job
    job2 = TranscodingJobModel.create(conn=test_conn, video_id=video["id"])
    failed = TranscodingJobModel.mark_failed(
        test_conn, job_id=job2["id"], error_message="Codec unsupported"
    )
    assert failed is True

    failed_job = TranscodingJobModel.get_by_id(test_conn, job2["id"])
    assert failed_job["status"] == "failed"
    assert failed_job["error_message"] == "Codec unsupported"
