"""Unit tests for the model artifact storage service."""

from pathlib import Path

from app.services.storage_service import StorageService


def test_storage_service_initialization(temp_dir: Path) -> None:
    """Verify storage vault directories are created on initialization."""
    vault = temp_dir / "vault"
    storage = StorageService(vault_dir=vault)
    storage.ensure_storage_dirs()

    assert vault.exists()
    assert vault.is_dir()


def test_storage_path_generation(temp_dir: Path) -> None:
    """Verify model version directory and artifact path resolution."""
    vault = temp_dir / "vault"
    storage = StorageService(vault_dir=vault)

    version_dir = storage.get_model_version_dir("nlp-model", "v1")
    assert version_dir.exists()
    assert version_dir == vault / "nlp-model" / "v1"

    weights_file = storage.get_artifact_path("nlp-model", "v1", "weights.json")
    assert weights_file == version_dir / "weights.json"


def test_storage_stats_calculation(temp_dir: Path) -> None:
    """Verify calculation of model artifact counts and disk utilization."""
    vault = temp_dir / "vault"
    storage = StorageService(vault_dir=vault)

    # Initially empty
    stats_empty = storage.get_storage_stats()
    assert stats_empty["total_models"] == 0
    assert stats_empty["total_files"] == 0
    assert stats_empty["size_bytes"] == 0

    # Write files
    p1 = storage.get_artifact_path("m1", "v1", "weights.json")
    p1.write_bytes(b"1234567890")

    p2 = storage.get_artifact_path("m2", "v1", "weights.json")
    p2.write_bytes(b"abcdefgh")

    stats = storage.get_storage_stats()
    assert stats["total_models"] == 2
    assert stats["total_files"] == 2
    assert stats["size_bytes"] == 18
