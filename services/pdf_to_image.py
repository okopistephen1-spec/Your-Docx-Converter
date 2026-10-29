import pymupdf
import os


def convert_pdf_to_images(pdf_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    pdf_document = pymupdf.open(pdf_path)

    try:
        for page_number, page in enumerate(pdf_document, start=1):
            pixmap = page.get_pixmap(dpi=150)

            image_path = os.path.join(
                output_folder,
                f"page_{page_number}.png"
            )

            pixmap.save(image_path)

    finally:
        pdf_document.close()