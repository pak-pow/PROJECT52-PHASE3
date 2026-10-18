"""Tests for application HTTP REST endpoints, models, and services."""

import pytest

from app.engine.operation import TextOperation, create_operation_from_diff
from app.models.document_model import Document
from app.models.snapshot_model import Snapshot
from app.services.document_service import DocumentService
from app.services.revision_service import RevisionService
from app.socket.editor_events import room_manager
from data.seed import seed_database


def test_health_check(client):
    """Verify health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert "PulsePad" in data["service"]


def test_index_route(client):
    """Verify index route serves frontend workbench HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"PulsePad" in response.data


def test_list_documents(client):
    """Verify list documents endpoint returns JSON list."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.get_json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


def test_create_operation_from_diff():
    """Verify diff derivation generates accurate TextOperations."""
    # Identical text (noop)
    op_same = create_operation_from_diff("abc", "abc")
    assert op_same.apply("abc") == "abc"

    # Insertion
    op_ins = create_operation_from_diff("hello", "hello world")
    assert op_ins.apply("hello") == "hello world"

    # Deletion
    op_del = create_operation_from_diff("hello world", "hello")
    assert op_del.apply("hello world") == "hello"

    # Replacement in middle
    op_rep = create_operation_from_diff("alpha one beta", "alpha two beta")
    assert op_rep.apply("alpha one beta") == "alpha two beta"

    # From empty and to empty
    op_to_empty = create_operation_from_diff("content", "")
    assert op_to_empty.apply("content") == ""
    op_from_empty = create_operation_from_diff("", "fresh")
    assert op_from_empty.apply("") == "fresh"


def test_document_and_revision_services(db_conn):
    """Verify Document and Revision models and service operations."""
    doc_service = DocumentService(db_conn)
    rev_service = RevisionService(db_conn)

    doc = doc_service.create_document(
        doc_id="doc-test",
        title="Test Doc",
        content="Initial text",
        version=0,
    )
    assert doc.id == "doc-test"
    assert doc.title == "Test Doc"

    rev_op = TextOperation().retain(12).insert(" added")
    rev = rev_service.record_revision(
        doc_id="doc-test",
        revision_num=1,
        author="Alice",
        operation=rev_op,
        current_content="Initial text added",
    )
    assert rev.revision_num == 1
    assert rev.author == "Alice"

    # Test update via save_document
    updated_doc = doc_service.save_document(
        doc_id="doc-test",
        content="Initial text added",
        version=1,
        title="Updated Title",
    )
    assert updated_doc.content == "Initial text added"
    assert updated_doc.version == 1
    assert updated_doc.title == "Updated Title"

    # Test export document
    content, mime_txt, name_txt = doc_service.export_document(
        "doc-test", format_type="txt"
    )
    assert content == "Initial text added"
    assert "text/plain" in mime_txt
    assert name_txt == "doc-test.txt"

    content_md, mime_md, name_md = doc_service.export_document(
        "doc-test", format_type="markdown"
    )
    assert "text/markdown" in mime_md
    assert name_md == "doc-test.md"

    # Nonexistent export raises ValueError
    with pytest.raises(ValueError):
        doc_service.export_document("non-existent")

    # Document deletion
    assert Document.delete(db_conn, "doc-test") is True
    assert Document.delete(db_conn, "doc-test") is False


def test_snapshot_model_and_reconstruction(db_conn):
    """Verify point-in-time snapshots and revision reconstruction."""
    doc_service = DocumentService(db_conn)
    rev_service = RevisionService(db_conn)

    doc_service.create_document(
        doc_id="doc-history",
        title="History Doc",
        content="Start",
        version=0,
    )
    rev_service.create_snapshot("doc-history", 0, "Start")

    # Rev 1: "Start" -> "Start here"
    op1 = TextOperation().retain(5).insert(" here")
    rev_service.record_revision(
        "doc-history", 1, "Alice", op1, current_content="Start here"
    )

    # Rev 2: "Start here" -> "Start right here"
    op2 = TextOperation().retain(6).insert("right ").retain(4)
    rev_service.record_revision(
        "doc-history", 2, "Bob", op2, current_content="Start right here"
    )

    # Reconstruct at rev 0, 1, 2
    assert rev_service.get_content_at_revision("doc-history", 0) == "Start"
    assert rev_service.get_content_at_revision("doc-history", 1) == "Start here"
    assert rev_service.get_content_at_revision("doc-history", 2) == "Start right here"

    # Test snapshot query
    snapshots = rev_service.get_snapshots("doc-history")
    assert len(snapshots) >= 2  # rev 0 and auto rev 1 snapshot
    latest_snap = Snapshot.get_latest_before_or_at(db_conn, "doc-history", 2)
    assert latest_snap is not None
    assert latest_snap.revision_num in (0, 1)

    # Test single revision retrieval
    rev1 = rev_service.get_revision("doc-history", 1)
    assert rev1 is not None
    assert rev1.author == "Alice"
    assert rev_service.get_revision("doc-history", 999) is None

    # Rollback to revision 1
    doc_service.save_document("doc-history", "Start right here", 2, "History Doc")
    rolled_content, new_ver, rollback_rev = rev_service.rollback_document(
        "doc-history", 1, author="Tester"
    )
    assert rolled_content == "Start here"
    assert new_ver == 3
    assert rollback_rev.author == "Tester"

    # Validation errors
    with pytest.raises(ValueError):
        rev_service.get_content_at_revision("doc-history", -1)

    with pytest.raises(ValueError):
        rev_service.rollback_document("doc-history", 999)

    with pytest.raises(ValueError):
        rev_service.rollback_document("non-existent-doc", 0)


def test_rest_get_and_revisions(client, db_conn):
    """Verify GET /api/documents/<doc_id> and revisions endpoints."""
    # Seed document
    doc_service = DocumentService(db_conn)
    doc_service.create_document(
        doc_id="doc-api",
        title="API Doc",
        content="API test content",
        version=1,
    )
    rev_service = RevisionService(db_conn)
    op = TextOperation().insert("API test content")
    rev_service.record_revision("doc-api", 1, "Alice", op, "API test content")

    # Get existing document
    res = client.get("/api/documents/doc-api")
    assert res.status_code == 200
    doc_data = res.get_json()["document"]
    assert doc_data["id"] == "doc-api"
    assert doc_data["title"] == "API Doc"
    assert doc_data["content"] == "API test content"

    # Get non-existing document
    res_404 = client.get("/api/documents/unknown-doc")
    assert res_404.status_code == 404

    # Get revisions
    res_revs = client.get("/api/documents/doc-api/revisions")
    assert res_revs.status_code == 200
    revs_data = res_revs.get_json()
    assert revs_data["count"] == 1
    assert revs_data["revisions"][0]["author"] == "Alice"

    # Revisions for unknown doc
    assert client.get("/api/documents/unknown-doc/revisions").status_code == 404


def test_rest_rollback_endpoint(client, db_conn):
    """Verify POST /api/documents/<doc_id>/rollback endpoint behavior."""
    doc_service = DocumentService(db_conn)
    rev_service = RevisionService(db_conn)

    doc_service.create_document(
        doc_id="doc-rb",
        title="Rollback Test",
        content="V0 Text",
        version=0,
    )
    rev_service.create_snapshot("doc-rb", 0, "V0 Text")

    op1 = TextOperation().retain(7).insert(" + V1")
    rev_service.record_revision("doc-rb", 1, "Alice", op1, "V0 Text + V1")
    doc_service.save_document("doc-rb", "V0 Text + V1", 1)

    # Active room session
    room_manager.get_or_create_room("doc-rb", "Rollback Test", "V0 Text + V1", 1)

    # Missing target_revision
    res_bad = client.post("/api/documents/doc-rb/rollback", json={})
    assert res_bad.status_code == 400

    # Out of range target_revision
    res_oor = client.post(
        "/api/documents/doc-rb/rollback", json={"target_revision": 100}
    )
    assert res_oor.status_code == 400

    # Nonexistent doc
    res_404 = client.post(
        "/api/documents/ghost-doc/rollback", json={"target_revision": 0}
    )
    assert res_404.status_code == 404

    # Successful rollback to V0
    res_ok = client.post(
        "/api/documents/doc-rb/rollback",
        json={"target_revision": 0, "author": "Admin Rollback"},
    )
    assert res_ok.status_code == 200
    rb_data = res_ok.get_json()
    assert rb_data["version"] == 2
    assert rb_data["content"] == "V0 Text"
    assert room_manager.rooms["doc-rb"].content == "V0 Text"
    assert room_manager.rooms["doc-rb"].version == 2


def test_rest_export_endpoint(client, db_conn):
    """Verify GET /api/documents/<doc_id>/export endpoint."""
    doc_service = DocumentService(db_conn)
    doc_service.create_document(
        doc_id="doc-export",
        title="Export Test",
        content="# Hello World\nSample export.",
        version=1,
    )

    # Text export
    res_txt = client.get("/api/documents/doc-export/export?format=txt")
    assert res_txt.status_code == 200
    assert "text/plain" in res_txt.content_type
    assert b"Hello World" in res_txt.data

    # Markdown export
    res_md = client.get("/api/documents/doc-export/export?format=markdown")
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.content_type

    # 404 for missing doc
    res_404 = client.get("/api/documents/missing/export")
    assert res_404.status_code == 404


def test_seed_database_execution(tmp_path, monkeypatch):
    """Verify seed_database initializes tables, starter doc, and snapshot."""
    test_db = str(tmp_path / "test_seed.db")
    monkeypatch.setattr("app.config.settings.Config.DB_PATH", test_db)
    seed_database()

    from app.db.connection import get_db_connection

    with get_db_connection(test_db) as conn:
        doc_service = DocumentService(conn)
        docs = doc_service.list_documents()
        assert len(docs) == 1
        assert docs[0].id == "welcome-doc"

        rev_service = RevisionService(conn)
        snaps = rev_service.get_snapshots("welcome-doc")
        assert len(snaps) == 1
        assert snaps[0].revision_num == 0


def test_list_and_get_documents_with_active_room(client, db_conn):
    """Verify live room attributes overlay on document listing and retrieval."""
    doc_service = DocumentService(db_conn)
    doc_service.create_document(
        doc_id="doc-live",
        title="DB Title",
        content="DB Content",
        version=1,
    )
    room_manager.get_or_create_room(
        doc_id="doc-live",
        title="Live Title",
        initial_content="Live Active Content",
        initial_version=5,
    )

    # Verify list documents overlays live room
    res_list = client.get("/api/documents")
    docs = res_list.get_json()["documents"]
    live_match = [d for d in docs if d["id"] == "doc-live"][0]
    assert live_match["title"] == "Live Title"
    assert live_match["content"] == "Live Active Content"
    assert live_match["version"] == 5

    # Verify get document overlays live room
    res_get = client.get("/api/documents/doc-live")
    doc_data = res_get.get_json()["document"]
    assert doc_data["title"] == "Live Title"
    assert doc_data["content"] == "Live Active Content"

    # Export overlays live room content
    res_exp = client.get("/api/documents/doc-live/export?format=markdown")
    assert b"Live Active Content" in res_exp.data

    # Room-only document without DB entry
    room_manager.get_or_create_room(
        doc_id="mem-only",
        title="Memory Only",
        initial_content="In Memory",
        initial_version=1,
    )
    res_mem = client.get("/api/documents/mem-only")
    assert res_mem.status_code == 200
    assert res_mem.get_json()["document"]["title"] == "Memory Only"


def test_revision_service_operation_variants_and_fallbacks(db_conn):
    """Verify RevisionService handles dict, str, and missing snapshot fallbacks."""
    rev_service = RevisionService(db_conn)
    doc_service = DocumentService(db_conn)

    doc_service.create_document("doc-poly", "Poly", "", 0)

    # Dict operation
    rev_dict = rev_service.record_revision(
        "doc-poly", 1, "Alice", {"components": [{"kind": "insert", "value": "A"}]}
    )
    assert rev_dict.revision_num == 1

    # String operation
    op_str = (
        '{"components": [{"kind": "retain", "value": 1}, '
        '{"kind": "insert", "value": "B"}]}'
    )
    rev_str = rev_service.record_revision("doc-poly", 2, "Bob", op_str)
    assert rev_str.revision_num == 2

    # Reconstruction with no snapshots
    reconstructed = rev_service.get_content_at_revision("doc-poly", 2)
    assert reconstructed == "AB"

    # Revision 0 when doc does not exist
    empty_content = rev_service.get_content_at_revision("ghost-doc", 0)
    assert empty_content == ""
