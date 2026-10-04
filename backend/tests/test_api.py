import io, os, sys
os.environ["EMBEDDING_BACKEND"] = "hash"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# config is read at import; force hash backend before app import
import app.config as cfg
cfg.settings.embedding_backend = "hash"
from fastapi.testclient import TestClient
from pypdf import PdfWriter
import app.main as main_module
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

def test_delete_single_document_removes_only_its_chunks():
    a = client.post("/upload", files={"file": ("alpha.txt", io.BytesIO(b"alpha doc "*40), "text/plain")})
    b = client.post("/upload", files={"file": ("beta.md", io.BytesIO(b"# Beta\n\nbeta doc "*40), "text/markdown")})
    assert a.status_code == 200 and b.status_code == 200
    n_a, n_b = a.json()["chunks_processed"], b.json()["chunks_processed"]
    assert len(store) == n_a + n_b

    r = client.delete("/documents/beta.md")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "removed" and body["filename"] == "beta.md"
    assert body["chunks_removed"] == n_b
    # only that document is gone; the other survives intact
    assert len(store) == n_a
    assert store.sources.count("alpha.txt") == n_a
    assert "beta.md" not in store.sources
    assert client.get("/documents").json()["files"] == {"alpha.txt": n_a}

def test_delete_document_handles_spaces_and_missing_file():
    up = client.post("/upload", files={"file": ("my notes v1.md", io.BytesIO(b"# notes\n\n"*40), "text/markdown")})
    assert up.status_code == 200
    from urllib.parse import quote
    r = client.delete("/documents/" + quote("my notes v1.md"))
    assert r.status_code == 200 and r.json()["chunks_removed"] == up.json()["chunks_processed"]
    assert len(store) == 0
    # unknown document -> 404, and the index is untouched
    assert client.delete("/documents/never-indexed.txt").status_code == 404
    assert len(store) == 0

def test_delete_single_document_still_serves_retrieval():
    client.post("/upload", files={"file": ("keep.txt", io.BytesIO(b"keep me "*40), "text/plain")})
    client.post("/upload", files={"file": ("drop.txt", io.BytesIO(b"drop me "*40), "text/plain")})
    client.delete("/documents/drop.txt")
    hits = store.search(HashEmbedder().encode(["keep me"]), top_k=20)
    assert hits and all("drop me" not in h for h in hits), hits

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

def test_websocket_uses_rag_context(monkeypatch):
    """SRS 3.3/2.2: the question is answered WITH retrieved document context.

    Asserts the real contract — that top-k chunks retrieved from the vector store
    are injected into the system prompt handed to the model. It deliberately does
    NOT assert on the offline mock's canned wording, which a real model will never
    emit; the test must hold whether GROQ_API_KEY is set or not.
    """
    data = ("ZebraDB is a fictional database whose port is 9876 and driver is zebra-py. " * 10).encode()
    client.post("/upload", files={"file": ("z.txt", io.BytesIO(data), "text/plain")})
    assert len(store) > 0, "upload should have populated the vector store"

    captured = {}

    async def fake_stream_chat(messages, api_key, model):
        captured["messages"] = messages
        captured["api_key_present"] = bool(api_key)
        captured["model"] = model
        yield "ZebraDB uses port **9876**."

    monkeypatch.setattr(main_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "What port does ZebraDB use?", "document_id": "z.txt"})
        tokens = ""
        while True:
            msg = ws.receive_json()
            if msg.get("status") == "done":
                break
            tokens += msg.get("token", "")

    system_prompt = captured["messages"][0]["content"]
    assert "ZebraDB" in system_prompt, "retrieved document chunk missing from system prompt"
    assert "9876" in system_prompt, "retrieved document chunk missing from system prompt"
    # RAG context must be appended to the programming-only system prompt.
    assert "strictly answer questions related to software engineering" in system_prompt
    # The user turn is still the question, unmodified.
    assert captured["messages"][-1] == {"role": "user", "content": "What port does ZebraDB use?"}
    assert "9876" in tokens

def test_websocket_without_documents_sends_no_context(monkeypatch):
    """With an empty store the system prompt must be the bare guardrail prompt."""
    store.clear()
    captured = {}

    async def fake_stream_chat(messages, api_key, model):
        captured["messages"] = messages
        yield "ok"

    monkeypatch.setattr(main_module, "stream_chat", fake_stream_chat)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "What is Python?"})
        while True:
            if ws.receive_json().get("status") == "done":
                break
    assert captured["messages"][0]["content"] == SYSTEM_PROMPT

def test_retrieval_context_respects_char_cap(monkeypatch):
    """SRS 5.2: retrieved context stays under max_context_chars (<4000 tokens)."""
    big = ("ZebraDB supports high availability across regions. " * 400).encode()
    client.post("/upload", files={"file": ("big.txt", io.BytesIO(big), "text/plain")})
    captured = {}

    async def fake_stream_chat(messages, api_key, model):
        captured["messages"] = messages
        yield "ok"

    monkeypatch.setattr(main_module, "stream_chat", fake_stream_chat)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "Describe ZebraDB availability."})
        while True:
            if ws.receive_json().get("status") == "done":
                break
    system_prompt = captured["messages"][0]["content"]
    # everything after the fixed guardrail sentence is retrieved context
    context = system_prompt.split("Use the following retrieved document context if relevant:")[-1]
    assert len(context.strip()) <= cfg.settings.max_context_chars

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
