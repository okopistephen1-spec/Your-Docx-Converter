from services.word_to_pdf import convert_word_to_pdf

word_file = "uploads/test.docx"
output_folder = "converted/test"

pdf_file = convert_word_to_pdf(word_file, output_folder)

print("Conversion successful!")
print("PDF location:", pdf_file)