import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except Exception:
    pass

class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama3-70b-8192")
    embedding_backend: str = os.getenv("EMBEDDING_BACKEND", "auto")  # auto|hash|sentence-transformers
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", str(5 * 1024 * 1024)))
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3
    max_context_chars: int = 12000  # ~ <4000 tokens, SRS 5.2
    cors_origins: list = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

settings = Settings()
