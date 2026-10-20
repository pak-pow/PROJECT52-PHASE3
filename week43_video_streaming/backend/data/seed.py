"""Database seeding script for PulseStream.

Populates initial categories and starter video records.
"""

import sys
from pathlib import Path
from typing import Optional, Union

# Ensure app package is importable when executed directly
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import Config  # noqa: E402
from app.db.connection import get_db_connection, init_db  # noqa: E402
from app.models.category import CategoryModel  # noqa: E402
from app.models.job import TranscodingJobModel  # noqa: E402
from app.models.video import VideoModel  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402

DEFAULT_CATEGORIES = [
    {
        "name": "Technology",
        "slug": "technology",
        "description": "Tech talks, coding tutorials, and engineering demos.",
    },
    {
        "name": "Education",
        "slug": "education",
        "description": "Science explainers, academic lectures, and courses.",
    },
    {
        "name": "Entertainment",
        "slug": "entertainment",
        "description": "Creative shorts, film trailers, and gaming clips.",
    },
    {
        "name": "Nature",
        "slug": "nature",
        "description": "Wildlife cinematography, ocean scenes, and landscapes.",
    },
    {
        "name": "Music",
        "slug": "music",
        "description": "Studio sessions, live acoustic performances, and beats.",
    },
]

STARTER_VIDEOS = [
    {
        "id": "vid-seed-001-bigbuck",
        "title": "Big Buck Bunny - Open Source Animation",
        "description": (
            "A large and lovable rabbit deals with bullying forest creatures "
            "in this classic open source animated short."
        ),
        "category_slug": "entertainment",
        "filename": "big_buck_bunny_720p.mp4",
        "duration": 596.0,
        "size_bytes": 10485760,  # 10 MB representative
        "status": "ready",
        "views_count": 1420,
        "poster_path": "big_buck_bunny_poster.jpg",
    },
    {
        "id": "vid-seed-002-tears",
        "title": "Tears of Steel - Sci-Fi VFX Demo",
        "description": (
            "A group of scientists gather at Oude Kerk in Amsterdam to stage "
            "a key event from the past to save the world from robots."
        ),
        "category_slug": "technology",
        "filename": "tears_of_steel_720p.mp4",
        "duration": 734.0,
        "size_bytes": 15728640,
        "status": "ready",
        "views_count": 890,
        "poster_path": "tears_of_steel_poster.jpg",
    },
    {
        "id": "vid-seed-003-cosmos",
        "title": "Cosmic Web & Galaxy Formation",
        "description": (
            "Astrophysical simulation showing the gravitational clustering of "
            "dark matter and pristine gas into early galaxies."
        ),
        "category_slug": "education",
        "filename": "cosmic_web_480p.mp4",
        "duration": 182.0,
        "size_bytes": 8388608,
        "status": "ready",
        "views_count": 420,
        "poster_path": "cosmic_web_poster.jpg",
    },
]


def seed_database(db_path: Optional[Union[str, Path]] = None) -> None:
    """Initialize schema and seed initial categories and videos."""
    init_db(db_path=db_path)
    storage = StorageService()
    storage.ensure_storage_dirs()

    conn = get_db_connection(db_path=db_path)
    try:
        # 1. Seed categories
        cat_map = {}
        for cat_data in DEFAULT_CATEGORIES:
            existing = CategoryModel.get_by_slug(conn, cat_data["slug"])
            if existing:
                cat_map[cat_data["slug"]] = existing["id"]
            else:
                created = CategoryModel.create(
                    conn,
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    description=cat_data["description"],
                )
                cat_map[cat_data["slug"]] = created["id"]

        # 2. Seed starter videos
        for v in STARTER_VIDEOS:
            existing_video = VideoModel.get_by_id(conn, v["id"])
            if not existing_video:
                cat_id = cat_map.get(v["category_slug"])
                VideoModel.create(
                    conn=conn,
                    video_id=v["id"],
                    title=v["title"],
                    description=v["description"],
                    category_id=cat_id,
                    filename=v["filename"],
                    duration=v["duration"],
                    size_bytes=v["size_bytes"],
                    status=v["status"],
                    poster_path=v["poster_path"],
                )
                # Seed renditions
                VideoModel.add_rendition(
                    conn=conn,
                    video_id=v["id"],
                    resolution="720p",
                    width=1280,
                    height=720,
                    bitrate_kbps=2500,
                    playlist_path=f"hls/{v['id']}/stream_720p.m3u8",
                    segment_count=15,
                )
                VideoModel.add_rendition(
                    conn=conn,
                    video_id=v["id"],
                    resolution="480p",
                    width=854,
                    height=480,
                    bitrate_kbps=1000,
                    playlist_path=f"hls/{v['id']}/stream_480p.m3u8",
                    segment_count=15,
                )
                # Seed completed job
                job = TranscodingJobModel.create(
                    conn=conn, video_id=v["id"], status="completed"
                )
                TranscodingJobModel.mark_completed(conn=conn, job_id=job["id"])
    finally:
        conn.close()


if __name__ == "__main__":
    target = Config.DB_PATH
    print(f"Seeding database at: {target}")
    seed_database(target)
    print("Database seeding completed successfully.")
