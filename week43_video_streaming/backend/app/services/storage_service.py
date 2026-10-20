"""Storage service managing physical media directories and file artifacts."""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from app.config.settings import Config


class StorageService:
    """Manages physical storage for raw uploads, HLS streams, and posters."""

    def __init__(self, media_dir: Optional[Path] = None) -> None:
        """Initialize storage service with custom or default media directory."""
        self.media_dir = Path(media_dir) if media_dir else Config.MEDIA_DIR
        self.raw_dir = self.media_dir / "raw"
        self.hls_dir = self.media_dir / "hls"
        self.thumbnails_dir = self.media_dir / "thumbnails"
        self.ensure_storage_dirs()

    def ensure_storage_dirs(self) -> None:
        """Ensure all required media directories exist on disk."""
        for directory in (
            self.media_dir,
            self.raw_dir,
            self.hls_dir,
            self.thumbnails_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def get_raw_video_path(self, filename: str) -> Path:
        """Return the absolute path for a raw uploaded video file."""
        safe_filename = Path(filename).name
        return self.raw_dir / safe_filename

    def get_video_hls_dir(self, video_id: str, create: bool = True) -> Path:
        """Return the directory containing HLS manifests and segments for a video."""
        safe_id = Path(video_id).name
        target = self.hls_dir / safe_id
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def get_thumbnail_path(self, filename: str) -> Path:
        """Return the absolute path for a video poster thumbnail."""
        safe_filename = Path(filename).name
        return self.thumbnails_dir / safe_filename

    def delete_video_files(
        self,
        video_id: str,
        raw_filename: Optional[str] = None,
        poster_filename: Optional[str] = None,
    ) -> None:
        """Safely remove all media artifacts associated with a video."""
        # Remove raw video file
        if raw_filename:
            raw_path = self.get_raw_video_path(raw_filename)
            if raw_path.exists():
                try:
                    raw_path.unlink()
                except OSError:
                    pass

        # Remove HLS directory tree
        hls_dir = self.get_video_hls_dir(video_id, create=False)
        if hls_dir.exists():
            shutil.rmtree(hls_dir, ignore_errors=True)

        # Remove thumbnail
        if poster_filename:
            poster_path = self.get_thumbnail_path(poster_filename)
            if poster_path.exists():
                try:
                    poster_path.unlink()
                except OSError:
                    pass

    def get_storage_stats(self) -> Dict[str, Any]:
        """Compute file counts and byte size statistics for media directories."""
        self.ensure_storage_dirs()
        stats: Dict[str, Any] = {
            "raw_count": 0,
            "raw_bytes": 0,
            "hls_videos_count": 0,
            "hls_bytes": 0,
            "thumbnails_count": 0,
            "thumbnails_bytes": 0,
            "total_bytes": 0,
        }

        # Raw uploads stats
        if self.raw_dir.exists():
            for item in self.raw_dir.iterdir():
                if item.is_file() and not item.name.startswith("."):
                    stats["raw_count"] += 1
                    stats["raw_bytes"] += item.stat().st_size

        # HLS stats
        if self.hls_dir.exists():
            for subdir in self.hls_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("."):
                    stats["hls_videos_count"] += 1
                    for root, _, files in os.walk(subdir):
                        for file in files:
                            if not file.startswith("."):
                                fpath = Path(root) / file
                                if fpath.is_file():
                                    stats["hls_bytes"] += fpath.stat().st_size

        # Thumbnails stats
        if self.thumbnails_dir.exists():
            for item in self.thumbnails_dir.iterdir():
                if item.is_file() and not item.name.startswith("."):
                    stats["thumbnails_count"] += 1
                    stats["thumbnails_bytes"] += item.stat().st_size

        stats["total_bytes"] = (
            stats["raw_bytes"] + stats["hls_bytes"] + stats["thumbnails_bytes"]
        )
        return stats
