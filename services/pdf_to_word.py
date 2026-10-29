from pdf2docx import Converter

def convert_pdf_to_word(pdf_path, word_path):
    converter = Converter(pdf_path)

    try:
        converter.convert(word_path)
    finally:
        converter.close()