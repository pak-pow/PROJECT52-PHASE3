"""Video media inspector extracting metadata and generating poster thumbnails."""

import json
import mimetypes
import shutil
import struct
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class MediaMetadata:
    """Extracted technical metadata for a video file."""

    duration: float
    width: int
    height: int
    bitrate_kbps: int
    video_codec: str
    audio_codec: str
    fps: float
    size_bytes: int
    mime_type: str
    is_valid: bool


class MediaInspector:
    """Inspects video media files and generates poster thumbnails."""

    @classmethod
    def inspect(cls, video_path: Union[str, Path]) -> MediaMetadata:
        """Inspect a video file and extract its technical metadata.

        Attempts ffprobe extraction if available on system PATH; otherwise
        falls back to pure-Python ISO Base Media File Format (MP4) parsing.
        """
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        file_size = path.stat().st_size
        mime, _ = mimetypes.guess_type(path.name)
        mime_type = mime or "video/mp4"

        # Try ffprobe if available
        if shutil.which("ffprobe"):
            ffprobe_meta = cls._inspect_ffprobe(path, file_size, mime_type)
            if ffprobe_meta is not None:
                return ffprobe_meta

        # Pure Python ISO BMFF / MP4 atom parser fallback
        return cls._inspect_pure_python(path, file_size, mime_type)

    @classmethod
    def _inspect_ffprobe(
        cls,
        path: Path,
        file_size: int,
        mime_type: str,
    ) -> Optional[MediaMetadata]:
        """Extract stream metadata using ffprobe subprocess."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            res = subprocess.run(  # nosec B603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode != 0:
                return None

            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            fmt = data.get("format", {})

            duration = float(fmt.get("duration", 0.0))
            bitrate_bps = int(fmt.get("bit_rate", 0))
            bitrate_kbps = bitrate_bps // 1000

            width = 0
            height = 0
            fps = 0.0
            video_codec = "unknown"
            audio_codec = "none"

            for s in streams:
                codec_type = s.get("codec_type")
                if codec_type == "video" and width == 0:
                    width = int(s.get("width", 0))
                    height = int(s.get("height", 0))
                    video_codec = s.get("codec_name", "unknown")
                    # Calculate fps
                    r_frame_rate = s.get("r_frame_rate", "0/1")
                    if "/" in r_frame_rate:
                        num, den = r_frame_rate.split("/")
                        if float(den) > 0:
                            fps = round(float(num) / float(den), 2)
                elif codec_type == "audio" and audio_codec == "none":
                    audio_codec = s.get("codec_name", "unknown")

            if bitrate_kbps == 0 and duration > 0:
                bitrate_kbps = int((file_size * 8) / (duration * 1000))

            return MediaMetadata(
                duration=round(duration, 2),
                width=width,
                height=height,
                bitrate_kbps=bitrate_kbps,
                video_codec=video_codec,
                audio_codec=audio_codec,
                fps=fps,
                size_bytes=file_size,
                mime_type=mime_type,
                is_valid=True,
            )
        except Exception:
            return None

    @classmethod
    def _inspect_pure_python(
        cls,
        path: Path,
        file_size: int,
        mime_type: str,
    ) -> MediaMetadata:
        """Parse ISO Base Media File Format (MP4/MOV) boxes natively in pure Python."""
        try:
            with open(path, "rb") as f:
                boxes = cls._parse_boxes(f, 0, file_size)

                moov = boxes.get("moov")
                if not moov:
                    return cls._create_fallback_metadata(file_size, mime_type, False)

                # Parse mvhd
                f.seek(moov["start"])
                moov_boxes = cls._parse_boxes(f, moov["start"], moov["size"])
                mvhd = moov_boxes.get("mvhd")

                duration = 0.0
                if mvhd:
                    f.seek(mvhd["start"])
                    ver_byte = f.read(1)
                    if ver_byte:
                        ver = struct.unpack(">B", ver_byte)[0]
                        f.seek(mvhd["start"] + 4)  # Skip version and 3-byte flags
                        if ver == 0:
                            # 4 create, 4 mod, 4 timescale, 4 duration
                            _, _, timescale, dur_ticks = struct.unpack(
                                ">IIII", f.read(16)
                            )
                        else:
                            # 8 create, 8 mod, 4 timescale, 8 duration
                            _, _, timescale, dur_ticks = struct.unpack(
                                ">QQIQ", f.read(28)
                            )
                        if timescale > 0:
                            duration = dur_ticks / timescale

                # Parse tracks for dimensions and codecs
                width = 0
                height = 0
                video_codec = "h264"
                audio_codec = "aac"
                fps = 30.0

                traks = moov_boxes.get("trak_list", [])
                for trak_info in traks:
                    f.seek(trak_info["start"])
                    trak_boxes = cls._parse_boxes(
                        f, trak_info["start"], trak_info["size"]
                    )

                    # Extract dimensions from tkhd
                    tkhd = trak_boxes.get("tkhd")
                    if tkhd and width == 0:
                        f.seek(tkhd["start"])
                        tkhd_ver = struct.unpack(">B", f.read(1))[0]
                        offset = 4 + (20 if tkhd_ver == 0 else 32) + 8 + 6 + 2 + 36
                        f.seek(tkhd["start"] + offset)
                        w_raw, h_raw = struct.unpack(">II", f.read(8))
                        w_parsed = w_raw >> 16
                        h_parsed = h_raw >> 16
                        if w_parsed > 0 and h_parsed > 0:
                            width = w_parsed
                            height = h_parsed

                    # Extract codecs from mdia -> minf -> stbl -> stsd
                    mdia = trak_boxes.get("mdia")
                    if mdia:
                        f.seek(mdia["start"])
                        mdia_boxes = cls._parse_boxes(f, mdia["start"], mdia["size"])
                        minf = mdia_boxes.get("minf")
                        if minf:
                            f.seek(minf["start"])
                            minf_boxes = cls._parse_boxes(
                                f, minf["start"], minf["size"]
                            )
                            stbl = minf_boxes.get("stbl")
                            if stbl:
                                f.seek(stbl["start"])
                                stbl_boxes = cls._parse_boxes(
                                    f, stbl["start"], stbl["size"]
                                )
                                stsd = stbl_boxes.get("stsd")
                                if stsd:
                                    f.seek(stsd["start"] + 8)
                                    entry_header = f.read(8)
                                    if len(entry_header) == 8:
                                        _, fmt_code = struct.unpack(
                                            ">I4s", entry_header
                                        )
                                        code_str = fmt_code.decode(
                                            "ascii", errors="ignore"
                                        )
                                        if code_str in (
                                            "avc1",
                                            "hvc1",
                                            "vp09",
                                            "av01",
                                        ):
                                            video_codec = (
                                                "h264"
                                                if code_str == "avc1"
                                                else code_str
                                            )
                                        elif code_str in ("mp4a", "opus"):
                                            audio_codec = code_str

                bitrate_kbps = 0
                if duration > 0:
                    bitrate_kbps = int((file_size * 8) / (duration * 1000))

                return MediaMetadata(
                    duration=round(duration, 2),
                    width=width or 1280,
                    height=height or 720,
                    bitrate_kbps=bitrate_kbps or 2500,
                    video_codec=video_codec,
                    audio_codec=audio_codec,
                    fps=fps,
                    size_bytes=file_size,
                    mime_type=mime_type,
                    is_valid=True,
                )
        except Exception:
            return cls._create_fallback_metadata(file_size, mime_type, False)

    @classmethod
    def _parse_boxes(
        cls,
        f: Any,
        start_pos: int,
        length: int,
    ) -> Dict[str, Any]:
        """Scan sequential ISO BMFF boxes within a byte window."""
        boxes: Dict[str, Any] = {}
        traks: List[Dict[str, Any]] = []
        f.seek(start_pos)
        end_pos = start_pos + length

        while f.tell() + 8 <= end_pos:
            box_header = f.read(8)
            if len(box_header) < 8:
                break
            size, btype_raw = struct.unpack(">I4s", box_header)
            btype = btype_raw.decode("ascii", errors="ignore")

            payload_size = size - 8
            if size == 1:
                size_64 = struct.unpack(">Q", f.read(8))[0]
                payload_size = size_64 - 16
            elif size == 0:
                payload_size = end_pos - f.tell()

            pos = f.tell()
            box_record = {"start": pos, "size": payload_size}
            if btype == "trak":
                traks.append(box_record)
            else:
                boxes[btype] = box_record

            f.seek(pos + payload_size)

        if traks:
            boxes["trak_list"] = traks
            boxes["trak"] = traks[0]
        return boxes

    @classmethod
    def _create_fallback_metadata(
        cls,
        file_size: int,
        mime_type: str,
        is_valid: bool,
    ) -> MediaMetadata:
        """Create a default metadata instance when parsing cannot complete."""
        return MediaMetadata(
            duration=0.0,
            width=0,
            height=0,
            bitrate_kbps=0,
            video_codec="unknown",
            audio_codec="none",
            fps=0.0,
            size_bytes=file_size,
            mime_type=mime_type,
            is_valid=is_valid,
        )

    @classmethod
    def generate_thumbnail(
        cls,
        video_path: Union[str, Path],
        output_path: Union[str, Path],
        title: str = "",
        width: int = 1280,
        height: int = 720,
    ) -> Path:
        """Generate a poster thumbnail image for a video.

        Tries ffmpeg frame capture first if ffmpeg is available; falls back
        to rendering an aesthetic dark poster using Pillow.
        """
        src = Path(video_path)
        dst = Path(output_path)
        dst.parent.mkdir(parents=True, exist_ok=True)

        if shutil.which("ffmpeg") and src.exists():
            if cls._generate_thumbnail_ffmpeg(src, dst):
                return dst

        return cls._generate_thumbnail_pillow(dst, title or src.stem, width, height)

    @classmethod
    def _generate_thumbnail_ffmpeg(cls, src: Path, dst: Path) -> bool:
        """Capture a representative frame using ffmpeg CLI."""
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(src),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(dst),
        ]
        try:
            res = subprocess.run(  # nosec B603
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            return res.returncode == 0 and dst.exists()
        except Exception:
            return False

    @classmethod
    def _generate_thumbnail_pillow(
        cls,
        dst: Path,
        title: str,
        width: int,
        height: int,
    ) -> Path:
        """Render a dark slate video poster thumbnail using Pillow."""
        # Create image with dark gradient background
        img = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Draw gradient bands
        for y in range(height):
            ratio = y / height
            r = int(15 + ratio * (30 - 15))
            g = int(23 + ratio * (41 - 23))
            b = int(42 + ratio * (59 - 42))
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Draw decorative video frame border
        border_inset = 24
        draw.rectangle(
            [
                (border_inset, border_inset),
                (width - border_inset, height - border_inset),
            ],
            outline=(51, 65, 85),
            width=2,
        )

        # Draw central Play button icon
        center_x = width // 2
        center_y = height // 2
        play_radius = 54
        draw.ellipse(
            [
                (center_x - play_radius, center_y - play_radius),
                (center_x + play_radius, center_y + play_radius),
            ],
            fill=(2, 132, 199),
            outline=(56, 189, 248),
            width=3,
        )

        # Draw Play triangle
        tri_offset = 18
        tri_points = [
            (center_x - tri_offset + 6, center_y - tri_offset - 2),
            (center_x - tri_offset + 6, center_y + tri_offset + 2),
            (center_x + tri_offset + 6, center_y),
        ]
        draw.polygon(tri_points, fill=(255, 255, 255))

        # Draw title text and badges
        display_title = title if len(title) <= 50 else title[:47] + "..."
        font = ImageFont.load_default()
        draw.text(
            (48, height - 70),
            display_title,
            fill=(248, 250, 252),
            font=font,
        )
        draw.text(
            (48, 48),
            "PulseStream HD",
            fill=(56, 189, 248),
            font=font,
        )

        img.save(dst, format="JPEG", quality=90)
        return dst
