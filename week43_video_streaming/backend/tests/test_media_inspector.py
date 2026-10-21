"""Unit tests for the MediaInspector service."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.services.media_inspector import MediaInspector, MediaMetadata
from PIL import Image
from tests.helpers import generate_sample_mp4


def test_inspect_missing_file_raises_not_found(temp_dir: Path) -> None:
    """Verify FileNotFoundError when target video does not exist."""
    missing = temp_dir / "nonexistent.mp4"
    with pytest.raises(FileNotFoundError):
        MediaInspector.inspect(missing)


def test_inspect_empty_or_corrupt_file(temp_dir: Path) -> None:
    """Verify fallback metadata when file is empty or corrupted."""
    corrupt = temp_dir / "corrupt.mp4"
    corrupt.write_bytes(b"garbage payload 12345")

    meta = MediaInspector.inspect(corrupt)
    assert isinstance(meta, MediaMetadata)
    assert meta.is_valid is False
    assert meta.duration == 0.0
    assert meta.size_bytes == len(b"garbage payload 12345")


def test_inspect_valid_mp4(temp_dir: Path) -> None:
    """Verify pure-Python inspection of a valid MP4 file."""
    video_file = temp_dir / "test_sample.mp4"
    generate_sample_mp4(
        video_file,
        duration_seconds=12.5,
        width=1920,
        height=1080,
        video_codec="avc1",
    )

    meta = MediaInspector.inspect(video_file)
    assert meta.is_valid is True
    assert meta.duration == 12.5
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.video_codec == "h264"
    assert meta.bitrate_kbps > 0
    assert meta.size_bytes > 0


def test_inspect_ffprobe_success(temp_dir: Path) -> None:
    """Verify ffprobe output parser when ffprobe is detected."""
    dummy_file = temp_dir / "sample.mp4"
    dummy_file.write_bytes(b"0" * 1024)

    ffprobe_payload = {
        "format": {"duration": "45.50", "bit_rate": "2400000"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "r_frame_rate": "30/1",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
            },
        ],
    }

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = json.dumps(ffprobe_payload)

    with patch("shutil.which", return_value="/usr/bin/ffprobe"):
        with patch("subprocess.run", return_value=mock_run):
            meta = MediaInspector.inspect(dummy_file)
            assert meta.is_valid is True
            assert meta.duration == 45.5
            assert meta.width == 1280
            assert meta.height == 720
            assert meta.video_codec == "h264"
            assert meta.audio_codec == "aac"
            assert meta.fps == 30.0
            assert meta.bitrate_kbps == 2400


def test_generate_thumbnail_pillow(temp_dir: Path) -> None:
    """Verify Pillow thumbnail generation when ffmpeg is unavailable."""
    video_file = temp_dir / "clip.mp4"
    video_file.write_bytes(b"dummy video data")
    out_thumb = temp_dir / "thumbnails" / "poster.jpg"

    with patch("shutil.which", return_value=None):
        result = MediaInspector.generate_thumbnail(
            video_file, out_thumb, title="Demo Video", width=640, height=360
        )
        assert result.exists()
        assert result == out_thumb

        # Verify image properties with Pillow
        with Image.open(result) as img:
            assert img.size == (640, 360)
            assert img.format == "JPEG"


def test_generate_thumbnail_ffmpeg(temp_dir: Path) -> None:
    """Verify ffmpeg thumbnail generation when ffmpeg is available."""
    video_file = temp_dir / "clip.mp4"
    video_file.write_bytes(b"dummy")
    out_thumb = temp_dir / "thumb_ffmpeg.jpg"

    def mock_subprocess(*args, **kwargs):
        # Simulate ffmpeg creating the output file
        out_thumb.write_bytes(b"fake jpeg data")
        res = MagicMock()
        res.returncode = 0
        return res

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("subprocess.run", side_effect=mock_subprocess):
            result = MediaInspector.generate_thumbnail(
                video_file, out_thumb, title="FFmpeg Demo"
            )
            assert result.exists()
            assert result == out_thumb
