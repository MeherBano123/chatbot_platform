import re
import json
from pypdf import PdfReader

def extract_structured_json(pdf_path):
    reader = PdfReader(pdf_path)

    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    lines = full_text.split("\n")

    data = []
    current_heading = None
    current_subheading = None
    current_content = []

    for line in lines:
        line = line.strip()

        # Detect Chapter
        if re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):

            # Save previous block
            if current_heading and current_subheading and current_content:
                data.append({
                    "heading": current_heading,
                    "sub_heading": current_subheading,
                    "content": " ".join(current_content),
                    "meta_data": generate_metadata(current_heading, current_subheading)
                })

            current_heading = line
            current_subheading = None
            current_content = []

        # Detect Subheading like 9.3.1
        elif re.match(r'^\d+(\.\d+)+', line):

            # Save previous subheading block
            if current_heading and current_subheading and current_content:
                data.append({
                    "heading": current_heading,
                    "sub_heading": current_subheading,
                    "content": " ".join(current_content),
                    "meta_data": generate_metadata(current_heading, current_subheading)
                })

            current_subheading = line
            current_content = []

        else:
            if line:
                current_content.append(line)

    # ✅ FIX: SAVE LAST BLOCK AFTER LOOP ENDS
    if current_heading and current_subheading and current_content:
        data.append({
            "heading": current_heading,
            "sub_heading": current_subheading,
            "content": " ".join(current_content),
            "meta_data": generate_metadata(current_heading, current_subheading)
        })

    return data


def generate_metadata(heading, sub_heading):
    text = (heading + " " + sub_heading).lower()

    keywords = []
    if "web" in text:
        keywords.append("web app")
    if "mobile" in text:
        keywords.append("mobile app")
    if "crm" in text:
        keywords.append("crm")
    if "password" in text:
        keywords.append("authentication")
    if "dashboard" in text:
        keywords.append("dashboard")

    return ", ".join(keywords)

data = extract_structured_json("EPay-Balochistan-User_Guide_my_copy.pdf")

with open("structured_output_epayBalochistan.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)