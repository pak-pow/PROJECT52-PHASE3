"""REST endpoints for video catalog, uploads, streaming, and HLS playback."""

import uuid
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, Response, current_app, jsonify, request

from app.config.settings import Config
from app.db.connection import get_db_connection
from app.models.category import CategoryModel
from app.models.job import TranscodingJobModel
from app.models.video import VideoModel
from app.services.storage_service import StorageService
from app.services.streaming_service import RangeStreamingEngine

video_bp = Blueprint("videos", __name__, url_prefix="/api")


def _enrich_video_urls(video: Dict[str, Any]) -> Dict[str, Any]:
    """Attach playback streaming and thumbnail URLs to a video record."""
    vid = video["id"]
    poster = video.get("poster_path")
    return {
        **video,
        "stream_url": f"/api/videos/{vid}/stream",
        "hls_url": f"/api/videos/{vid}/hls/master.m3u8",
        "poster_url": f"/api/thumbnails/{poster}" if poster else None,
    }


@video_bp.route("/videos/upload", methods=["POST"])
def upload_video() -> Tuple[Any, int]:
    """Handle multipart video upload, persist raw file, and enqueue transcoding."""
    if "video" not in request.files and "file" not in request.files:
        return jsonify({"error": "Missing video file in request."}), 400

    file = request.files.get("video") or request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"error": "No file selected for upload."}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in Config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(Config.ALLOWED_EXTENSIONS))
        return (
            jsonify({"error": f"Unsupported format '.{ext}'. Allowed: {allowed}"}),
            400,
        )

    title = request.form.get("title", "").strip()
    if not title:
        title = file.filename.rsplit(".", 1)[0]

    description = request.form.get("description", "").strip() or None
    category_id_raw = request.form.get("category_id")
    category_id: Optional[int] = None
    if category_id_raw and str(category_id_raw).isdigit():
        category_id = int(category_id_raw)

    video_id = str(uuid.uuid4())
    safe_filename = f"{video_id}.{ext}"

    storage = StorageService(media_dir=current_app.config.get("MEDIA_DIR"))
    dest_path = storage.get_raw_video_path(safe_filename)
    file.save(dest_path)
    size_bytes = dest_path.stat().st_size
    mime_type = file.content_type or f"video/{'mp4' if ext == 'mp4' else ext}"

    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        video = VideoModel.create(
            conn=conn,
            title=title,
            filename=safe_filename,
            description=description,
            category_id=category_id,
            size_bytes=size_bytes,
            mime_type=mime_type,
            video_id=video_id,
            status="pending",
        )

        queue = getattr(current_app, "transcoding_queue", None)
        if queue:
            job = queue.enqueue(video_id)
        else:
            job = TranscodingJobModel.create(conn, video_id=video_id, status="queued")

        return (
            jsonify(
                {
                    "video": _enrich_video_urls(video),
                    "job": job,
                    "message": (
                        "Video uploaded successfully and enqueued for transcoding."
                    ),
                }
            ),
            201,
        )
    finally:
        conn.close()


