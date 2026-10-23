"""Asynchronous background transcoding queue and worker thread service."""

import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.models.job import TranscodingJobModel
from app.models.video import VideoModel
from app.services.hls_packager import HLSPackager
from app.services.media_inspector import MediaInspector
from app.services.storage_service import StorageService
from app.transcoding.profiles import get_profiles_for_source


class TranscodingWorker:
    """Daemon thread worker consuming queued video transcoding tasks."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        media_dir: Optional[Union[str, Path]] = None,
        poll_interval: float = 0.2,
    ) -> None:
        """Initialize worker with database path and storage configuration."""
        self.db_path = db_path or Config.DB_PATH
        self.storage = StorageService(media_dir=media_dir)
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        """Return True if background worker thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start background daemon thread if not already running."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="PulseStream-TranscodingWorker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Signal worker thread to stop and wait for termination."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def _worker_loop(self) -> None:
        """Continuous polling loop picking up queued transcoding jobs."""
        while not self._stop_event.is_set():
            processed = self.process_next_job()
            if not processed:
                time.sleep(self.poll_interval)

    def process_next_job(self) -> bool:
        """Check for and process the next available queued job in database."""
        conn = get_db_connection(self.db_path)
        try:
            queued_jobs = TranscodingJobModel.list_by_status(
                conn, status="queued", limit=1
            )
            if not queued_jobs:
                return False

            job = queued_jobs[0]
            self._execute_job(conn, job)
            return True
        finally:
            conn.close()

    def process_single_job(self, job_id: str) -> bool:
        """Synchronously process a specific job by ID for direct execution."""
        conn = get_db_connection(self.db_path)
        try:
            job = TranscodingJobModel.get_by_id(conn, job_id)
            if not job:
                return False
            self._execute_job(conn, job)
            return True
        finally:
            conn.close()

    def _execute_job(
        self,
        conn: Any,
        job: Dict[str, Any],
    ) -> None:
        """Execute four-stage transcoding lifecycle with progress updates."""
        job_id = job["id"]
        video_id = job["video_id"]

        try:
            # 0. Initial state verification
            video = VideoModel.get_by_id(conn, video_id)
            if not video:
                raise ValueError(f"Video {video_id} not found in database.")

            raw_path = self.storage.get_raw_video_path(video["filename"])
            if not raw_path.is_file():
                raise FileNotFoundError(
                    f"Raw media asset not found on disk: {raw_path}"
                )

            # Stage 1: Inspect media metadata (15%)
            TranscodingJobModel.update_progress(
                conn, job_id, progress=15, current_stage="inspecting"
            )
            VideoModel.update_status(conn, video_id, status="processing")

            meta = MediaInspector.inspect(raw_path)
            duration = meta.duration if meta.duration > 0 else 10.0
            VideoModel.update_status(
                conn, video_id, status="processing", duration=duration
            )

            # Stage 2: Generate video poster thumbnail (30%)
            TranscodingJobModel.update_progress(
                conn, job_id, progress=30, current_stage="thumbnailing"
            )
            poster_filename = f"{video_id}_poster.jpg"
            poster_path = self.storage.get_thumbnail_path(poster_filename)
            MediaInspector.generate_thumbnail(
                video_path=raw_path,
                output_path=poster_path,
                title=video["title"],
            )
            VideoModel.update_status(
                conn, video_id, status="processing", poster_path=poster_filename
            )

            # Stage 3: Multi-profile HLS packaging (50% -> 85%)
            TranscodingJobModel.update_progress(
                conn, job_id, progress=50, current_stage="packaging_hls"
            )
            hls_dir = self.storage.get_video_hls_dir(video_id)
            target_profiles = get_profiles_for_source(meta.height)

            package_result = HLSPackager.package_video(
                source_path=raw_path,
                output_dir=hls_dir,
                video_id=video_id,
                profiles=target_profiles,
            )

            # Stage 4: Persist rendition profiles (85% -> 100%)
            TranscodingJobModel.update_progress(
                conn, job_id, progress=85, current_stage="saving_renditions"
            )
            for rend in package_result.renditions:
                VideoModel.add_rendition(
                    conn=conn,
                    video_id=video_id,
                    resolution=rend.name,
                    width=rend.width,
                    height=rend.height,
                    bitrate_kbps=rend.bitrate_kbps,
                    playlist_path=rend.playlist_path,
                    segment_count=rend.segment_count,
                )

            # Finalize: Mark job complete and video ready
            VideoModel.update_status(
                conn,
                video_id=video_id,
                status="ready",
                duration=duration,
                poster_path=poster_filename,
            )
            TranscodingJobModel.mark_completed(conn, job_id)

        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            TranscodingJobModel.mark_failed(conn, job_id, error_message=err_msg)
            VideoModel.update_status(conn, video_id, status="failed")


class TranscodingQueue:
    """Thread-safe facade coordinating job creation and worker lifecycle."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        media_dir: Optional[Union[str, Path]] = None,
        autostart_worker: bool = False,
    ) -> None:
        """Initialize transcoding queue manager and optional worker."""
        self.db_path = db_path or Config.DB_PATH
        self.media_dir = media_dir or Config.MEDIA_DIR
        self._worker = TranscodingWorker(
            db_path=self.db_path,
            media_dir=self.media_dir,
        )
        self._internal_queue: queue.Queue = queue.Queue()

        if autostart_worker:
            self.start_worker()

    @property
    def is_worker_running(self) -> bool:
        """Return True if background worker thread is actively polling."""
        return self._worker.is_running

    def start_worker(self) -> None:
        """Start the background transcoding worker thread."""
        self._worker.start()

    def stop_worker(self, timeout: float = 3.0) -> None:
        """Stop background worker thread."""
        self._worker.stop(timeout=timeout)

    def enqueue(self, video_id: str) -> Dict[str, Any]:
        """Create a new queued transcoding job in database and return record."""
        conn = get_db_connection(self.db_path)
        try:
            job = TranscodingJobModel.create(conn, video_id=video_id, status="queued")
            self._internal_queue.put(job["id"])
            return job
        finally:
            conn.close()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve latest job progress and stage by ID."""
        conn = get_db_connection(self.db_path)
        try:
            return TranscodingJobModel.get_by_id(conn, job_id)
        finally:
            conn.close()

    def get_job_for_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve most recent job for a video."""
        conn = get_db_connection(self.db_path)
        try:
            return TranscodingJobModel.get_by_video_id(conn, video_id)
        finally:
            conn.close()

    def list_active_jobs(self) -> List[Dict[str, Any]]:
        """List all pending or in-flight transcoding jobs."""
        conn = get_db_connection(self.db_path)
        try:
            queued = TranscodingJobModel.list_by_status(conn, status="queued")
            processing = TranscodingJobModel.list_by_status(conn, status="processing")
            return queued + processing
        finally:
            conn.close()

    def process_single(self, job_id: str) -> bool:
        """Synchronously execute a specific job on demand."""
        return self._worker.process_single_job(job_id)
