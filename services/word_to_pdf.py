import subprocess
import os

def convert_word_to_pdf(word_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    command = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_folder,
        word_path
    ]

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=120
    )

    pdf_filename = os.path.splitext(
        os.path.basename(word_path)
    )[0] +".pdf"

    pdf_path = os.path.join(output_folder,
                            pdf_filename)

    return pdf_path