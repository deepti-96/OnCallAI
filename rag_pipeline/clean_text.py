import re

def clean_text(text: str) -> str:
    # Collapse multiple newlines and spaces
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing spaces
    return text.strip()
