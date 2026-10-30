from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

def read_document(file_path):
    document = Document(file_path)

    content = []

    for element in document.element.body:

        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, document)

            runs = read_paragraph_runs(paragraph)

            content.append({
                "type": "paragraph",
                "style": paragraph.style.name,
                "alignment": str(paragraph.alignment),
                "paragraph": runs
            })

        elif element.tag.endswith("}tbl"):
            table = Table(element, document)

            table_data = []

            for row in table.rows:
                row_data = []

                for cell in row.cells:
                    row_data.append(cell.text)

                table_data.append(row_data)

            content.append({
                "type": "table",
                "data": table_data
            })

    return content


def read_paragraph_runs(paragraph):
    runs = []

    for run in paragraph.runs:
        runs.append({
            "text": run.text,
            "bold": run.bold,
            "italic": run.italic,
            "underline": run.underline,
            "font_name": run.font.name,
            "font_size": run.font.size.pt if run.font.size else None
        })

    return runs

def replace_text(document, old_text, new_text):
    for paragraph in document.paragraphs:
        for run in paragraph.runs:

            if old_text in run.text:
                run.text = run.text.replace(old_text, new_text)
                print("Found and replaced!")