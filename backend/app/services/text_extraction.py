from pathlib import Path

from pypdf import PdfReader


class UnsupportedFileTypeError(Exception):
    pass


def extract_text(file_path: str, filename: str) -> str:
    """
    Extracts plain text from an uploaded document. Supports .txt, .md, and
    .pdf. Add new formats here rather than scattering file-type checks
    elsewhere -- ingestion should have exactly one place that knows how to
    read a file.
    """
    suffix = Path(filename).suffix.lower()

    if suffix in (".txt", ".md"):
        with open(file_path, encoding="utf-8", errors="replace") as f:
            return f.read()

    if suffix == ".pdf":
        reader = PdfReader(file_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
        return "\n\n".join(pages_text)

    raise UnsupportedFileTypeError(
        f"Unsupported file type '{suffix}'. Supported: .txt, .md, .pdf"
    )
