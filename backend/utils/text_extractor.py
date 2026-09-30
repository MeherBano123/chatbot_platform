# import PyPDF2
import docx
import os
from PyPDF2 import PdfReader
import re
import docx


def extract_text_from_pdf(file_path: str):
    """
    Extract text from a PDF per page using pypdf.

    Returns:
        [
            {"page_number": 1, "content": "..."},
            {"page_number": 2, "content": "..."}
        ]
    """
    pages = []

    try:
        reader = PdfReader(file_path)

        for i, page in enumerate(reader.pages):
            text = page.extract_text()

            if text:
                # Clean whitespace (replace newlines / multiple spaces with one space)
                text = re.sub(r'\s+', ' ', text).strip()

                pages.append({
                    "page_number": i + 1,
                    "content": text
                })

        print(f" Extracted {len(pages)} pages using pypdf")
        return pages

    except Exception as e:
        print(f" PDF extraction failed: {str(e)}")
        raise

def extract_text_from_docx(path):
    doc = docx.Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_txt(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}    
def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS