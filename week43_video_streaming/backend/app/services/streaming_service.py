"""RFC 7233 compliant byte-range streaming engine for video media."""

import mimetypes
import re
from pathlib import Path
from typing import Generator, Optional, Tuple, Union

from flask import Response

# Regex to parse RFC 7233 Range headers (e.g., bytes=0-1048575, bytes=1000-, bytes=-500)
RANGE_HEADER_REGEX = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeStreamingEngine:
    """Engine for serving partial video content with byte-range slicing."""

    DEFAULT_CHUNK_SIZE: int = 64 * 1024  # 64 KB buffer for streaming chunks

    @classmethod
    def parse_range_header(
        cls,
        range_header: Optional[str],
        file_size: int,
    ) -> Optional[Tuple[int, int]]:
        """Parse and validate RFC 7233 Range header against the total file size.

        Returns a tuple of (start_byte, end_byte) if valid, or None if the header
        is missing, malformed, or specifies an invalid range.
        """
        if not range_header or file_size <= 0:
            return None

        # Take the first range if multiple comma-separated ranges are provided
        header_val = range_header.split(",")[0].strip()
        match = RANGE_HEADER_REGEX.match(header_val)
        if not match:
            return None

        start_str, end_str = match.groups()

        if start_str and end_str:
            # Case 1: Explicit range (bytes=0-1000)
            start = int(start_str)
            end = int(end_str)
        elif start_str and not end_str:
            # Case 2: Range to EOF (bytes=1000-)
            start = int(start_str)
            end = file_size - 1
        elif not start_str and end_str:
            # Case 3: Suffix range (bytes=-500)
            suffix_len = int(end_str)
            if suffix_len <= 0:
                return None
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            return None

        if start < 0 or start >= file_size or start > end:
            return None

        # Clamp end to final byte of file
        end = min(end, file_size - 1)
        return start, end

    @classmethod
    def stream_file_range(
        cls,
        file_path: Path,
        start_byte: int,
        length: int,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Generator[bytes, None, None]:
        """Yield discrete byte chunks without buffering entire file in memory."""
        bytes_remaining = length
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            while bytes_remaining > 0:
                read_amount = min(chunk_size, bytes_remaining)
                chunk = f.read(read_amount)
                if not chunk:
                    break
                bytes_remaining -= len(chunk)
                yield chunk

    @classmethod
    def build_stream_response(
        cls,
        file_path: Union[str, Path],
        range_header: Optional[str],
        mime_type: Optional[str] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Response:
        """Construct Flask Response with appropriate 200, 206, or 416 HTTP status."""
        path = Path(file_path)
        if not path.is_file():
            return Response("Video file not found", status=404, mimetype="text/plain")

        file_size = path.stat().st_size
        resolved_mime = mime_type
        if not resolved_mime:
            guessed, _ = mimetypes.guess_type(path.name)
            resolved_mime = guessed or "video/mp4"

        # Handle empty file edge case
        if file_size == 0:
            headers = {
                "Content-Length": "0",
                "Content-Type": resolved_mime,
                "Accept-Ranges": "bytes",
            }
            return Response(b"", status=200, headers=headers)

        # Parse range header if present
        if range_header:
            parsed_range = cls.parse_range_header(range_header, file_size)
            if parsed_range is None:
                # Range header was requested but is out-of-bounds or invalid
                headers = {
                    "Content-Range": f"bytes */{file_size}",
                    "Accept-Ranges": "bytes",
                }
                return Response(
                    "Requested range not satisfiable",
                    status=416,
                    headers=headers,
                    mimetype="text/plain",
                )

            start, end = parsed_range
            content_length = end - start + 1
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": resolved_mime,
                "Cache-Control": "public, max-age=3600",
            }

            generator = cls.stream_file_range(
                path, start, content_length, chunk_size=chunk_size
            )
            return Response(
                generator,
                status=206,
                headers=headers,
                direct_passthrough=True,
            )

        # No Range header: Serve full file with 200 OK
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": resolved_mime,
            "Cache-Control": "public, max-age=3600",
        }
        generator = cls.stream_file_range(path, 0, file_size, chunk_size=chunk_size)
        return Response(
            generator,
            status=200,
            headers=headers,
            direct_passthrough=True,
        )
