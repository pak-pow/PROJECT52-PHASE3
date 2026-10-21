"""Unit tests for RFC 7233 RangeStreamingEngine."""

from pathlib import Path

from app.services.streaming_service import RangeStreamingEngine


def test_parse_range_header_cases() -> None:
    """Verify various valid and invalid RFC 7233 range formats."""
    file_size = 1000

    # None and empty
    assert RangeStreamingEngine.parse_range_header(None, file_size) is None
    assert RangeStreamingEngine.parse_range_header("", file_size) is None
    assert RangeStreamingEngine.parse_range_header("invalid", file_size) is None

    # Explicit ranges
    assert RangeStreamingEngine.parse_range_header("bytes=0-499", file_size) == (0, 499)
    assert RangeStreamingEngine.parse_range_header("bytes=500-999", file_size) == (
        500,
        999,
    )

    # Range to EOF
    assert RangeStreamingEngine.parse_range_header("bytes=700-", file_size) == (
        700,
        999,
    )

    # Suffix range
    assert RangeStreamingEngine.parse_range_header("bytes=-200", file_size) == (
        800,
        999,
    )
    assert RangeStreamingEngine.parse_range_header("bytes=-1500", file_size) == (0, 999)

    # Invalid suffix
    assert RangeStreamingEngine.parse_range_header("bytes=-0", file_size) is None

    # Clamping end to file_size - 1
    assert RangeStreamingEngine.parse_range_header("bytes=500-2000", file_size) == (
        500,
        999,
    )

    # Out of bounds and inverted
    assert RangeStreamingEngine.parse_range_header("bytes=1000-", file_size) is None
    assert RangeStreamingEngine.parse_range_header("bytes=1200-1400", file_size) is None
    assert RangeStreamingEngine.parse_range_header("bytes=500-200", file_size) is None

    # Zero file size
    assert RangeStreamingEngine.parse_range_header("bytes=0-10", 0) is None


def test_stream_response_missing_file(temp_dir: Path) -> None:
    """Verify 404 response for nonexistent media files."""
    missing = temp_dir / "missing.mp4"
    resp = RangeStreamingEngine.build_stream_response(missing, "bytes=0-100")
    assert resp.status_code == 404


def test_stream_response_empty_file(temp_dir: Path) -> None:
    """Verify 200 response with 0 length for empty files."""
    empty = temp_dir / "empty.mp4"
    empty.write_bytes(b"")
    resp = RangeStreamingEngine.build_stream_response(empty, None)
    assert resp.status_code == 200
    assert resp.headers["Content-Length"] == "0"


def test_stream_response_full_file(temp_dir: Path) -> None:
    """Verify 200 response with Accept-Ranges when no Range header is supplied."""
    payload = b"abcdefghijklmnopqrstuvwxyz" * 100  # 2600 bytes
    clip = temp_dir / "full_clip.mp4"
    clip.write_bytes(payload)

    resp = RangeStreamingEngine.build_stream_response(clip, None)
    assert resp.status_code == 200
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert resp.headers["Content-Length"] == "2600"
    assert resp.headers["Content-Type"] == "video/mp4"

    body = b"".join(resp.response)
    assert body == payload


def test_stream_response_partial_content_206(temp_dir: Path) -> None:
    """Verify 206 Partial Content when valid byte range is requested."""
    payload = bytes(range(256)) * 4  # 1024 bytes (0..255 repeated 4 times)
    clip = temp_dir / "partial.mp4"
    clip.write_bytes(payload)

    # Request range 100-299 (200 bytes)
    resp = RangeStreamingEngine.build_stream_response(
        clip, "bytes=100-299", chunk_size=64
    )
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == "bytes 100-299/1024"
    assert resp.headers["Content-Length"] == "200"
    assert resp.headers["Accept-Ranges"] == "bytes"

    body = b"".join(resp.response)
    assert len(body) == 200
    assert body == payload[100:300]


def test_stream_response_out_of_bounds_416(temp_dir: Path) -> None:
    """Verify 416 Range Not Satisfiable when range is beyond file boundary."""
    clip = temp_dir / "small.mp4"
    clip.write_bytes(b"0123456789")  # 10 bytes

    resp = RangeStreamingEngine.build_stream_response(clip, "bytes=20-50")
    assert resp.status_code == 416
    assert resp.headers["Content-Range"] == "bytes */10"
    assert b"Requested range not satisfiable" in resp.data
