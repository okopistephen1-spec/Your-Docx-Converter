import os
import uuid
import zipfile


from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from services.pdf_to_image import convert_pdf_to_images

from services.pdf_to_word import convert_pdf_to_word
from services.word_to_pdf import convert_word_to_pdf

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
CONVERTED_FOLDER = os.path.join(app.root_path, "converted")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/converter")
def converter():
    return render_template("converter.html")

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
    pdf_path = os.path.join(
        UPLOAD_FOLDER, f"{unique_id}_{filename}"
    )

    word_filename = f"{os.path.splitext(filename)[0]}.docx"
    word_path = os.path.join(
        CONVERTED_FOLDER, f"{unique_id}.docx"
    )

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
            download_name=f"{os.path.splitext(filename)[0]}_images.zip"
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

    word_path = os.path.join(
        UPLOAD_FOLDER,
        f"{unique_id}_{filename}"
    )

    output_folder = os.path.join(
        CONVERTED_FOLDER,
        unique_id
    )

    uploaded_file.save(word_path)

    try:
        pdf_path = convert_word_to_pdf(word_path, output_folder)

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f"{os.path.splitext(filename)[0]}.pdf"
        )

    except Exception:
        app.logger.exception("Word-to-PDF conversion failed.")
        return "Conversion failed. Please try another Word document.", 500


if __name__ == "__main__":
    app.run(debug=True)