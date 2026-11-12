import shutil

import pytest
from docx import Document

from services.word_to_pdf import convert_word_to_pdf


def _libreoffice_available():
    return any(shutil.which(command) for command in ("libreoffice", "soffice"))


@pytest.mark.requires_render
@pytest.mark.skipif(
    not _libreoffice_available(),
    reason="LibreOffice/soffice is not installed in this local environment; this test requires the Render runtime.",
)
def test_word_to_pdf_requires_render_runtime(tmp_path):
    source_path = tmp_path / "render_test.docx"
    output_dir = tmp_path / "converted"
    output_dir.mkdir()

    document = Document()
    document.add_paragraph("Render runtime conversion test")
    document.save(source_path)

    pdf_path = convert_word_to_pdf(str(source_path), str(output_dir))

    assert pdf_path
    assert str(pdf_path).endswith(".pdf")