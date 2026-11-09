from docx import Document
from services.document_editor import (
    replace_text,
    replace_paragraph,
    save_document,
    get_all_paragraphs
)



# TEST A: Text replacement and saving

# Create a sample Word document
document = Document()

document.add_paragraph(
    "Welcome to Your-Docx-Converter."
)

# Save the original document
save_document(document, "sample.docx")

# Open the saved document
document = Document("sample.docx")

# Replace existing text
replace_text(
    document,
    "Your-Docx-Converter",
    "My Document Editor"
)

# Save the edited document
save_document(document, "edited_document.docx")

# Verify the edited document
check_document = Document("edited_document.docx")

for paragraph in check_document.paragraphs:
    print(paragraph.text)

    # TEST B: Retrieving paragraphs from tables

document = Document()

document.add_paragraph("This is outside the table.")

table = document.add_table(rows=1, cols=2)

table.cell(0, 0).text = "Your-Docx"
table.cell(0, 1).text = "Converter"

save_document(document, "table_test.docx")

# Open the saved document
document = Document("table_test.docx")

# Retrieve all paragraphs
paragraphs = get_all_paragraphs(document)

# Display the retrieved text
for paragraph in paragraphs:
    print(paragraph.text)

# TEST C: Replacing text inside a table

document = Document("table_test.docx")

replace_text(
    document,
    "Your-Docx",
    "My-Docx"
)

save_document(document, "table_edited.docx")

# Verify table replacement

check_document = Document("table_edited.docx")

for paragraph in get_all_paragraphs(check_document):
    print(paragraph.text)