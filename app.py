import os
import uuid
import zipfile

from docx import Document
from docx.shared import Pt
from flask import Flask, jsonify, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from services.document_editor import (
    add_paragraph,
    add_table_column,
    add_table_row,
    delete_paragraph,
    delete_table_column,
    delete_table_row,
    format_paragraph,
    read_document,
    replace_text,
    replace_all_text,
    save_document,
    update_paragraph,
    update_table_cell,
)
from services.pdf_to_image import convert_pdf_to_images
from services.pdf_to_word import convert_pdf_to_word
from services.word_to_pdf import convert_word_to_pdf

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "docx-converter-dev-secret")

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
CONVERTED_FOLDER = os.path.join(app.root_path, "converted")
EDITOR_FOLDER = os.path.join(UPLOAD_FOLDER, "editor")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)
os.makedirs(EDITOR_FOLDER, exist_ok=True)


def _get_or_create_editor_session_dir():
    session_id = session.get("editor_session_id")
    if not session_id:
        session_id = uuid.uuid4().hex
        session["editor_session_id"] = session_id

    session_dir = os.path.join(EDITOR_FOLDER, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


def _load_document_from_session():
    document_path = session.get("editor_document_path")
    if not document_path:
        raise FileNotFoundError("No document is currently open in the editor.")

    if not os.path.exists(document_path):
        raise FileNotFoundError("The current editor document could not be found.")

    return Document(document_path)


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

    session_dir = _get_or_create_editor_session_dir()
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    document_path = os.path.join(session_dir, unique_name)

    try:
        uploaded_file.save(document_path)
        session["editor_document_path"] = document_path
        session["editor_document_name"] = filename

        document = Document(document_path)
        payload = _serialize_document(document)
        return jsonify({
            "success": True,
            "filename": filename,
            "document": payload,
        })

    except Exception as exc:
        app.logger.exception("Editor upload failed")
        return jsonify({"error": "The uploaded file could not be opened as a valid DOCX document."}), 400


@app.route("/editor/document", methods=["GET"])
def editor_document():
    document_path = session.get("editor_document_path")
    if not document_path or not os.path.exists(document_path):
        return jsonify({"error": "No document is open."}), 404

    try:
        document = Document(document_path)
        return jsonify({
            "filename": session.get("editor_document_name", "document.docx"),
            "document": _serialize_document(document),
        })
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
    except Exception as exc:
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
        return "The uploaded files is not a valid PDF.", 400

    uploaded_file.stream.seek(0)

    unique_id = uuid.uuid4().hex
    pdf_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}_{filename}")

    word_filename = f"{os.path.splitext(filename)[0]}.docx"
    word_path = os.path.join(CONVERTED_FOLDER, f"{unique_id}.docx")

    uploaded_file.save(pdf_path)

    try:
        convert_pdf_to_word(pdf_path, word_path)

        return send_file(
            word_path,
            as_attachment=True,
            download_name=word_filename,
        )

    except Exception:
        app.logger.exception("PDF-to-Word conversion failed")
        return "Conversion failed. Please try another PDf file.", 500


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
                image_path = os.path.join(image_folder, image_name)
                zip_file.write(image_path, arcname=image_name)

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"{os.path.splitext(filename)[0]}_images.zip",
        )

    except Exception:
        app.logger.exception("PDF-to-Images conversion failed.")
        return "Conversion failed. Please try another PDF file.", 500


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

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"{os.path.splitext(filename)[0]}.pdf",
        )

    except Exception:
        app.logger.exception("Word-to-PDF conversion failed.")
        return "Conversion failed. Please try another Word document.", 500


if __name__ == "__main__":
    app.run(debug=True)