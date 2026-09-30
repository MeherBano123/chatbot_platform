import re
import json
from pypdf import PdfReader


def extract_pdf_text(pdf_path):
    """Extract full text from PDF."""
    reader = PdfReader(pdf_path)
    text = ""

    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"

    return text


def split_into_modules(text):
    """
    Split text into modules based on numbered headings.
    Removes section numbers from final heading.
    """

    # Pattern for headings like:
    # 4.2 Token Tax
    # 4.2.2 Professional Tax
    heading_pattern = r"\n\d+\.\d+(?:\.\d+)?\s+[A-Za-z &()/-]+"

    headings = re.findall(heading_pattern, text)
    sections = re.split(heading_pattern, text)

    modules = []

    for i in range(len(headings)):
        raw_heading = headings[i].strip()

        # Remove section number
        clean_heading = re.sub(r"^\d+\.\d+(?:\.\d+)?\s+", "", raw_heading)

        content = sections[i + 1].strip() if i + 1 < len(sections) else ""

        modules.append({
            "heading": clean_heading,
            "content": content,
            
        })

    return modules


def save_to_json(modules, output_file="epay_modules1.json"):
    """Save structured modules to JSON."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(modules, f, indent=4, ensure_ascii=False)


def main():
    pdf_path = "EPay-Balochistan-User Guide.pdf"  # Change if needed

    print("Extracting text...")
    text = extract_pdf_text(pdf_path)

    print("Splitting into modules...")
    modules = split_into_modules(text)

    print(f"Detected {len(modules)} modules.")

    print("Saving to JSON...")
    save_to_json(modules)

    print("Done! File saved as epay_modules1.json")


if __name__ == "__main__":
    main()