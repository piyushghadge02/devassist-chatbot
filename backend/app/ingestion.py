import io
from pathlib import Path
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
def validate_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext or '(none)'}'. Allowed: .txt, .md, .pdf")
    return ext
def extract_text(filename: str, data: bytes) -> str:
    ext = validate_extension(filename)
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return data.decode("utf-8", errors="ignore")
