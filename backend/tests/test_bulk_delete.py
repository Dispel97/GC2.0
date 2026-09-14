"""Tests for the new bulk-delete endpoint."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://openfiber-notes.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
SAMPLE_PDF = "/tmp/sample.pdf"


def _upload_notes():
    with open(SAMPLE_PDF, "rb") as f:
        r = requests.post(f"{API}/pdf/parse", files={"file": ("sample.pdf", f, "application/pdf")}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["notes"]


def test_bulk_delete_empty_ids():
    r = requests.post(f"{API}/notes/bulk-delete", json={"ids": []}, timeout=30)
    assert r.status_code == 200
    assert r.json() == {"deleted": 0}


def test_bulk_delete_removes_notes():
    # baseline count
    before = len(requests.get(f"{API}/notes").json())
    created = _upload_notes()
    assert len(created) >= 3, f"Need at least 3 notes; got {len(created)}"
    ids_to_delete = [n["id"] for n in created[:2]]

    r = requests.post(f"{API}/notes/bulk-delete", json={"ids": ids_to_delete}, timeout=30)
    assert r.status_code == 200
    assert r.json()["deleted"] == 2

    after = len(requests.get(f"{API}/notes").json())
    assert after == before + len(created) - 2

    # verify actual ids are gone
    all_ids = {n["id"] for n in requests.get(f"{API}/notes").json()}
    for did in ids_to_delete:
        assert did not in all_ids

    # cleanup remaining created notes
    remaining = [n["id"] for n in created[2:]]
    if remaining:
        requests.post(f"{API}/notes/bulk-delete", json={"ids": remaining}, timeout=30)


def test_bulk_delete_unknown_ids():
    r = requests.post(f"{API}/notes/bulk-delete", json={"ids": ["nonexistent-1", "nonexistent-2"]}, timeout=30)
    assert r.status_code == 200
    assert r.json()["deleted"] == 0
