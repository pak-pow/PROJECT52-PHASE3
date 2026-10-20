"""Unit tests for transcoding profiles and adaptive bitrate selection."""

from app.transcoding.profiles import (
    STANDARD_PROFILES,
    get_profiles_for_source,
)


def test_standard_profiles_exist() -> None:
    """Verify that standard ABR resolution tiers are defined."""
    assert "1080p" in STANDARD_PROFILES
    assert "720p" in STANDARD_PROFILES
    assert "480p" in STANDARD_PROFILES
    assert "360p" in STANDARD_PROFILES

    p1080 = STANDARD_PROFILES["1080p"]
    assert p1080.height == 1080
    assert p1080.bitrate_kbps == 4500

    p720 = STANDARD_PROFILES["720p"]
    assert p720.height == 720
    assert p720.bitrate_kbps == 2500


def test_get_profiles_for_source_filtering() -> None:
    """Verify that source resolution does not upscale to higher resolutions."""
    # 720p source should get 720p, 480p, 360p (no 1080p)
    profiles_720 = get_profiles_for_source(720)
    names_720 = [p.name for p in profiles_720]
    assert "1080p" not in names_720
    assert "720p" in names_720
    assert "480p" in names_720
    assert "360p" in names_720

    # 1080p source gets all profiles
    profiles_1080 = get_profiles_for_source(1080)
    assert len(profiles_1080) == 4

    # Tiny source (e.g. 240p) defaults to at least 360p
    profiles_tiny = get_profiles_for_source(240)
    assert len(profiles_tiny) == 1
    assert profiles_tiny[0].name == "360p"
