import PyPDF2

def load_pdf(pdf_path: str) -> str:
    """Read a PDF and return extracted text."""
    text = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text
