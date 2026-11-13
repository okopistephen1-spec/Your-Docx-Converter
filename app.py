import fnmatch
import json
import os
import secrets
import time
import uuid
import zipfile
from pathlib import Path

from docx import Document
from docx.shared import Pt
from flask import Flask, jsonify, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from database import database_status, init_database
from services.google_auth import google_auth_bp
from services.document_editor import (
    add_paragraph,
    add_table_column,
    add_table_row,
    delete_paragraph,
    delete_table_column,
    delete_table_row,
    format_paragraph,
    replace_all_text,
    replace_text,
    save_document,
    update_paragraph,
    update_table_cell,
)
from services.pdf_to_image import convert_pdf_to_images
from services.pdf_to_word import convert_pdf_to_word
from services.word_to_pdf import convert_word_to_pdf

app = Flask(__name__)
app.register_blueprint(google_auth_bp)


def resolve_secret_key():
    environment = os.environ.get("APP_ENV", "development").lower()
    secret_key = os.environ.get("SECRET_KEY")
    if environment == "production":
        if not secret_key or secret_key == "docx-converter-dev-secret":
            raise RuntimeError("Production SECRET_KEY is not configured.")
        return secret_key
    return secret_key or "docx-converter-dev-secret"


app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["SECRET_KEY"] = resolve_secret_key()
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "true" if os.environ.get("APP_ENV", "development").lower() == "production" else "false").lower() in {"1", "true", "yes"}

init_database(app)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
CONVERTED_FOLDER = BASE_DIR / "converted"
EDITOR_FOLDER = UPLOAD_FOLDER / "editor"
SESSION_STORE = UPLOAD_FOLDER / "sessions"
SESSION_TTL_SECONDS = int(os.environ.get("EDITOR_SESSION_TTL_SECONDS", str(60 * 60 * 24)))

with app.app_context():
    app.config["DATABASE_STATUS"] = database_status()
    if not app.config.get("DATABASE_CONFIGURED"):
        app.logger.warning("Database not configured: set DATABASE_URL to enable database-backed features.")

for folder in (UPLOAD_FOLDER, CONVERTED_FOLDER, EDITOR_FOLDER, SESSION_STORE):
    folder.mkdir(parents=True, exist_ok=True)


