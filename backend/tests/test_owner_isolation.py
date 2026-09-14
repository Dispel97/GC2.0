"""Backend tests for iteration 4: X-Owner-Key isolation + full note editability."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # fallback for local
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')

API = f"{BASE_URL}/api"
PDF_PATH = "/tmp/sample.pdf"

DEV_A = "DEV-A-iter4-test"
DEV_B = "DEV-B-iter4-test"


def _upload(owner):
    with open(PDF_PATH, "rb") as f:
        r = requests.post(f"{API}/pdf/parse", files={"file": ("sample.pdf", f, "application/pdf")},
                          headers={"X-Owner-Key": owner}, timeout=60)
    return r


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    # Cleanup after tests
    for owner in (DEV_A, DEV_B):
        r = requests.get(f"{API}/notes", headers={"X-Owner-Key": owner})
        if r.status_code == 200:
            ids = [n["id"] for n in r.json()]
            if ids:
                requests.post(f"{API}/notes/bulk-delete", json={"ids": ids},
                              headers={"X-Owner-Key": owner})


@pytest.fixture(scope="module")
def dev_a_notes():
    r = _upload(DEV_A)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def dev_b_notes():
    r = _upload(DEV_B)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_dev_a_creates_4_notes(dev_a_notes):
    assert dev_a_notes["created_count"] == 4
    for n in dev_a_notes["notes"]:
        assert n["owner_key"] == DEV_A
        assert n["wr"].isdigit()


def test_upload_dev_b_creates_4_notes(dev_b_notes):
    assert dev_b_notes["created_count"] == 4
    for n in dev_b_notes["notes"]:
        assert n["owner_key"] == DEV_B


def test_list_notes_isolation(dev_a_notes, dev_b_notes):
    a_ids = {n["id"] for n in dev_a_notes["notes"]}
    b_ids = {n["id"] for n in dev_b_notes["notes"]}

    ra = requests.get(f"{API}/notes", headers={"X-Owner-Key": DEV_A})
    assert ra.status_code == 200
    a_list_ids = {n["id"] for n in ra.json()}
    assert a_ids.issubset(a_list_ids)
    assert a_list_ids.isdisjoint(b_ids)

    rb = requests.get(f"{API}/notes", headers={"X-Owner-Key": DEV_B})
    assert rb.status_code == 200
    b_list_ids = {n["id"] for n in rb.json()}
    assert b_ids.issubset(b_list_ids)
    assert b_list_ids.isdisjoint(a_ids)


def test_cross_owner_patch_forbidden(dev_a_notes):
    nid = dev_a_notes["notes"][0]["id"]
    r = requests.patch(f"{API}/notes/{nid}", json={"cpe": "X"},
                       headers={"X-Owner-Key": DEV_B})
    assert r.status_code == 403


def test_cross_owner_delete_forbidden(dev_a_notes):
    nid = dev_a_notes["notes"][0]["id"]
    r = requests.delete(f"{API}/notes/{nid}", headers={"X-Owner-Key": DEV_B})
    assert r.status_code == 403


def test_cross_owner_get_forbidden(dev_a_notes):
    nid = dev_a_notes["notes"][0]["id"]
    r = requests.get(f"{API}/notes/{nid}", headers={"X-Owner-Key": DEV_B})
    assert r.status_code == 403


def test_patch_technical_fields_regenerates_note_text(dev_a_notes):
    nid = dev_a_notes["notes"][1]["id"]
    r = requests.patch(f"{API}/notes/{nid}",
                       json={"ts": "TS 5", "tc": "TC 3", "d": "D 10", "a": "A 2"},
                       headers={"X-Owner-Key": DEV_A})
    assert r.status_code == 200
    data = r.json()
    assert data["ts"] == "TS 5"
    assert data["tc"] == "TC 3"
    assert "TS 5 TC 3 D 10 A 2 MONO INT" in data["note_text"]
    assert "PFS" in data["note_text"] and "PTE" in data["note_text"]
    assert data["note_text_manual"] is False


def test_patch_pte_est_field(dev_a_notes):
    nid = dev_a_notes["notes"][1]["id"]
    r = requests.patch(f"{API}/notes/{nid}", json={"pte_est": "PTE-EST-CUSTOM"},
                       headers={"X-Owner-Key": DEV_A})
    assert r.status_code == 200
    assert "PTE-EST-CUSTOM" in r.json()["note_text"]


def test_manual_note_text_override(dev_a_notes):
    nid = dev_a_notes["notes"][2]["id"]
    custom = "TOTALLY CUSTOM NOTE TEXT LINE 1\nline 2"
    r = requests.patch(f"{API}/notes/{nid}",
                       json={"note_text": custom, "note_text_manual": True},
                       headers={"X-Owner-Key": DEV_A})
    assert r.status_code == 200
    assert r.json()["note_text"] == custom
    assert r.json()["note_text_manual"] is True

    # subsequent patch of other fields should NOT overwrite
    r2 = requests.patch(f"{API}/notes/{nid}", json={"ts": "TS 99"},
                        headers={"X-Owner-Key": DEV_A})
    assert r2.status_code == 200
    assert r2.json()["note_text"] == custom
    assert r2.json()["note_text_manual"] is True
    assert r2.json()["ts"] == "TS 99"


def test_regenerate_endpoint(dev_a_notes):
    nid = dev_a_notes["notes"][2]["id"]
    r = requests.post(f"{API}/notes/{nid}/regenerate",
                      headers={"X-Owner-Key": DEV_A})
    assert r.status_code == 200
    data = r.json()
    assert data["note_text_manual"] is False
    assert "TOTALLY CUSTOM" not in data["note_text"]
    assert "WR:" in data["note_text"]


def test_bulk_delete_scoped(dev_a_notes, dev_b_notes):
    # pick 1 A note (not previously deleted) and 1 B note
    a_id = dev_a_notes["notes"][3]["id"]
    b_id = dev_b_notes["notes"][0]["id"]
    r = requests.post(f"{API}/notes/bulk-delete", json={"ids": [a_id, b_id]},
                      headers={"X-Owner-Key": DEV_A})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1

    # b_id should still exist for DEV_B
    rb = requests.get(f"{API}/notes/{b_id}", headers={"X-Owner-Key": DEV_B})
    assert rb.status_code == 200
    # a_id should not exist
    ra = requests.get(f"{API}/notes/{a_id}", headers={"X-Owner-Key": DEV_A})
    assert ra.status_code == 404


def test_photo_upload_cross_owner_forbidden(dev_a_notes):
    nid = dev_a_notes["notes"][1]["id"]
    files = {"files": ("t.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")}
    r = requests.post(f"{API}/notes/{nid}/photos", files=files,
                      headers={"X-Owner-Key": DEV_B})
    assert r.status_code == 403


def test_photo_delete_cross_owner_forbidden(dev_a_notes):
    nid = dev_a_notes["notes"][1]["id"]
    r = requests.delete(f"{API}/notes/{nid}/photos/does-not-exist",
                        headers={"X-Owner-Key": DEV_B})
    assert r.status_code == 403
