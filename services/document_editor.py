import os
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.table import Table
from docx.text.paragraph import Paragraph


def _as_string_path(path):
    return str(path) if path is not None else ""


def _validate_document(document):
    if document is None:
        raise ValueError("A Word document object is required.")

    return document


def _paragraph_text(paragraph):
    if paragraph is None:
        return ""
    return "".join(run.text for run in paragraph.runs)


def _find_occurrences(text, target, replace_all):
    if target is None or target == "":
        raise ValueError("Search text cannot be empty.")

    occurrences = []
    start = 0

    while True:
        index = text.find(target, start)
        if index == -1:
            break

        occurrences.append((index, index + len(target)))
        if not replace_all:
            break
        start = index + 1

    return occurrences


def _apply_single_text_replacement(paragraph, old_text, new_text):
    if paragraph is None:
        return 0

    runs = list(paragraph.runs)
    combined_text = "".join(run.text for run in runs)
    index = combined_text.find(old_text)

    if index == -1:
        return 0

    end_index = index + len(old_text)
    cursor = 0
    replacement_done = False

    for run in runs:
        run_text = run.text
        run_start = cursor
        run_end = run_start + len(run_text)

        if run_end <= index:
            cursor = run_end
            continue

        if run_start >= end_index:
            break

        leading = run_text[: max(0, index - run_start)] if run_start < index else ""
        trailing = run_text[max(0, end_index - run_start):] if run_end > end_index else ""

        if not replacement_done:
            run.text = leading + new_text + trailing
            replacement_done = True
        elif run_end > end_index:
            run.text = trailing
        else:
            run.text = ""

        cursor = run_end

    return 1


def read_document(file_path):
    """Read a DOCX document and return its paragraph/table structure in order.

    Args:
        file_path (str | os.PathLike): Path to the Word document.

    Returns:
        list[dict]: Ordered list containing paragraph and table entries.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the path is invalid or the file is not a DOCX document.
    """
    if file_path is None:
        raise ValueError("Document path is required.")

    file_path = str(file_path)

    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Document not found: {file_path}")

    if not file_path.lower().endswith(".docx"):
        raise ValueError("Only DOCX files are supported.")

    try:
        document = Document(file_path)
    except Exception as exc:  # pragma: no cover - preserves clear failure path
        raise ValueError(f"Unable to read DOCX document: {file_path}") from exc

    content = []

    for element in document.element.body:
        if element.tag.endswith("}p"):
            paragraph = Paragraph(element, document)
            content.append({
                "type": "paragraph",
                "style": paragraph.style.name if paragraph.style else None,
                "alignment": str(paragraph.alignment),
                "paragraph": read_paragraph_runs(paragraph),
            })
        elif element.tag.endswith("}tbl"):
            table = Table(element, document)
            table_data = []

            for row in table.rows:
                row_data = [cell.text for cell in row.cells]
                table_data.append(row_data)

            content.append({
                "type": "table",
                "data": table_data,
            })

    return content


def read_paragraph_runs(paragraph):
    """Return the text runs for a paragraph with basic formatting metadata."""
    paragraph = paragraph if paragraph is not None else Paragraph()
    runs = []

    for run in paragraph.runs:
        runs.append({
            "text": run.text,
            "bold": run.bold,
            "italic": run.italic,
            "underline": run.underline,
            "font_name": run.font.name,
            "font_size": run.font.size.pt if run.font.size else None,
        })

    return runs


def get_all_paragraphs(document):
    """Return every paragraph in the document, including table-cell paragraphs."""
    _validate_document(document)
    paragraphs = list(document.paragraphs)

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)

    return paragraphs


def replace_text(document, old_text, new_text, replace_all=False):
    """Replace text in document paragraphs and table cells.

    Args:
        document (Document): The document object to edit.
        old_text (str): Text to search for.
        new_text (str): Replacement text.
        replace_all (bool): When True, replace every occurrence.

    Returns:
        int: Number of replacements made.

    Raises:
        ValueError: If the search text is empty.
    """
    _validate_document(document)

    if old_text is None or old_text == "":
        raise ValueError("Search text cannot be empty.")

    replacements = 0

    for paragraph in get_all_paragraphs(document):
        while True:
            count = _apply_single_text_replacement(paragraph, old_text, new_text)
            if count == 0:
                break

            replacements += 1
            if not replace_all:
                break

    return replacements


def replace_all_text(document, old_text, new_text):
    """Replace every matching occurrence of text in the document."""
    return replace_text(document, old_text, new_text, replace_all=True)


def replace_paragraph(document, paragraph_index, new_text):
    """Replace the text of a paragraph by index.

    Returns:
        bool: True when the paragraph was updated, False when the index is invalid.
    """
    _validate_document(document)

    if paragraph_index is None or paragraph_index < 0 or paragraph_index >= len(document.paragraphs):
        return False

    document.paragraphs[paragraph_index].text = new_text or ""
    return True


def add_paragraph(document, text="", style=None, alignment=None, position=None):
    """Add a paragraph to the document at a chosen location.

    Args:
        document (Document): Target document.
        text (str): Paragraph content.
        style (str | None): Optional style name.
        alignment (str | object | None): Optional alignment value.
        position (int | None): Optional insertion index.

    Returns:
        Paragraph: The created paragraph.
    """
    _validate_document(document)

    if position is None or position < 0 or position > len(document.paragraphs):
        paragraph = document.add_paragraph(text or "")
    else:
        paragraphs = document.paragraphs
        insertion = document.add_paragraph(text or "")
        paragraph = insertion

        if position < len(paragraphs):
            paragraph._p.addprevious(paragraphs[position]._p)

    if style:
        try:
            paragraph.style = style
        except Exception:
            pass

    if alignment is not None:
        try:
            mapping = {
                "left": WD_ALIGN_PARAGRAPH.LEFT,
                "center": WD_ALIGN_PARAGRAPH.CENTER,
                "right": WD_ALIGN_PARAGRAPH.RIGHT,
                "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                "distributed": WD_ALIGN_PARAGRAPH.DISTRIBUTED,
            }
            if isinstance(alignment, str):
                paragraph.alignment = mapping.get(alignment.lower(), paragraph.alignment)
            else:
                paragraph.alignment = alignment
        except Exception:
            pass

    return paragraph


