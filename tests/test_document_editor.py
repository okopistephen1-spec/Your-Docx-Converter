from docx import Document
from services.document_editor import replace_text, replace_paragraph



# Create a sample Word document
document = Document()

paragraph = document.add_paragraph()

paragraph.add_run("Welcome ")
paragraph.add_run("to Your-")
paragraph.add_run("Docx-Converter")

document.save("sample.docx")


# Test the replacement function
document = Document("sample.docx")
# Test paragraph replacement

document = Document()

document.add_paragraph(
    "Welcome to Your-Docx-Converter. We make document conversion easy."
)

replace_paragraph(
    document,
    0,
    "Your-Docx-Converter helps you convert and edit documents."
)

document.save("paragraph_test.docx")

# Verify the replacement

check_document = Document("paragraph_test.docx")

for paragraph in check_document.paragraphs:
    print(paragraph.text)
replace_text(document, "Your-Docx", "My-Docx")

document.save("edited_sample.docx")

