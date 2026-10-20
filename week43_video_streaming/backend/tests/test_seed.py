"""Integration tests for database seeding."""

from pathlib import Path

from app.db.connection import get_db_connection
from app.models.category import CategoryModel
from app.models.video import VideoModel
from data.seed import seed_database


def test_seed_database(temp_dir: Path) -> None:
    """Verify that seed_database populates categories and starter videos."""
    db_file = temp_dir / "seed_test.db"
    seed_database(db_path=db_file)

    conn = get_db_connection(db_path=db_file)
    try:
        categories = CategoryModel.list_all(conn)
        assert len(categories) >= 5
        slugs = [c["slug"] for c in categories]
        assert "technology" in slugs
        assert "entertainment" in slugs
        assert "education" in slugs

        videos = VideoModel.list_all(conn)
        assert len(videos) >= 3

        # Check renditions for first video
        renditions = VideoModel.get_renditions(conn, videos[0]["id"])
        assert len(renditions) >= 2
    finally:
        conn.close()
