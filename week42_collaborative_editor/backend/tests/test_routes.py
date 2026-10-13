from app.services.document_service import DocumentService
from app.services.revision_service import RevisionService
from data.seed import seed_database


def test_health_check(client):
    """Verify health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert "PulsePad" in data["service"]


def test_list_documents(client):
    """Verify list documents endpoint returns JSON list."""
    response = client.get("/api/documents")
    assert response.status_code == 200
    data = response.get_json()
    assert "documents" in data
    assert isinstance(data["documents"], list)


def test_document_and_revision_services(db_conn):
    """Verify Document and Revision models and service operations."""
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO documents (id, title, content, version)
        VALUES ('doc-test', 'Test Doc', 'Initial text', 0)
        """)
    cursor.execute("""
        INSERT INTO revisions (document_id, revision_num, author, operation_json)
        VALUES ('doc-test', 1, 'Alice', '{"components":[]}')
        """)
    db_conn.commit()

    doc_service = DocumentService(db_conn)
    rev_service = RevisionService(db_conn)

    docs = doc_service.list_documents()
    assert len(docs) == 1
    assert docs[0].title == "Test Doc"
    assert docs[0].to_dict()["id"] == "doc-test"

    doc = doc_service.get_document("doc-test")
    assert doc is not None
    assert doc.id == "doc-test"

    missing = doc_service.get_document("non-existent")
    assert missing is None

    revisions = rev_service.get_revisions("doc-test")
    assert len(revisions) == 1
    assert revisions[0].author == "Alice"
    assert revisions[0].to_dict()["revision_num"] == 1


def test_seed_database_execution(tmp_path, monkeypatch):
    """Verify seed_database initializes tables and seed data."""
    test_db = str(tmp_path / "test_seed.db")
    monkeypatch.setattr("app.config.settings.Config.DB_PATH", test_db)
    seed_database()

    from app.db.connection import get_db_connection

    with get_db_connection(test_db) as conn:
        doc_service = DocumentService(conn)
        docs = doc_service.list_documents()
        assert len(docs) == 1
        assert docs[0].id == "welcome-doc"
