"""Iteration 22 backend tests:
- POST /api/instructions/{id}/file admin-only upload; tech gets 403
- GET /api/instructions returns 'files' array for admin AND technician
- DELETE /api/instructions/{id}/file/{fileId} admin-only
- GET /api/files?path=... is public and returns 200 with content
"""
import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASSWORD = "Mucchetta4!"
TECH_EMAIL = "tecnico.test@gc.it"
TECH_PASSWORD = "Test1234!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}


@pytest.fixture(scope="module")
def tech_h():
    return {"Authorization": f"Bearer {_login(TECH_EMAIL, TECH_PASSWORD)}"}


@pytest.fixture(scope="module")
def instruction_id(admin_h):
    # create a new instruction card
    payload = {"title": f"TEST22_{uuid.uuid4().hex[:6]}", "body": "iter22 test card"}
    r = requests.post(f"{API}/instructions", json=payload, headers=admin_h, timeout=20)
    assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
    iid = r.json().get("id") or r.json().get("_id")
    assert iid
    yield iid
    # cleanup
    requests.delete(f"{API}/instructions/{iid}", headers=admin_h, timeout=20)


def test_upload_file_admin_success(admin_h, instruction_id):
    files = {"file": ("iter22.txt", io.BytesIO(b"hello iter22"), "text/plain")}
    r = requests.post(f"{API}/instructions/{instruction_id}/file", files=files,
                      headers=admin_h, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert "files" in body and len(body["files"]) >= 1
    f = body["files"][-1]
    assert f["filename"] == "iter22.txt"
    assert f["size"] == len(b"hello iter22")
    assert "storage_path" in f and "id" in f
    pytest.file_info = f  # stash for later tests


def test_upload_file_tech_forbidden(tech_h, instruction_id):
    files = {"file": ("nope.txt", io.BytesIO(b"nope"), "text/plain")}
    r = requests.post(f"{API}/instructions/{instruction_id}/file", files=files,
                      headers=tech_h, timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"


def test_instructions_list_contains_files_admin(admin_h, instruction_id):
    r = requests.get(f"{API}/instructions", headers=admin_h, timeout=20)
    assert r.status_code == 200
    match = next((x for x in r.json() if x.get("id") == instruction_id), None)
    assert match is not None
    assert isinstance(match.get("files"), list)
    assert any(f["filename"] == "iter22.txt" for f in match["files"])


def test_instructions_list_contains_files_tech(tech_h, instruction_id):
    r = requests.get(f"{API}/instructions", headers=tech_h, timeout=20)
    assert r.status_code == 200
    match = next((x for x in r.json() if x.get("id") == instruction_id), None)
    assert match is not None
    assert isinstance(match.get("files"), list)
    assert any(f["filename"] == "iter22.txt" for f in match["files"])


def test_files_endpoint_public_download(instruction_id, admin_h):
    # get storage_path via admin
    r = requests.get(f"{API}/instructions", headers=admin_h, timeout=20)
    match = next((x for x in r.json() if x.get("id") == instruction_id), None)
    f = match["files"][-1]
    path = f["storage_path"]

    # no auth header -> public
    r2 = requests.get(f"{API}/files", params={"path": path}, timeout=30)
    assert r2.status_code == 200, f"{r2.status_code} {r2.text[:200]}"
    assert r2.content == b"hello iter22"


def test_delete_file_tech_forbidden(tech_h, instruction_id, admin_h):
    r = requests.get(f"{API}/instructions", headers=admin_h, timeout=20)
    match = next((x for x in r.json() if x.get("id") == instruction_id), None)
    fid = match["files"][-1]["id"]
    r2 = requests.delete(f"{API}/instructions/{instruction_id}/file/{fid}",
                         headers=tech_h, timeout=20)
    assert r2.status_code == 403


def test_delete_file_admin_success(admin_h, instruction_id):
    r = requests.get(f"{API}/instructions", headers=admin_h, timeout=20)
    match = next((x for x in r.json() if x.get("id") == instruction_id), None)
    fid = match["files"][-1]["id"]
    r2 = requests.delete(f"{API}/instructions/{instruction_id}/file/{fid}",
                         headers=admin_h, timeout=20)
    assert r2.status_code == 200
    assert not any(f["id"] == fid for f in r2.json().get("files", []))
