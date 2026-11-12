import io

from docx import Document

from app import app


def _make_docx_bytes(text="Hello World"):
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def test_editor_upload_returns_session_token_and_document():
    with app.test_client() as client:
        response = client.post(
            "/api/editor/upload",
            data={"file": (io.BytesIO(_make_docx_bytes("Welcome to Your-Docx-Converter.")), "sample.docx")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200, response.get_data(as_text=True)
        payload = response.get_json()
        assert payload["success"] is True
        assert payload["filename"] == "sample.docx"
        assert payload["token"]
        assert payload["document"]["paragraphs"][0]["text"] == "Welcome to Your-Docx-Converter."


def test_editor_document_requires_valid_session_token():
    with app.test_client() as client:
        response = client.get("/api/editor/document")
        assert response.status_code == 401

        upload_response = client.post(
            "/api/editor/upload",
            data={"file": (io.BytesIO(_make_docx_bytes("Alpha Beta")), "session-test.docx")},
            content_type="multipart/form-data",
        )
        token = upload_response.get_json()["token"]

        response = client.get(
            "/api/editor/document",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.get_json()["filename"] == "session-test.docx"


def test_editor_sessions_are_isolated():
    with app.test_client() as client:
        first = client.post(
            "/api/editor/upload",
            data={"file": (io.BytesIO(_make_docx_bytes("Original Text")), "first.docx")},
            content_type="multipart/form-data",
        ).get_json()
        second = client.post(
            "/api/editor/upload",
            data={"file": (io.BytesIO(_make_docx_bytes("Other Document")), "second.docx")},
            content_type="multipart/form-data",
        ).get_json()

        client.post(
            "/api/editor/action",
            headers={"Authorization": f"Bearer {first['token']}"},
            json={"action": "replace", "find_text": "Original", "replace_text": "Updated", "replace_all": False},
        )

        first_doc = client.get(
            "/api/editor/document",
            headers={"Authorization": f"Bearer {first['token']}"},
        ).get_json()
        second_doc = client.get(
            "/api/editor/document",
            headers={"Authorization": f"Bearer {second['token']}"},
        ).get_json()

        assert "Updated Text" in first_doc["document"]["paragraphs"][0]["text"]
        assert second_doc["document"]["paragraphs"][0]["text"] == "Other Document"
