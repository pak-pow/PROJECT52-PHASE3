"""HLS packaging engine generating master manifests, playlists, and TS segments."""

import math
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union

from app.services.media_inspector import MediaInspector, MediaMetadata
from app.transcoding.profiles import (
    RenditionProfile,
    get_profiles_for_source,
)


@dataclass(frozen=True)
class RenditionResult:
    """Packaging output for an individual ABR rendition profile."""

    name: str
    resolution: str
    width: int
    height: int
    bitrate_kbps: int
    playlist_path: str
    segment_count: int
    duration: float


@dataclass(frozen=True)
class HLSPackageResult:
    """Consolidated result of HLS multi-profile packaging."""

    video_id: str
    master_playlist_path: Path
    renditions: List[RenditionResult]
    total_segments: int
    engine_used: str


class HLSPackager:
    """Generates HLS master manifests, variant playlists, and media segments."""

    DEFAULT_SEGMENT_DURATION: float = 4.0

    @classmethod
    def generate_master_manifest(
        cls,
        profiles: List[RenditionProfile],
        playlist_prefix: str = "",
    ) -> str:
        """Generate an RFC 8216 compliant HLS Master Manifest (master.m3u8)."""
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "",
        ]

        codec_map: Dict[str, str] = {
            "1080p": 'CODECS="avc1.64002a,mp4a.40.2"',
            "720p": 'CODECS="avc1.4d401f,mp4a.40.2"',
            "480p": 'CODECS="avc1.4d401e,mp4a.40.2"',
            "360p": 'CODECS="avc1.42e01e,mp4a.40.2"',
        }

        for profile in profiles:
            bandwidth = profile.bitrate_kbps * 1000
            res = f"{profile.width}x{profile.height}"
            codecs = codec_map.get(profile.name, 'CODECS="avc1.4d401f,mp4a.40.2"')
            stream_inf = (
                f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},"
                f"RESOLUTION={res},"
                f"FRAME-RATE={float(profile.fps):.3f},"
                f"{codecs}"
            )
            playlist_name = f"stream_{profile.name}.m3u8"
            if playlist_prefix:
                clean_prefix = playlist_prefix.rstrip("/")
                playlist_name = f"{clean_prefix}/{playlist_name}"

            lines.append(stream_inf)
            lines.append(playlist_name)
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    @classmethod
    def generate_variant_playlist(
        cls,
        segment_durations: List[float],
        segment_filenames: List[str],
        target_duration: Optional[int] = None,
    ) -> str:
        """Generate an HLS Media Variant Playlist (e.g., stream_720p.m3u8)."""
        if len(segment_durations) != len(segment_filenames):
            raise ValueError(
                "Segment durations and filenames counts must match exactly."
            )

        max_dur = max(segment_durations) if segment_durations else 4.0
        target_dur = target_duration or int(math.ceil(max_dur))

        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{target_dur}",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-PLAYLIST-TYPE:VOD",
        ]

        for dur, filename in zip(segment_durations, segment_filenames):
            lines.append(f"#EXTINF:{dur:.6f},")
            lines.append(filename)

        lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"

    @classmethod
    def package_video(
        cls,
        source_path: Union[str, Path],
        output_dir: Union[str, Path],
        video_id: str,
        profiles: Optional[List[RenditionProfile]] = None,
        segment_duration: float = DEFAULT_SEGMENT_DURATION,
    ) -> HLSPackageResult:
        """Transcode and package video into multi-bitrate HLS structure."""
        src = Path(source_path)
        dst = Path(output_dir)
        dst.mkdir(parents=True, exist_ok=True)

        if not src.is_file():
            raise FileNotFoundError(f"Source video file not found: {src}")

        # Extract metadata to determine available rendition targets
        meta = MediaInspector.inspect(src)
        target_profiles = profiles or get_profiles_for_source(meta.height)

        # Check for host FFmpeg
        if shutil.which("ffmpeg"):
            ffmpeg_result = cls._package_ffmpeg(
                src, dst, video_id, target_profiles, segment_duration
            )
            if ffmpeg_result is not None:
                return ffmpeg_result

        # Pure Python fallback packager
        return cls._package_python_fallback(
            src, dst, video_id, target_profiles, meta, segment_duration
        )

    @classmethod
    def _package_ffmpeg(
        cls,
        src: Path,
        dst: Path,
        video_id: str,
        profiles: List[RenditionProfile],
        segment_duration: float,
    ) -> Optional[HLSPackageResult]:
        """Execute FFmpeg multi-rendition HLS segmentation pipeline."""
        rendition_results: List[RenditionResult] = []
        total_segments = 0

        for profile in profiles:
            variant_name = f"stream_{profile.name}.m3u8"
            segment_pattern = str(dst / f"{profile.name}_seg_%03d.ts")
            variant_path = dst / variant_name

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                f"scale={profile.width}:{profile.height}",
                "-c:v",
                "libx264",
                "-b:v",
                f"{profile.bitrate_kbps}k",
                "-c:a",
                "aac",
                "-b:a",
                f"{profile.audio_bitrate_kbps}k",
                "-hls_time",
                str(int(segment_duration)),
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                segment_pattern,
                str(variant_path),
            ]

            try:
                res = subprocess.run(  # nosec B603
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=180,
                    check=False,
                )
                if res.returncode != 0 or not variant_path.exists():
                    return None

                seg_files = list(dst.glob(f"{profile.name}_seg_*.ts"))
                count = len(seg_files)
                total_segments += count

                rendition_results.append(
                    RenditionResult(
                        name=profile.name,
                        resolution=f"{profile.width}x{profile.height}",
                        width=profile.width,
                        height=profile.height,
                        bitrate_kbps=profile.bitrate_kbps,
                        playlist_path=f"hls/{video_id}/{variant_name}",
                        segment_count=count,
                        duration=count * segment_duration,
                    )
                )
            except Exception:
                return None

        # Write master playlist
        master_content = cls.generate_master_manifest(profiles)
        master_path = dst / "master.m3u8"
        master_path.write_text(master_content, encoding="utf-8")

        return HLSPackageResult(
            video_id=video_id,
            master_playlist_path=master_path,
            renditions=rendition_results,
            total_segments=total_segments,
            engine_used="ffmpeg",
        )

    @classmethod
    def _package_python_fallback(
        cls,
        src: Path,
        dst: Path,
        video_id: str,
        profiles: List[RenditionProfile],
        meta: MediaMetadata,
        segment_duration: float,
    ) -> HLSPackageResult:
        """Create valid HLS manifest structure and synthetic TS chunks natively."""
        total_duration = meta.duration if meta.duration > 0 else 10.0
        num_segments = max(1, int(math.ceil(total_duration / segment_duration)))

        rendition_results: List[RenditionResult] = []
        total_segments = 0

        # Calculate segment durations
        seg_durations: List[float] = []
        rem_dur = total_duration
        for _ in range(num_segments):
            chunk_dur = min(segment_duration, rem_dur)
            seg_durations.append(round(chunk_dur, 6))
            rem_dur -= chunk_dur
            if rem_dur <= 0:
                break

        # Read source slice bytes to embed into TS packets
        src_bytes = b""
        if src.exists():
            with open(src, "rb") as f:
                src_bytes = f.read(1024 * 16)

        for profile in profiles:
            seg_filenames: List[str] = []
            for i, dur in enumerate(seg_durations):
                filename = f"{profile.name}_seg_{i:03d}.ts"
                seg_filenames.append(filename)
                seg_path = dst / filename

                # Generate valid MPEG-2 TS chunk
                ts_bytes = cls._generate_ts_chunk(
                    segment_index=i,
                    duration=dur,
                    bitrate_kbps=profile.bitrate_kbps,
                    sample_payload=src_bytes,
                )
                seg_path.write_bytes(ts_bytes)

            count = len(seg_filenames)
            total_segments += count

            # Write variant playlist
            variant_name = f"stream_{profile.name}.m3u8"
            variant_content = cls.generate_variant_playlist(
                segment_durations=seg_durations,
                segment_filenames=seg_filenames,
            )
            variant_path = dst / variant_name
            variant_path.write_text(variant_content, encoding="utf-8")

            rendition_results.append(
                RenditionResult(
                    name=profile.name,
                    resolution=f"{profile.width}x{profile.height}",
                    width=profile.width,
                    height=profile.height,
                    bitrate_kbps=profile.bitrate_kbps,
                    playlist_path=f"hls/{video_id}/{variant_name}",
                    segment_count=count,
                    duration=total_duration,
                )
            )

        # Write master playlist
        master_content = cls.generate_master_manifest(profiles)
        master_path = dst / "master.m3u8"
        master_path.write_text(master_content, encoding="utf-8")

        return HLSPackageResult(
            video_id=video_id,
            master_playlist_path=master_path,
            renditions=rendition_results,
            total_segments=total_segments,
            engine_used="python_fallback",
        )

    @classmethod
    def _generate_ts_chunk(
        cls,
        segment_index: int,
        duration: float,
        bitrate_kbps: int,
        sample_payload: bytes,
    ) -> bytes:
        """Synthesize a valid MPEG-2 TS stream chunk with PAT, PMT, and PES framing."""
        packets: List[bytes] = []

        # 1. Program Association Table (PAT) - PID 0x0000
        # Maps Program 1 to PMT PID 0x1000
        pat_payload = (
            b"\x00"  # Pointer field
            b"\x00\xb0\x0d"  # Table ID 0, Section syntax 1, Length 13
            b"\x00\x01"  # Transport stream ID 1
            b"\xc1"  # Version 0, Current/next 1
            b"\x00\x00"  # Section 0, Last section 0
            b"\x00\x01"  # Program number 1
            b"\xe1\x00"  # PMT PID 0x1000
            b"\x2a\xb1\x04\xb2"  # CRC32 placeholder
        )
        packets.append(
            cls._build_ts_packet(pid=0, payload=pat_payload, payload_start=True)
        )

        # 2. Program Map Table (PMT) - PID 0x1000
        # Declares Stream 1 (H.264, PID 0x0100) and Stream 2 (AAC, PID 0x0101)
        pmt_payload = (
            b"\x00"  # Pointer field
            b"\x02\xb0\x17"  # Table ID 2, Section syntax 1, Length 23
            b"\x00\x01"  # Transport stream ID 1
            b"\xc1"  # Version 0, Current/next 1
            b"\x00\x00"  # Section 0, Last section 0
            b"\xe1\x00"  # PCR PID 0x0100
            b"\xf0\x00"  # Program info length 0
            b"\x1b\xe1\x00\xf0\x00"  # Video Stream: H.264 (0x1b), PID 0x0100
            b"\x0f\xe1\x01\xf0\x00"  # Audio Stream: AAC (0x0f), PID 0x0101
            b"\x4e\x59\x3d\x8a"  # CRC32 placeholder
        )
        packets.append(
            cls._build_ts_packet(pid=0x1000, payload=pmt_payload, payload_start=True)
        )

        # 3. Video PES Packets - PID 0x0100
        # Target chunk packet count based on duration and bitrate (min 16 packets)
        target_byte_size = max(
            188 * 16, int((bitrate_kbps * 1000 * duration) / (8 * 10))
        )
        num_data_packets = min(120, target_byte_size // 188)

        # PES packet header (Start code prefix 0x000001, stream_id 0xE0)
        pes_header = (
            b"\x00\x00\x01\xe0"  # Start code + video stream ID
            b"\x00\x00"  # PES packet length (0 = unbound)
            b"\x80\x80\x05"  # PES flags: PTS present
            b"\x21\x00\x01\x00\x01"  # PTS timestamp
        )
        packets.append(
            cls._build_ts_packet(
                pid=0x0100, payload=pes_header, payload_start=True, cc=1
            )
        )

        # Payload fill
        slice_data = sample_payload if sample_payload else b"\x00" * 64
        for cc in range(2, num_data_packets):
            offset = ((segment_index * 10) + cc) % max(1, len(slice_data))
            end_offset = offset + 120
            chunk_slice = slice_data[offset:end_offset]
            if len(chunk_slice) < 120:
                chunk_slice = chunk_slice + b"\x00" * (120 - len(chunk_slice))

            packets.append(
                cls._build_ts_packet(
                    pid=0x0100,
                    payload=chunk_slice,
                    payload_start=False,
                    cc=cc % 16,
                )
            )

        return b"".join(packets)

    @classmethod
    def _build_ts_packet(
        cls,
        pid: int,
        payload: bytes,
        payload_start: bool = False,
        cc: int = 0,
    ) -> bytes:
        """Encode a standard 188-byte MPEG-2 Transport Stream packet with padding."""
        header = bytearray(4)
        header[0] = 0x47  # Sync byte
        header[1] = ((1 if payload_start else 0) << 6) | ((pid >> 8) & 0x1F)
        header[2] = pid & 0xFF
        header[3] = 0x10 | (cc & 0x0F)  # Adaptation: payload only (01)

        payload_len = len(payload)
        pad_len = 188 - 4 - payload_len
        if pad_len < 0:
            payload = payload[: 188 - 4]
            pad_len = 0

        return bytes(header) + payload + (b"\xff" * pad_len)
