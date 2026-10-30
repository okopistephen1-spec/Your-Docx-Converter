from docx import Document
from services.document_editor import read_document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from services.document_editor import read_document, replace_text


# Create a sample Word document
document = Document()
document.add_heading("My First Heading", level=1)
paragraph = document.add_paragraph()
paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

table = document.add_table(rows=2, cols=2)

table.cell(0, 0).text = "Name"
table.cell(0, 1).text = "Subject"

table.cell(1, 0).text = "John"
table.cell(1, 1).text = "Mathematics"

run1 = paragraph.add_run("Welcome")
run1.font.size = 12
run1.font.name = "Arial"
run1.font.size = Pt(12)
run1.bold = True

paragraph.add_run(" to Your-Docx-Converter.")

document.save("sample.docx")


# Read the document
content = read_document("sample.docx")

print(content)

replace_text(document, "Welcome", "Hello")
document.save("edited_sample.docx")