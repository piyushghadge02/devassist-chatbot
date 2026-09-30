import io, os, sys
os.environ["EMBEDDING_BACKEND"] = "hash"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# config is read at import; force hash backend before app import
import app.config as cfg
cfg.settings.embedding_backend = "hash"
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from app.main import app, store
from app.chunking import chunk_text
from app.prompts import SYSTEM_PROMPT, build_prompt, RATE_LIMIT_MESSAGE
from app.vector_store import VectorStore
from app.embeddings import HashEmbedder

client = TestClient(app)

def setup_function(): store.clear()

def test_health():
    r = client.get("/health"); assert r.status_code == 200; assert r.json()["status"] == "ok"

def test_chunking_srs_500_50():
    text = "a" * 1200
    chunks = chunk_text(text, 500, 50)
    assert chunks[0] == text[:500]
    # second chunk starts at 450 (500-50 overlap)
    assert chunks[1] == text[450:950]
    assert len(chunks) == 3

def test_chunking_empty(): assert chunk_text("  ") == []

def test_system_prompt_programming_only():
    assert "strictly answer questions related to software engineering" in SYSTEM_PROMPT
    assert "designed only for programming assistance" in SYSTEM_PROMPT
    msgs = build_prompt("hi", ["ctx chunk"])
    assert "ctx chunk" in msgs[0]["content"]

def test_upload_txt_and_retrieval_top3():
    data = ("Python functions are defined with the def keyword. " * 30).encode()
    r = client.post("/upload", files={"file": ("notes.txt", io.BytesIO(data), "text/plain")})
    assert r.status_code == 200, r.text
    body = r.json(); assert body["status"] == "success"; assert body["filename"] == "notes.txt"; assert body["chunks_processed"] >= 1
    emb = HashEmbedder(); store_results = store.search(emb.encode(["python function def"]), top_k=3)
    assert 1 <= len(store_results) <= 3

def test_upload_md():
    r = client.post("/upload", files={"file": ("a.md", io.BytesIO(b"# Title\n\nSome code docs "*20), "text/markdown")})
    assert r.status_code == 200 and r.json()["chunks_processed"] >= 1

def _make_pdf(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n"); offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out); out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets: out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)

def test_upload_pdf():
    raw = _make_pdf("FastAPI WebSocket streaming guide for developers")
    r = client.post("/upload", files={"file": ("doc.pdf", io.BytesIO(raw), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["chunks_processed"] >= 1

def test_upload_rejects_bad_extension():
    r = client.post("/upload", files={"file": ("x.exe", io.BytesIO(b"hi"), "application/octet-stream")})
    assert r.status_code == 400

def test_upload_rejects_oversize():
    big = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post("/upload", files={"file": ("big.txt", io.BytesIO(big), "text/plain")})
    assert r.status_code == 413

def test_websocket_streaming_and_done():
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "How do I write a Python function?"})
        tokens, done = "", False
        while not done:
            msg = ws.receive_json()
            if msg.get("status") == "done": done = True
            elif msg.get("status") == "streaming": tokens += msg.get("token", "")
            else: raise AssertionError(f"unexpected {msg}")
        assert "Python" in tokens or "programming" in tokens.lower() or "Offline" in tokens

def test_websocket_uses_rag_context():
    data = ("ZebraDB is a fictional database whose port is 9876 and driver is zebra-py. " * 10).encode()
    client.post("/upload", files={"file": ("z.txt", io.BytesIO(data), "text/plain")})
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "What port does ZebraDB use?"})
        tokens = ""
        while True:
            msg = ws.receive_json()
            if msg.get("status") == "done": break
            tokens += msg.get("token", "")
        # offline mock confirms context was retrieved/used
        assert "uploaded document context" in tokens

def test_websocket_empty_message_error():
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "  "})
        assert ws.receive_json()["status"] == "error"

def test_rate_limit_message_constant():
    assert RATE_LIMIT_MESSAGE == "Traffic is high. Please wait 10 seconds before asking again."

def test_vector_store_topk_limit():
    vs = VectorStore(); emb = HashEmbedder()
    texts = [f"topic {i} python code example {i}" for i in range(10)]
    vs.add(emb.encode(texts), texts, "t")
    assert len(vs.search(emb.encode(["python code"]), top_k=3)) == 3
