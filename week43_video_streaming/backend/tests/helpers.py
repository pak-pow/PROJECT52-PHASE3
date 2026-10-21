"""Test helper functions for generating mock media assets."""

import struct
from pathlib import Path


def make_box(box_type: str, payload: bytes) -> bytes:
    """Pack an ISO BMFF 8-byte box header and payload."""
    return struct.pack(">I", len(payload) + 8) + box_type.encode("ascii") + payload


def generate_sample_mp4(
    output_path: Path,
    duration_seconds: float = 10.0,
    width: int = 1280,
    height: int = 720,
    video_codec: str = "avc1",
) -> Path:
    """Generate a structurally valid ISO BMFF MP4 binary for test execution."""
    matrix = struct.pack(
        ">9I",
        0x00010000,
        0,
        0,
        0,
        0x00010000,
        0,
        0,
        0,
        0x40000000,
    )
    ftyp = make_box(
        "ftyp",
        b"isom" + struct.pack(">I", 512) + b"isomiso2mp41",
    )

    timescale = 1000
    duration_ticks = int(duration_seconds * timescale)

    # mvhd
    mvhd_payload = (
        struct.pack(">B3s", 0, b"\x00" * 3)
        + struct.pack(">IIII", 0, 0, timescale, duration_ticks)
        + struct.pack(">Ih10s", 0x00010000, 0x0100, b"\x00" * 10)
        + matrix
        + b"\x00" * 24
        + struct.pack(">I", 2)
    )
    mvhd = make_box("mvhd", mvhd_payload)

    # tkhd
    tkhd_payload = (
        struct.pack(">B3s", 0, b"\x00\x00\x03")
        + struct.pack(">IIII", 0, 0, 1, 0)
        + struct.pack(">I8shhh2s", duration_ticks, b"\x00" * 8, 0, 0, 0, b"\x00" * 2)
        + matrix
        + struct.pack(">II", width << 16, height << 16)
    )
    tkhd = make_box("tkhd", tkhd_payload)

    # mdia
    mdhd = make_box(
        "mdhd",
        struct.pack(">B3s", 0, b"\x00" * 3)
        + struct.pack(">IIII", 0, 0, timescale, duration_ticks)
        + struct.pack(">HH", 0x55C4, 0),
    )
    hdlr = make_box(
        "hdlr",
        struct.pack(">B3s", 0, b"\x00" * 3)
        + struct.pack(">4s4s12s", b"\x00" * 4, b"vide", b"\x00" * 12)
        + b"VideoHandler\x00",
    )
    codec_box = make_box(
        video_codec,
        b"\x00" * 6
        + struct.pack(">H", 1)
        + b"\x00" * 16
        + struct.pack(">HH", width, height)
        + b"\x00" * 50,
    )
    stsd = make_box(
        "stsd",
        struct.pack(">B3s", 0, b"\x00" * 3) + struct.pack(">I", 1) + codec_box,
    )
    stts = make_box(
        "stts",
        struct.pack(">B3s", 0, b"\x00" * 3)
        + struct.pack(">I", 1)
        + struct.pack(">II", 300, 33),
    )
    stsz = make_box(
        "stsz",
        struct.pack(">B3s", 0, b"\x00" * 3)
        + struct.pack(">II", 0, 300)
        + b"\x00\x00\x10\x00" * 300,
    )
    stsc = make_box(
        "stsc",
        struct.pack(">B3s", 0, b"\x00" * 3) + struct.pack(">I", 0),
    )
    stco = make_box(
        "stco",
        struct.pack(">B3s", 0, b"\x00" * 3) + struct.pack(">I", 0),
    )
    stbl = make_box("stbl", stsd + stts + stsz + stsc + stco)
    vmhd = make_box(
        "vmhd",
        struct.pack(">B3s", 0, b"\x00\x00\x01") + struct.pack(">H6s", 0, b"\x00" * 6),
    )
    minf = make_box("minf", vmhd + stbl)
    mdia = make_box("mdia", mdhd + hdlr + minf)
    trak = make_box("trak", tkhd + mdia)
    moov = make_box("moov", mvhd + trak)
    mdat = make_box("mdat", b"\x00" * 2048)

    full_data = ftyp + moov + mdat
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(full_data)
    return output_path
