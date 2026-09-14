"""Test that /api/files returns the stored PDF bytes with application/pdf content-type."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://openfiber-notes.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
SAMPLE_PDF = "/tmp/sample.pdf"


def test_files_returns_pdf_bytes():
    # Upload sample pdf via parser to obtain a valid pdf_storage_path
    with open(SAMPLE_PDF, "rb") as f:
        r = requests.post(f"{API}/pdf/parse",
                          files={"file": ("sample.pdf", f, "application/pdf")},
                          timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    pdf_path = data.get("pdf_storage_path")
    created_ids = [n["id"] for n in data.get("notes", [])]
    try:
        assert pdf_path, "pdf_storage_path missing"

        # Fetch via /api/files
        rf = requests.get(f"{API}/files", params={"path": pdf_path}, timeout=60)
        assert rf.status_code == 200
        assert rf.headers.get("content-type", "").startswith("application/pdf")
        assert rf.content[:4] == b"%PDF"
        assert len(rf.content) > 1000
    finally:
        if created_ids:
            requests.post(f"{API}/notes/bulk-delete", json={"ids": created_ids}, timeout=30)


def test_files_unknown_path_returns_404():
    r = requests.get(f"{API}/files", params={"path": "openfiber-notes/pdfs/does-not-exist.pdf"}, timeout=30)
    assert r.status_code == 404