def delete_paragraph(document, paragraph_index):
    """Delete a paragraph by index and return True when removed."""
    _validate_document(document)

    if paragraph_index is None or paragraph_index < 0 or paragraph_index >= len(document.paragraphs):
        return False

    paragraph = document.paragraphs[paragraph_index]
    paragraph._p.getparent().remove(paragraph._p)
    return True


def update_paragraph(document, paragraph_index, new_text=None, style=None, alignment=None):
    """Update paragraph content and optionally its style/alignment."""
    _validate_document(document)

    if paragraph_index is None or paragraph_index < 0 or paragraph_index >= len(document.paragraphs):
        return False

    paragraph = document.paragraphs[paragraph_index]

    if new_text is not None:
        paragraph.text = new_text

    if style:
        try:
            paragraph.style = style
        except Exception:
            pass

    if alignment is not None:
        try:
            mapping = {
                "left": WD_ALIGN_PARAGRAPH.LEFT,
                "center": WD_ALIGN_PARAGRAPH.CENTER,
                "right": WD_ALIGN_PARAGRAPH.RIGHT,
                "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
                "distributed": WD_ALIGN_PARAGRAPH.DISTRIBUTED,
            }
            if isinstance(alignment, str):
                paragraph.alignment = mapping.get(alignment.lower(), paragraph.alignment)
            else:
                paragraph.alignment = alignment
        except Exception:
            pass

    return True


def set_paragraph_alignment(document, paragraph_index, alignment):
    """Set the alignment for a paragraph by index."""
    return update_paragraph(document, paragraph_index, alignment=alignment)


def set_paragraph_style(document, paragraph_index, style_name):
    """Set the paragraph style by index if the style exists."""
    return update_paragraph(document, paragraph_index, style=style_name)


def format_paragraph(paragraph, bold=None, italic=None, underline=None, font_name=None, font_size=None, alignment=None):
    """Apply formatting settings to every run in a paragraph."""
    if paragraph is None:
        raise ValueError("Paragraph instance is required.")

    for run in paragraph.runs:
        if bold is not None:
            run.bold = bold
        if italic is not None:
            run.italic = italic
        if underline is not None:
            run.underline = underline
        if font_name is not None:
            run.font.name = font_name
        if font_size is not None:
            try:
                run.font.size = font_size
            except Exception:
                pass

    if alignment is not None:
        mapping = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "distributed": WD_ALIGN_PARAGRAPH.DISTRIBUTED,
        }
        if isinstance(alignment, str):
            paragraph.alignment = mapping.get(alignment.lower(), paragraph.alignment)
        else:
            paragraph.alignment = alignment

    return True


def get_table_contents(document, table_index):
    """Return the rows and cells for a table by index."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]
    return [[cell.text for cell in row.cells] for row in table.rows]


def update_table_cell(document, table_index, row_index, cell_index, new_text):
    """Update a single cell value in a table."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]

    if row_index is None or row_index < 0 or row_index >= len(table.rows):
        raise IndexError(f"Row index out of range: {row_index}")

    if cell_index is None or cell_index < 0 or cell_index >= len(table.rows[row_index].cells):
        raise IndexError(f"Cell index out of range: {cell_index}")

    table.rows[row_index].cells[cell_index].text = new_text or ""
    return True


def add_table_row(document, table_index, values=None):
    """Append a row to the selected table."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]
    row = table.add_row().cells

    if values:
        for index, value in enumerate(values[:len(row)]):
            row[index].text = str(value)

    return row


def delete_table_row(document, table_index, row_index):
    """Delete a row in the selected table."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]

    if row_index is None or row_index < 0 or row_index >= len(table.rows):
        raise IndexError(f"Row index out of range: {row_index}")

    if len(table.rows) == 1:
        raise ValueError("A table must contain at least one row.")

    table._tbl.remove(table.rows[row_index]._tr)
    return True


def add_table_column(document, table_index, values=None):
    """Append a column to the selected table."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]
    for row in table.rows:
        row.cells.add()

    if values:
        for index, value in enumerate(values[:len(table.rows)]):
            table.rows[index].cells[-1].text = str(value)

    return len(table.columns)


def delete_table_column(document, table_index, column_index):
    """Delete a column from the selected table where supported."""
    _validate_document(document)

    if table_index is None or table_index < 0 or table_index >= len(document.tables):
        raise IndexError(f"Table index out of range: {table_index}")

    table = document.tables[table_index]

    if column_index is None or column_index < 0 or column_index >= len(table.columns):
        raise IndexError(f"Column index out of range: {column_index}")

    if len(table.columns) == 1:
        raise ValueError("A table must contain at least one column.")

    for row in table.rows:
        cell = row.cells[column_index]
        row._tr.remove(cell._tc)

    return True


def save_document(document, output_path):
    """Save a document to a file path while preserving the existing document content."""
    _validate_document(document)

    if output_path is None or _as_string_path(output_path).strip() == "":
        raise ValueError("An output path is required.")

    output_path = Path(output_path)

    if output_path.parent and not output_path.parent.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        document.save(str(output_path))
    except Exception as exc:  # pragma: no cover - keep save failures explicit
        raise OSError(f"Failed to save document to '{output_path}'") from exc

    return True
