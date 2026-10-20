"""Unit tests for StorageService directory management and file lifecycle."""

from pathlib import Path

from app.services.storage_service import StorageService


def test_storage_service_initialization(temp_dir: Path) -> None:
    """Verify that storage directories are automatically created on init."""
    media_dir = temp_dir / "custom_media"
    storage = StorageService(media_dir=media_dir)

    assert storage.media_dir.exists()
    assert storage.raw_dir.exists()
    assert storage.hls_dir.exists()
    assert storage.thumbnails_dir.exists()


def test_storage_path_generation(temp_dir: Path) -> None:
    """Verify safe path generation for raw, hls, and thumbnail media."""
    storage = StorageService(media_dir=temp_dir / "media")

    raw_path = storage.get_raw_video_path("video123.mp4")
    assert raw_path.name == "video123.mp4"
    assert raw_path.parent == storage.raw_dir

    hls_dir = storage.get_video_hls_dir("vid-abc-456")
    assert hls_dir.name == "vid-abc-456"
    assert hls_dir.exists()

    thumb_path = storage.get_thumbnail_path("thumb_456.jpg")
    assert thumb_path.name == "thumb_456.jpg"
    assert thumb_path.parent == storage.thumbnails_dir


def test_storage_stats_and_cleanup(temp_dir: Path) -> None:
    """Verify storage stats computation and safe file deletion."""
    storage = StorageService(media_dir=temp_dir / "media")

    # Write dummy files
    raw_file = storage.get_raw_video_path("test_clip.mp4")
    raw_file.write_bytes(b"0" * 1024)

    hls_dir = storage.get_video_hls_dir("test-vid-id")
    chunk_file = hls_dir / "seg_000.ts"
    chunk_file.write_bytes(b"1" * 2048)

    thumb_file = storage.get_thumbnail_path("test_poster.jpg")
    thumb_file.write_bytes(b"2" * 512)

    stats = storage.get_storage_stats()
    assert stats["raw_count"] == 1
    assert stats["raw_bytes"] == 1024
    assert stats["hls_videos_count"] == 1
    assert stats["hls_bytes"] == 2048
    assert stats["thumbnails_count"] == 1
    assert stats["thumbnails_bytes"] == 512
    assert stats["total_bytes"] == 1024 + 2048 + 512

    # Delete video files
    storage.delete_video_files(
        video_id="test-vid-id",
        raw_filename="test_clip.mp4",
        poster_filename="test_poster.jpg",
    )

    assert not raw_file.exists()
    assert not hls_dir.exists()
    assert not thumb_file.exists()

    cleared_stats = storage.get_storage_stats()
    assert cleared_stats["raw_count"] == 0
    assert cleared_stats["total_bytes"] == 0