@video_bp.route("/videos", methods=["GET"])
def list_videos() -> Tuple[Any, int]:
    """List videos with optional search query, category filtering, and pagination."""
    category_id_raw = request.args.get("category_id")
    category_id: Optional[int] = None
    if category_id_raw and str(category_id_raw).isdigit():
        category_id = int(category_id_raw)

    status = request.args.get("status")
    search = request.args.get("search")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        videos = VideoModel.list_all(
            conn=conn,
            category_id=category_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        enriched = [_enrich_video_urls(v) for v in videos]
        return jsonify({"videos": enriched, "count": len(enriched)}), 200
    finally:
        conn.close()


@video_bp.route("/categories", methods=["GET"])
def list_categories() -> Tuple[Any, int]:
    """List all available video taxonomy categories."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        categories = CategoryModel.list_all(conn)
        return jsonify({"categories": categories, "count": len(categories)}), 200
    finally:
        conn.close()


@video_bp.route("/videos/<video_id>", methods=["GET"])
def get_video_details(video_id: str) -> Tuple[Any, int]:
    """Retrieve video metadata, renditions, and increment views count."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        video = VideoModel.get_by_id(conn, video_id)
        if not video:
            return jsonify({"error": "Video not found."}), 404

        VideoModel.increment_views(conn, video_id)
        refetched = VideoModel.get_by_id(conn, video_id)
        renditions = VideoModel.get_renditions(conn, video_id)

        enriched = _enrich_video_urls(refetched or video)
        return jsonify({"video": enriched, "renditions": renditions}), 200
    finally:
        conn.close()


@video_bp.route("/videos/<video_id>/stream", methods=["GET"])
def stream_video(video_id: str) -> Response:
    """Serve progressive video stream using RFC 7233 partial content byte ranges."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        video = VideoModel.get_by_id(conn, video_id)
        if not video:
            return Response("Video not found", status=404, mimetype="text/plain")

        storage = StorageService(media_dir=current_app.config.get("MEDIA_DIR"))
        raw_path = storage.get_raw_video_path(video["filename"])

        return RangeStreamingEngine.build_stream_response(
            file_path=raw_path,
            range_header=request.headers.get("Range"),
            mime_type=video.get("mime_type", "video/mp4"),
        )
    finally:
        conn.close()


@video_bp.route("/videos/<video_id>/hls/<path:filename>", methods=["GET"])
def serve_hls_asset(video_id: str, filename: str) -> Response:
    """Serve HLS master/variant playlists (.m3u8) and segment chunks (.ts)."""
    storage = StorageService(media_dir=current_app.config.get("MEDIA_DIR"))
    hls_dir = storage.get_video_hls_dir(video_id, create=False)

    safe_hls_dir = hls_dir.resolve()
    target_path = (hls_dir / filename).resolve()

    # Prevent directory traversal attacks
    if not str(target_path).startswith(str(safe_hls_dir)):
        return Response("Forbidden", status=403, mimetype="text/plain")

    if not target_path.is_file():
        return Response("HLS asset not found", status=404, mimetype="text/plain")

    if filename.endswith(".m3u8"):
        mimetype = "application/vnd.apple.mpegurl"
    elif filename.endswith(".ts"):
        mimetype = "video/mp2t"
    else:
        mimetype = "application/octet-stream"

    content = target_path.read_bytes()
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=3600",
    }
    return Response(content, status=200, headers=headers, mimetype=mimetype)


@video_bp.route("/thumbnails/<filename>", methods=["GET"])
def serve_thumbnail(filename: str) -> Response:
    """Serve generated video poster thumbnail images."""
    storage = StorageService(media_dir=current_app.config.get("MEDIA_DIR"))
    thumb_dir = storage.thumbnails_dir.resolve()
    target_path = (storage.thumbnails_dir / filename).resolve()

    if not str(target_path).startswith(str(thumb_dir)) or not target_path.is_file():
        return Response("Thumbnail not found", status=404, mimetype="text/plain")

    content = target_path.read_bytes()
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=86400",
    }
    mimetype = "image/png" if filename.endswith(".png") else "image/jpeg"
    return Response(content, status=200, headers=headers, mimetype=mimetype)


@video_bp.route("/videos/<video_id>", methods=["DELETE"])
def delete_video(video_id: str) -> Tuple[Any, int]:
    """Delete video database record and remove associated media files from disk."""
    db_path = current_app.config.get("DB_PATH")
    conn = get_db_connection(db_path)
    try:
        video = VideoModel.get_by_id(conn, video_id)
        if not video:
            return jsonify({"error": "Video not found."}), 404

        storage = StorageService(media_dir=current_app.config.get("MEDIA_DIR"))
        storage.delete_video_files(
            video_id=video_id,
            raw_filename=video["filename"],
            poster_filename=video.get("poster_path"),
        )

        VideoModel.delete(conn, video_id)
        return (
            jsonify({"message": "Video deleted successfully.", "id": video_id}),
            200,
        )
    finally:
        conn.close()
