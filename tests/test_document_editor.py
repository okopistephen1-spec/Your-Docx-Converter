from docx import Document

from services.document_editor import add_paragraph, get_all_paragraphs, replace_text, save_document


def test_replace_text_updates_paragraphs_and_table_cells(tmp_path):
    document = Document()
    document.add_paragraph("Welcome to Your-Docx-Converter.")

    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Your-Docx"
    table.cell(0, 1).text = "Converter"

    file_path = tmp_path / "sample.docx"
    save_document(document, file_path)

    loaded_document = Document(file_path)
    replacements = replace_text(loaded_document, "Your-Docx", "My-Docx")

    assert replacements >= 1
    assert loaded_document.tables[0].cell(0, 0).text == "My-Docx"
    assert "Welcome to My-Docx-Converter." in [paragraph.text for paragraph in loaded_document.paragraphs]


def test_add_paragraph_keeps_document_content(tmp_path):
    document = Document()
    add_paragraph(document, "Alpha")
    add_paragraph(document, "Beta")

    file_path = tmp_path / "paragraphs.docx"
    save_document(document, file_path)

    loaded_document = Document(file_path)
    paragraph_texts = [paragraph.text for paragraph in loaded_document.paragraphs]

    assert "Alpha" in paragraph_texts
    assert "Beta" in paragraph_texts