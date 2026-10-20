"""Transcoding profiles and quality definitions."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class RenditionProfile:
    """Adaptive Bitrate (ABR) rendition target profile."""

    name: str
    width: int
    height: int
    bitrate_kbps: int
    fps: int = 30
    audio_bitrate_kbps: int = 128


STANDARD_PROFILES: Dict[str, RenditionProfile] = {
    "1080p": RenditionProfile(
        name="1080p",
        width=1920,
        height=1080,
        bitrate_kbps=4500,
        fps=60,
        audio_bitrate_kbps=192,
    ),
    "720p": RenditionProfile(
        name="720p",
        width=1280,
        height=720,
        bitrate_kbps=2500,
        fps=30,
        audio_bitrate_kbps=128,
    ),
    "480p": RenditionProfile(
        name="480p",
        width=854,
        height=480,
        bitrate_kbps=1000,
        fps=30,
        audio_bitrate_kbps=96,
    ),
    "360p": RenditionProfile(
        name="360p",
        width=640,
        height=360,
        bitrate_kbps=600,
        fps=30,
        audio_bitrate_kbps=64,
    ),
}


def get_profiles_for_source(height: int) -> List[RenditionProfile]:
    """Return profiles that do not upscale above the source vertical resolution."""
    profiles: List[RenditionProfile] = []
    for profile in STANDARD_PROFILES.values():
        if profile.height <= height:
            profiles.append(profile)
    # Always include at least the lowest tier if source is tiny
    if not profiles:
        profiles.append(STANDARD_PROFILES["360p"])
    return sorted(profiles, key=lambda p: p.height, reverse=True)
