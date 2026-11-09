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

def get_all_paragraphs(document):

    paragraphs = []

    for paragraph in document.paragraphs:
        paragraphs.append(paragraph)

    for table in document.tables:

        for row in table.rows:

            for cell in row.cells:

                for paragraph in cell.paragraphs:
                    paragraphs.append(paragraph)

    return paragraphs

def replace_text(document, old_text, new_text):

    if not old_text:
        return

    for paragraph in get_all_paragraphs(document):

        full_text = "".join(run.text for run in paragraph.runs)

        start_index = full_text.find(old_text)

        if start_index == -1:
            continue

        end_index = start_index + len(old_text)

        current_index = 0
        replacement_inserted = False

        for run in paragraph.runs:

            run_start = current_index
            run_end = current_index + len(run.text)

            overlap_start = max(start_index, run_start)
            overlap_end = min(end_index, run_end)

            if overlap_start < overlap_end:

                local_start = overlap_start - run_start
                local_end = overlap_end - run_start

                if not replacement_inserted:

                    run.text = (
                        run.text[:local_start]
                        + new_text
                        + run.text[local_end:]
                    )

                    replacement_inserted = True

                else:

                    run.text = (
                        run.text[:local_start]
                        + run.text[local_end:]
                    )

            current_index = run_end

        print("Found and replaced!")


def replace_paragraph(document, paragraph_index, new_text):

    if paragraph_index < 0 or paragraph_index >= len(document.paragraphs):
        return False

    paragraph = document.paragraphs[paragraph_index]

    paragraph.text = new_text

    return True


def save_document(document, output_path):
    document.save(output_path)

    return True