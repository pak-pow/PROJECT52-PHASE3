"""Storage service managing model artifacts, weights, and configuration paths."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.config.settings import Config


class StorageService:
    """Manages models vault directory layout and artifact persistence."""

    def __init__(
        self,
        vault_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize storage service with base models vault directory."""
        self.vault_dir = Path(vault_dir or Config.MODELS_VAULT_DIR)

    def ensure_storage_dirs(self) -> None:
        """Create base storage vault directory if not present."""
        self.vault_dir.mkdir(parents=True, exist_ok=True)

    def get_model_version_dir(self, model_id: str, version: str) -> Path:
        """Retrieve path for a specific model version artifact directory."""
        m_dir = self.vault_dir / model_id.strip().lower() / version.strip().lower()
        m_dir.mkdir(parents=True, exist_ok=True)
        return m_dir

    def get_artifact_path(
        self, model_id: str, version: str, filename: str = "weights.json"
    ) -> Path:
        """Generate absolute filesystem path for a model artifact file."""
        v_dir = self.get_model_version_dir(model_id, version)
        return v_dir / filename

    def get_storage_stats(self) -> Dict[str, Any]:
        """Calculate total model artifact files and cumulative size in bytes."""
        if not self.vault_dir.exists():
            return {"total_models": 0, "total_files": 0, "size_bytes": 0}

        total_files = 0
        total_size = 0
        model_dirs = [d for d in self.vault_dir.iterdir() if d.is_dir()]

        for path in self.vault_dir.rglob("*"):
            if path.is_file():
                total_files += 1
                total_size += path.stat().st_size

        return {
            "total_models": len(model_dirs),
            "total_files": total_files,
            "size_bytes": total_size,
        }
