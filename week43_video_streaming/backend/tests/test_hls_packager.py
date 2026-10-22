"""Unit tests for the HLSPackager service."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.services.hls_packager import (
    HLSPackager,
    HLSPackageResult,
    RenditionResult,
)
from app.transcoding.profiles import STANDARD_PROFILES
from tests.helpers import generate_sample_mp4


def test_generate_master_manifest_syntax() -> None:
    """Verify Master Manifest structure, tags, and codecs."""
    profiles = [STANDARD_PROFILES["1080p"], STANDARD_PROFILES["720p"]]
    manifest = HLSPackager.generate_master_manifest(profiles)

    assert manifest.startswith("#EXTM3U")
    assert "#EXT-X-VERSION:3" in manifest
    assert "stream_1080p.m3u8" in manifest
    assert "stream_720p.m3u8" in manifest

    # Check bandwidth and resolution tags
    assert "BANDWIDTH=4500000" in manifest
    assert "RESOLUTION=1920x1080" in manifest
    assert "BANDWIDTH=2500000" in manifest
    assert "RESOLUTION=1280x720" in manifest

    # With prefix
    prefixed = HLSPackager.generate_master_manifest(
        profiles, playlist_prefix="hls/vid-1"
    )
    assert "hls/vid-1/stream_1080p.m3u8" in prefixed


def test_generate_variant_playlist_syntax() -> None:
    """Verify Variant Playlist formatting, target duration, and segment entries."""
    durations = [4.0, 4.0, 2.5]
    filenames = ["seg_000.ts", "seg_001.ts", "seg_002.ts"]

    playlist = HLSPackager.generate_variant_playlist(durations, filenames)

    assert playlist.startswith("#EXTM3U")
    assert "#EXT-X-VERSION:3" in playlist
    assert "#EXT-X-TARGETDURATION:4" in playlist
    assert "#EXT-X-MEDIA-SEQUENCE:0" in playlist
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in playlist

    assert "#EXTINF:4.000000,\nseg_000.ts" in playlist
    assert "#EXTINF:4.000000,\nseg_001.ts" in playlist
    assert "#EXTINF:2.500000,\nseg_002.ts" in playlist
    assert playlist.strip().endswith("#EXT-X-ENDLIST")


def test_generate_variant_mismatched_counts_raises_error() -> None:
    """Verify ValueError when segment durations and filenames lists differ."""
    with pytest.raises(ValueError):
        HLSPackager.generate_variant_playlist([4.0], ["seg1.ts", "seg2.ts"])


def test_package_video_missing_file_raises_not_found(temp_dir: Path) -> None:
    """Verify FileNotFoundError when source media path does not exist."""
    missing = temp_dir / "nonexistent.mp4"
    out_dir = temp_dir / "hls"
    with pytest.raises(FileNotFoundError):
        HLSPackager.package_video(missing, out_dir, video_id="vid-1")


def test_package_video_python_fallback(temp_dir: Path) -> None:
    """Verify end-to-end HLS packaging using the pure-Python fallback pipeline."""
    sample_mp4 = temp_dir / "sample.mp4"
    generate_sample_mp4(sample_mp4, duration_seconds=9.0, width=1280, height=720)

    out_dir = temp_dir / "hls_output"
    profiles = [STANDARD_PROFILES["720p"], STANDARD_PROFILES["480p"]]

    # Ensure ffmpeg is treated as unavailable to exercise fallback
    with patch("shutil.which", return_value=None):
        result = HLSPackager.package_video(
            sample_mp4,
            out_dir,
            video_id="test-vid-123",
            profiles=profiles,
            segment_duration=4.0,
        )

    assert isinstance(result, HLSPackageResult)
    assert result.engine_used == "python_fallback"
    assert result.video_id == "test-vid-123"
    assert result.master_playlist_path.exists()
    assert len(result.renditions) == 2

    # Verify master manifest on disk
    master_text = result.master_playlist_path.read_text(encoding="utf-8")
    assert "stream_720p.m3u8" in master_text
    assert "stream_480p.m3u8" in master_text

    # Verify renditions and segment chunks
    for rend in result.renditions:
        assert isinstance(rend, RenditionResult)
        assert rend.segment_count == 3  # 9 seconds / 4s = ceil(2.25) = 3 segments
        variant_file = out_dir / f"stream_{rend.name}.m3u8"
        assert variant_file.exists()

        # Check TS chunks framing (multiples of 188 bytes, starting with 0x47)
        for i in range(rend.segment_count):
            chunk = out_dir / f"{rend.name}_seg_{i:03d}.ts"
            assert chunk.exists()
            data = chunk.read_bytes()
            assert len(data) > 0
            assert len(data) % 188 == 0
            assert data[0] == 0x47


def test_package_video_ffmpeg_success(temp_dir: Path) -> None:
    """Verify package_video when host FFmpeg execution succeeds."""
    sample_mp4 = temp_dir / "sample.mp4"
    sample_mp4.write_bytes(b"dummy")

    out_dir = temp_dir / "hls_ffmpeg"
    profiles = [STANDARD_PROFILES["720p"]]

    def mock_subprocess(*args, **kwargs):
        # Simulate ffmpeg generating the variant playlist and segments
        (out_dir / "stream_720p.m3u8").write_text("#EXTM3U\n", encoding="utf-8")
        (out_dir / "720p_seg_000.ts").write_bytes(b"\x47" * 188)
        res = MagicMock()
        res.returncode = 0
        return res

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("subprocess.run", side_effect=mock_subprocess):
            result = HLSPackager.package_video(
                sample_mp4,
                out_dir,
                video_id="ffmpeg-vid",
                profiles=profiles,
            )

            assert result.engine_used == "ffmpeg"
            assert result.total_segments == 1
            assert (out_dir / "master.m3u8").exists()


def test_package_video_ffmpeg_failure_falls_back(temp_dir: Path) -> None:
    """Verify graceful fallback to pure Python when FFmpeg exits with error."""
    sample_mp4 = temp_dir / "sample.mp4"
    generate_sample_mp4(sample_mp4, duration_seconds=6.0, width=1280, height=720)

    out_dir = temp_dir / "hls_fallback_on_err"
    profiles = [STANDARD_PROFILES["360p"]]

    mock_fail = MagicMock()
    mock_fail.returncode = 1  # FFmpeg error

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch("subprocess.run", return_value=mock_fail):
            result = HLSPackager.package_video(
                sample_mp4,
                out_dir,
                video_id="fallback-vid",
                profiles=profiles,
            )

            assert result.engine_used == "python_fallback"
            assert (out_dir / "master.m3u8").exists()
            assert (out_dir / "stream_360p.m3u8").exists()


def test_ts_packet_builder_truncation() -> None:
    """Verify that oversized payloads are truncated safely to 184 bytes."""
    oversized = b"A" * 300
    pkt = HLSPackager._build_ts_packet(pid=0x0100, payload=oversized, cc=2)
    assert len(pkt) == 188
    assert pkt[0] == 0x47
