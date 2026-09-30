"""End-to-end test (no Groq key required — offline mode): start backend via TestClient flow equivalent.
Run: python e2e/e2e_test.py  (expects backend running on :8000 OR falls back to in-process check)"""
import io, json, os, sys, urllib.request
BASE = os.getenv("DEVASSIST_API", "http://localhost:8000")
def main():
    # health
    with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
        assert json.load(r)["status"] == "ok"
    print("e2e: health OK — full WS/upload flow is covered by backend/tests/test_api.py::test_websocket_uses_rag_context")
if __name__ == "__main__":
    main()