class EditorSessionError(RuntimeError):
    def __init__(self, message, status_code=401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _allowed_origins():
    configured = []
    for entry in (
        os.environ.get("FRONTEND_ORIGIN"),
        os.environ.get("CORS_ALLOWED_ORIGINS"),
    ):
        if not entry:
            continue
        configured.extend([part.strip() for part in entry.split(",") if part.strip()])

    defaults = [
        "https://your-docx-converter-frontend.vercel.app",
        "http://localhost:3000",
        "http://localhost:4173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:4173",
    ]
    return list(dict.fromkeys(configured + defaults))


def _origin_allowed(origin):
    if not origin:
        return True
    return origin in _allowed_origins()


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"
    if request.method == "OPTIONS":
        response.status_code = 204
    return response


@app.errorhandler(EditorSessionError)
def handle_editor_session_error(error):
    return jsonify({"error": error.message}), error.status_code


def _serialize_document(document):
    paragraphs = []
    for index, paragraph in enumerate(document.paragraphs):
        paragraphs.append({
            "index": index,
            "text": paragraph.text,
            "style": paragraph.style.name if paragraph.style else None,
            "alignment": str(paragraph.alignment),
        })

    tables = []
    for table_index, table in enumerate(document.tables):
        tables.append({
            "index": table_index,
            "rows": [[cell.text for cell in row.cells] for row in table.rows],
        })

    return {"paragraphs": paragraphs, "tables": tables}


def _secure_path_under_base(candidate_path, base_path):
    resolved_candidate = Path(candidate_path).resolve()
    resolved_base = Path(base_path).resolve()
    if not resolved_candidate.is_relative_to(resolved_base):
        raise EditorSessionError("Invalid document path requested.", 403)
    return str(resolved_candidate)


def _get_or_create_legacy_editor_session_dir():
    session_id = session.get("editor_session_id")
    if not session_id:
        session_id = uuid.uuid4().hex
        session["editor_session_id"] = session_id

    session_dir = EDITOR_FOLDER / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _load_document_from_session():
    document_path = session.get("editor_document_path")
    if not document_path:
        raise FileNotFoundError("No document is currently open in the editor.")

    secure_path = _secure_path_under_base(document_path, EDITOR_FOLDER)
    if not os.path.exists(secure_path):
        raise FileNotFoundError("The current editor document could not be found.")

    return Document(secure_path)


def _editor_token_from_request():
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
            if token:
                return token
        raise EditorSessionError("Invalid authorization token.", 401)

    token = (request.get_json(silent=True) or {}).get("token") or request.args.get("token")
    if not token:
        raise EditorSessionError("Authentication required.", 401)
    return token


def _session_store_path(token):
    return SESSION_STORE / f"{token}.json"


def _read_session_record(token):
    if not token:
        raise EditorSessionError("Authentication required.", 401)

    session_file = _session_store_path(token)
    if not session_file.exists():
        raise EditorSessionError("Session not found or expired.", 401)

    try:
        with session_file.open("r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (json.JSONDecodeError, OSError):
        session_file.unlink(missing_ok=True)
        raise EditorSessionError("Session not found or expired.", 401)

    if record.get("expires_at", 0) <= time.time():
        session_file.unlink(missing_ok=True)
        raise EditorSessionError("Editor session expired.", 401)

    return record


def _write_session_record(record):
    token = record["token"]
    with _session_store_path(token).open("w", encoding="utf-8") as handle:
        json.dump(record, handle)


def _create_editor_session(document_path, filename):
    token = secrets.token_urlsafe(32)
    while _session_store_path(token).exists():
        token = secrets.token_urlsafe(32)

    record = {
        "token": token,
        "filename": filename,
        "document_path": str(document_path),
        "created_at": int(time.time()),
        "expires_at": int(time.time()) + SESSION_TTL_SECONDS,
    }
    _write_session_record(record)
    return record


def _editor_document_record(token):
    record = _read_session_record(token)
    document_path = _secure_path_under_base(record["document_path"], EDITOR_FOLDER)
    if not os.path.exists(document_path):
        raise EditorSessionError("The uploaded document is no longer available.", 404)
    return record, document_path


def _render_editor_payload(document_path, filename):
    document = Document(document_path)
    return {
        "filename": filename,
        "document": _serialize_document(document),
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/converter")
def converter():
    return render_template("converter.html")


@app.route("/editor")
def editor():
    return render_template("editor.html")


@app.route("/editor/upload", methods=["POST"])
def editor_upload():
    uploaded_file = request.files.get("file")

    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify({"error": "Please select a DOCX file."}), 400

    filename = secure_filename(uploaded_file.filename)
    if not filename or not filename.lower().endswith(".docx"):
        return jsonify({"error": "Please upload a valid DOCX file."}), 400

    session_dir = _get_or_create_legacy_editor_session_dir()
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    document_path = session_dir / unique_name

    try:
        uploaded_file.save(str(document_path))
        session["editor_document_path"] = str(document_path)
        session["editor_document_name"] = filename

        payload = _render_editor_payload(str(document_path), filename)
        return jsonify({"success": True, "filename": filename, "document": payload["document"]})
    except Exception:
        app.logger.exception("Editor upload failed")
        return jsonify({"error": "The uploaded file could not be opened as a valid DOCX document."}), 400


@app.route("/editor/document", methods=["GET"])
def editor_document():
    document_path = session.get("editor_document_path")
    if not document_path or not os.path.exists(document_path):
        return jsonify({"error": "No document is open."}), 404

    try:
        payload = _render_editor_payload(document_path, session.get("editor_document_name", "document.docx"))
        return jsonify(payload)
    except Exception:
        app.logger.exception("Loading editor document failed")
        return jsonify({"error": "The document could not be loaded."}), 500


@app.route("/editor/action", methods=["POST"])
def editor_action():
    data = request.get_json(silent=True) or {}

    try:
        document = _load_document_from_session()
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    action = data.get("action")

    try:
        if action == "replace":
            find_text = data.get("find_text", "")
            replace_text_value = data.get("replace_text", "")
            replace_all = bool(data.get("replace_all", False))

            if not find_text:
                return jsonify({"error": "Find text cannot be empty."}), 400

            count = (
                replace_all_text(document, find_text, replace_text_value)
                if replace_all
                else replace_text(document, find_text, replace_text_value)
            )
            save_document(document, session["editor_document_path"])
            return jsonify({"success": True, "count": count})

        if action == "paragraph":
            paragraph_action = data.get("paragraph_action")
            paragraph_index = int(data.get("paragraph_index", -1))

            if paragraph_action == "update":
                text = data.get("text", "")
                update_paragraph(document, paragraph_index, new_text=text)
            elif paragraph_action == "add":
                text = data.get("text", "")
                add_paragraph(document, text=text)
            elif paragraph_action == "delete":
                delete_paragraph(document, paragraph_index)
            elif paragraph_action == "format":
                paragraph = document.paragraphs[paragraph_index]
                font_size = data.get("font_size")
                font_name = data.get("font_name")
                alignment = data.get("alignment")
                bold = data.get("bold")
                italic = data.get("italic")
                underline = data.get("underline")

                if font_size is not None:
                    try:
                        font_size = Pt(float(font_size))
                    except (TypeError, ValueError):
                        font_size = None

                if alignment is not None:
                    alignment = str(alignment).lower()

                format_paragraph(
                    paragraph,
                    bold=bold if bold is not None else None,
                    italic=italic if italic is not None else None,
                    underline=underline if underline is not None else None,
                    font_name=font_name,
                    font_size=font_size,
                    alignment=alignment,
                )
            else:
                return jsonify({"error": "Unsupported paragraph action."}), 400

            save_document(document, session["editor_document_path"])
            return jsonify({"success": True, "document": _serialize_document(document)})

        if action == "table":
            table_action = data.get("table_action")
            table_index = int(data.get("table_index", -1))

            if table_action == "update_cell":
                row_index = int(data.get("row_index", -1))
                cell_index = int(data.get("cell_index", -1))
                new_text = str(data.get("text", ""))
                update_table_cell(document, table_index, row_index, cell_index, new_text)
            elif table_action == "add_row":
                values = data.get("values") or []
                add_table_row(document, table_index, values)
            elif table_action == "delete_row":
                row_index = int(data.get("row_index", -1))
                delete_table_row(document, table_index, row_index)
            elif table_action == "add_column":
                values = data.get("values") or []
                add_table_column(document, table_index, values)
            elif table_action == "delete_column":
                column_index = int(data.get("column_index", -1))
                delete_table_column(document, table_index, column_index)
            else:
                return jsonify({"error": "Unsupported table action."}), 400

            save_document(document, session["editor_document_path"])
            return jsonify({"success": True, "document": _serialize_document(document)})

        return jsonify({"error": "Unsupported editor action."}), 400

    except (IndexError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Editor action failed")
        return jsonify({"error": "The requested document change could not be applied."}), 500


@app.route("/editor/save", methods=["POST"])
def editor_save():
    document_path = session.get("editor_document_path")
    if not document_path or not os.path.exists(document_path):
        return jsonify({"error": "No document is open in the editor."}), 404

    try:
        document = Document(document_path)
        save_document(document, document_path)
        return jsonify({"success": True, "filename": session.get("editor_document_name", "document.docx")})
    except Exception:
        app.logger.exception("Saving document failed")
        return jsonify({"error": "The document could not be saved."}), 500


@app.route("/editor/download")
def editor_download():
    document_path = session.get("editor_document_path")
    if not document_path or not os.path.exists(document_path):
        return "Document not found.", 404

    filename = session.get("editor_document_name", "document.docx")
    return send_file(document_path, as_attachment=True, download_name=filename)


@app.route("/api/editor/upload", methods=["POST"])
def api_editor_upload():
    uploaded_file = request.files.get("file")
    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify({"error": "Please select a DOCX file."}), 400

    filename = secure_filename(uploaded_file.filename)
    if not filename or not filename.lower().endswith(".docx"):
        return jsonify({"error": "Please upload a valid DOCX file."}), 400

    session_dir = EDITOR_FOLDER / uuid.uuid4().hex
    session_dir.mkdir(parents=True, exist_ok=True)
    document_path = session_dir / filename

    try:
        uploaded_file.save(str(document_path))
        record = _create_editor_session(str(document_path), filename)
        payload = _render_editor_payload(str(document_path), filename)
        payload["token"] = record["token"]
        payload["success"] = True
        return jsonify(payload)
    except Exception:
        app.logger.exception("API editor upload failed")
        return jsonify({"error": "The uploaded file could not be opened as a valid DOCX document."}), 400


@app.route("/api/editor/document", methods=["GET"])
def api_editor_document():
    try:
        token = _editor_token_from_request()
        _, document_path = _editor_document_record(token)
        payload = _render_editor_payload(document_path, _read_session_record(token)["filename"])
        return jsonify({"filename": payload["filename"], "document": payload["document"]})
    except EditorSessionError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception:
        app.logger.exception("Loading editor document failed")
        return jsonify({"error": "The document could not be loaded."}), 500


@app.route("/api/editor/action", methods=["POST"])
def api_editor_action():
    data = request.get_json(silent=True) or {}

    try:
        token = _editor_token_from_request()
        record, document_path = _editor_document_record(token)
        document = Document(document_path)
    except EditorSessionError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception:
        return jsonify({"error": "No document is open."}), 404

    action = data.get("action")

    try:
        if action == "replace":
            find_text = data.get("find_text", "")
            replace_text_value = data.get("replace_text", "")
            replace_all = bool(data.get("replace_all", False))

            if not find_text:
                return jsonify({"error": "Find text cannot be empty."}), 400

            count = replace_all_text(document, find_text, replace_text_value) if replace_all else replace_text(document, find_text, replace_text_value)
            save_document(document, document_path)
            return jsonify({"success": True, "count": count})

        if action == "paragraph":
            paragraph_action = data.get("paragraph_action")
            paragraph_index = int(data.get("paragraph_index", -1))

            if paragraph_action == "update":
                update_paragraph(document, paragraph_index, new_text=data.get("text", ""))
            elif paragraph_action == "add":
                add_paragraph(document, text=data.get("text", ""))
            elif paragraph_action == "delete":
                delete_paragraph(document, paragraph_index)
            elif paragraph_action == "format":
                paragraph = document.paragraphs[paragraph_index]
                font_size = data.get("font_size")
                font_name = data.get("font_name")
                alignment = data.get("alignment")
                bold = data.get("bold")
                italic = data.get("italic")
                underline = data.get("underline")

                if font_size is not None:
                    try:
                        font_size = Pt(float(font_size))
                    except (TypeError, ValueError):
                        font_size = None

                if alignment is not None:
                    alignment = str(alignment).lower()

                format_paragraph(
                    paragraph,
                    bold=bold if bold is not None else None,
                    italic=italic if italic is not None else None,
                    underline=underline if underline is not None else None,
                    font_name=font_name,
                    font_size=font_size,
                    alignment=alignment,
                )
            else:
                return jsonify({"error": "Unsupported paragraph action."}), 400

            save_document(document, document_path)
            return jsonify({"success": True, "document": _serialize_document(document)})

        if action == "table":
            table_action = data.get("table_action")
            table_index = int(data.get("table_index", -1))

            if table_action == "update_cell":
                update_table_cell(document, table_index, int(data.get("row_index", -1)), int(data.get("cell_index", -1)), str(data.get("text", "")))
            elif table_action == "add_row":
                add_table_row(document, table_index, data.get("values") or [])
            elif table_action == "delete_row":
                delete_table_row(document, table_index, int(data.get("row_index", -1)))
            elif table_action == "add_column":
                add_table_column(document, table_index, data.get("values") or [])
            elif table_action == "delete_column":
                delete_table_column(document, table_index, int(data.get("column_index", -1)))
            else:
                return jsonify({"error": "Unsupported table action."}), 400

            save_document(document, document_path)
            return jsonify({"success": True, "document": _serialize_document(document)})

        return jsonify({"error": "Unsupported editor action."}), 400
    except (IndexError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("API editor action failed")
        return jsonify({"error": "The requested document change could not be applied."}), 500


@app.route("/api/editor/save", methods=["POST"])
def api_editor_save():
    try:
        token = _editor_token_from_request()
        _, document_path = _editor_document_record(token)
        document = Document(document_path)
        save_document(document, document_path)
        return jsonify({"success": True, "filename": _read_session_record(token)["filename"]})
    except EditorSessionError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception:
        app.logger.exception("API editor save failed")
        return jsonify({"error": "The document could not be saved."}), 500


@app.route("/api/editor/download")
def api_editor_download():
    try:
        token = _editor_token_from_request()
        _, document_path = _editor_document_record(token)
        filename = _read_session_record(token)["filename"]
        return send_file(document_path, as_attachment=True, download_name=filename)
    except EditorSessionError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    except Exception:
        app.logger.exception("API editor download failed")
        return jsonify({"error": "The document could not be downloaded."}), 500


@app.route("/convert/pdf-to-word", methods=["POST"])
def pdf_to_word():
    uploaded_file = request.files.get("pdf_file")

    if uploaded_file is None or uploaded_file.filename == "":
        return "Please select a PDF file.", 400

    filename = secure_filename(uploaded_file.filename)

    if not filename.lower().endswith(".pdf"):
        return "Please upload a PDF file.", 400

    header = uploaded_file.stream.read(1024)
    if b"%PDF" not in header:
        return "The uploaded file is not a valid PDF.", 400
    uploaded_file.stream.seek(0)

    unique_id = uuid.uuid4().hex
    pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}_{filename}")
    word_filename = f"{os.path.splitext(filename)[0]}.docx"
    word_path = os.path.join(CONVERTED_FOLDER, f"{unique_id}.docx")

    uploaded_file.save(pdf_path)

    try:
        convert_pdf_to_word(pdf_path, word_path)
        return send_file(word_path, as_attachment=True, download_name=word_filename)
    except Exception:
        app.logger.exception("PDF-to-Word conversion failed")
        return "Conversion failed. Please try another PDF file.", 500


@app.route("/api/convert/pdf-to-word", methods=["POST"])
def api_pdf_to_word():
    return pdf_to_word()


@app.route("/convert/pdf-to-images", methods=["POST"])
def pdf_to_images():
    uploaded_file = request.files.get("pdf_file")

    if uploaded_file is None or uploaded_file.filename == "":
        return "Please select a PDF file.", 400

    filename = secure_filename(uploaded_file.filename)
    if not filename.lower().endswith(".pdf"):
        return "Please upload a PDF file.", 400

    header = uploaded_file.stream.read(1024)
    if b"%PDF-" not in header:
        return "The uploaded file does not appear to be a valid PDF.", 400
    uploaded_file.stream.seek(0)

    unique_id = uuid.uuid4().hex
    pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}_{filename}")
    image_folder = os.path.join(CONVERTED_FOLDER, unique_id)
    zip_path = os.path.join(CONVERTED_FOLDER, f"{unique_id}.zip")

    uploaded_file.save(pdf_path)

    try:
        convert_pdf_to_images(pdf_path, image_folder)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for image_name in os.listdir(image_folder):
                zip_file.write(os.path.join(image_folder, image_name), arcname=image_name)
        return send_file(zip_path, as_attachment=True, download_name=f"{os.path.splitext(filename)[0]}_images.zip")
    except Exception:
        app.logger.exception("PDF-to-Images conversion failed.")
        return "Conversion failed. Please try another PDF file.", 500


@app.route("/api/convert/pdf-to-images", methods=["POST"])
def api_pdf_to_images():
    return pdf_to_images()


@app.route("/convert/word-to-pdf", methods=["POST"])
def word_to_pdf():
    uploaded_file = request.files.get("word_file")

    if uploaded_file is None or uploaded_file.filename == "":
        return "Please select a Word document.", 400

    filename = secure_filename(uploaded_file.filename)
    if not filename.lower().endswith((".docx", ".doc")):
        return "Please upload a Word document.", 400

    unique_id = uuid.uuid4().hex
    word_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}_{filename}")
    output_folder = os.path.join(CONVERTED_FOLDER, unique_id)

    uploaded_file.save(word_path)

    try:
        pdf_path = convert_word_to_pdf(word_path, output_folder)
        return send_file(pdf_path, as_attachment=True, download_name=f"{os.path.splitext(filename)[0]}.pdf")
    except Exception:
        app.logger.exception("Word-to-PDF conversion failed.")
        return "Conversion failed. Please try another Word document.", 500


@app.route("/api/convert/word-to-pdf", methods=["POST"])
def api_word_to_pdf():
    return word_to_pdf()


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.route("/api/db/health")
def api_db_health():
    status = database_status()
    return jsonify(status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)