"""Extract text from PDF bytes for Claude context injection."""
import io
from pypdf import PdfReader


def extract_text(pdf_bytes: bytes, max_chars: int = 60_000) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    total = 0
    for i, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        snippet = f"\n--- Page {i} ---\n{text}"
        if total + len(snippet) > max_chars:
            pages.append(snippet[: max_chars - total])
            break
        pages.append(snippet)
        total += len(snippet)
    return "".join(pages)


def page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
