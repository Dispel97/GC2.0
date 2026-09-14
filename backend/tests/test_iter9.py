"""Iteration 9 backend tests: inventory/serials, sync, sospeso status, magazzino role."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fall back to reading frontend env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PWD = "Mucchetta4!"

TECH_EMAIL = f"TEST_tech_{uuid.uuid4().hex[:6]}@example.com"
MAG_EMAIL = f"TEST_mag_{uuid.uuid4().hex[:6]}@example.com"
PWD = "TestPass123"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def tech_ctx(admin_h):
    # register tech
    r = requests.post(f"{API}/auth/register", json={"email": TECH_EMAIL, "password": PWD, "name": "Tech Test"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    # approve as user
    r = requests.post(f"{API}/auth/admin/approve/{uid}", json={"role": "user"}, headers=admin_h)
    assert r.status_code == 200
    assert r.json()["role"] == "user"
    r = requests.post(f"{API}/auth/login", json={"email": TECH_EMAIL, "password": PWD})
    assert r.status_code == 200
    return {"id": uid, "token": r.json()["access_token"], "email": TECH_EMAIL}


@pytest.fixture(scope="module")
def tech_h(tech_ctx):
    return {"Authorization": f"Bearer {tech_ctx['token']}"}


@pytest.fixture(scope="module")
def mag_ctx(admin_h):
    r = requests.post(f"{API}/auth/register", json={"email": MAG_EMAIL, "password": PWD, "name": "Mag Test"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    r = requests.post(f"{API}/auth/admin/approve/{uid}", json={"role": "magazzino"}, headers=admin_h)
    assert r.status_code == 200
    assert r.json()["role"] == "magazzino"
    r = requests.post(f"{API}/auth/login", json={"email": MAG_EMAIL, "password": PWD})
    assert r.status_code == 200
    return {"id": uid, "token": r.json()["access_token"]}


@pytest.fixture(scope="module")
def mag_h(mag_ctx):
    return {"Authorization": f"Bearer {mag_ctx['token']}"}


# ----- Serial CRUD -----
def test_serial_crud(admin_h):
    ser = f"TEST-SN-{uuid.uuid4().hex[:8].upper()}"
    r = requests.post(f"{API}/inventory/serials", json={"serial": ser, "tipo": "CPE"}, headers=admin_h)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["serial"] == ser
    assert doc["status"] == "in_stock"
    sid = doc["id"]

    # list
    r = requests.get(f"{API}/inventory/serials", headers=admin_h)
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())

    # duplicate rejected
    r = requests.post(f"{API}/inventory/serials", json={"serial": ser}, headers=admin_h)
    assert r.status_code == 400

    # get admin user id for assignment
    r = requests.get(f"{API}/inventory/users", headers=admin_h)
    assert r.status_code == 200
    users = r.json()
    assert len(users) > 0
    target = next(u for u in users if u["email"] == ADMIN_EMAIL)

    # assign
    r = requests.patch(f"{API}/inventory/serials/{sid}", json={"assigned_to_user_id": target["id"]}, headers=admin_h)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["status"] == "assegnato"
    assert updated["assigned_to_user_id"] == target["id"]
    assert updated["assigned_to_name"]

    # delete
    r = requests.delete(f"{API}/inventory/serials/{sid}", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["deleted"] == 1


def test_bulk_serials(admin_h):
    s1 = f"TEST-B1-{uuid.uuid4().hex[:6].upper()}"
    s2 = f"TEST-B2-{uuid.uuid4().hex[:6].upper()}"
    # create s1 first to test dedupe
    requests.post(f"{API}/inventory/serials", json={"serial": s1}, headers=admin_h)
    r = requests.post(f"{API}/inventory/serials/bulk",
                      json={"serials": [s1, s2, ""], "tipo": "ONT"}, headers=admin_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    assert s1 in body["skipped"]
    # cleanup
    r = requests.get(f"{API}/inventory/serials", headers=admin_h)
    for s in r.json():
        if s["serial"] in (s1, s2):
            requests.delete(f"{API}/inventory/serials/{s['id']}", headers=admin_h)


# ----- RBAC -----
def test_inventory_forbidden_for_tecnico(tech_h):
    r = requests.get(f"{API}/inventory/serials", headers=tech_h)
    assert r.status_code == 403


def test_inventory_allowed_for_magazzino(mag_h):
    r = requests.get(f"{API}/inventory/serials", headers=mag_h)
    assert r.status_code == 200


# ----- Sync flow -----
def test_sync_note_serials(admin_h, tech_ctx, tech_h):
    # tech uploads pdf
    with open("/tmp/sample.pdf", "rb") as f:
        r = requests.post(f"{API}/pdf/parse", files={"file": ("sample.pdf", f, "application/pdf")}, headers=tech_h)
    assert r.status_code == 200, r.text
    notes = r.json()["notes"]
    assert len(notes) >= 1
    nid = notes[0]["id"]
    wr = notes[0]["wr"]

    cpe_sn = f"TEST-CPE-{uuid.uuid4().hex[:6].upper()}"
    ont_sn = f"TEST-ONT-{uuid.uuid4().hex[:6].upper()}"
    r = requests.patch(f"{API}/notes/{nid}", json={"cpe": cpe_sn, "ont_sfp": ont_sn}, headers=tech_h)
    assert r.status_code == 200

    r = requests.post(f"{API}/notes/{nid}/sync", headers=tech_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["synced"] == 2
    assert body["note"]["synced"] is True
    assert body["note"]["synced_at"]

    # admin sees the two serials as scaricato with downloaded_by_name
    r = requests.get(f"{API}/inventory/serials", headers=admin_h)
    serials = r.json()
    found_cpe = next((s for s in serials if s["serial"] == cpe_sn), None)
    found_ont = next((s for s in serials if s["serial"] == ont_sn), None)
    assert found_cpe and found_ont
    assert found_cpe["status"] == "scaricato"
    assert found_ont["status"] == "scaricato"
    assert found_cpe["downloaded_by_name"]  # non-empty
    assert found_cpe["downloaded_at"]
    # tech name/email used
    assert TECH_EMAIL.lower() in found_cpe["downloaded_by_name"].lower() or "Tech Test" in found_cpe["downloaded_by_name"]

    # cleanup serials & notes
    for s in serials:
        if s["serial"] in (cpe_sn, ont_sn):
            requests.delete(f"{API}/inventory/serials/{s['id']}", headers=admin_h)
    # cleanup all notes for tech
    r = requests.get(f"{API}/notes", headers=tech_h)
    ids = [n["id"] for n in r.json()]
    if ids:
        requests.post(f"{API}/notes/bulk-delete", json={"ids": ids}, headers=tech_h)

    # store wr for next tests
    pytest.tech_wr = wr


# ----- Status sospeso/espletato -----
def test_status_sospeso(tech_h):
    # upload again
    with open("/tmp/sample.pdf", "rb") as f:
        r = requests.post(f"{API}/pdf/parse", files={"file": ("sample.pdf", f, "application/pdf")}, headers=tech_h)
    nid = r.json()["notes"][0]["id"]
    r = requests.patch(f"{API}/notes/{nid}", json={"status": "sospeso", "suspend_reason": "cliente assente"}, headers=tech_h)
    assert r.status_code == 200
    assert r.json()["status"] == "sospeso"
    assert r.json()["suspend_reason"] == "cliente assente"

    r = requests.patch(f"{API}/notes/{nid}", json={"status": "espletato", "suspend_reason": ""}, headers=tech_h)
    assert r.status_code == 200
    assert r.json()["status"] == "espletato"
    assert r.json()["suspend_reason"] == ""

    # cleanup
    r = requests.get(f"{API}/notes", headers=tech_h)
    ids = [n["id"] for n in r.json()]
    if ids:
        requests.post(f"{API}/notes/bulk-delete", json={"ids": ids}, headers=tech_h)


# ----- set-role -----
def test_admin_set_role(admin_h, tech_ctx):
    uid = tech_ctx["id"]
    r = requests.post(f"{API}/auth/admin/set-role/{uid}", json={"role": "magazzino"}, headers=admin_h)
    assert r.status_code == 200
    assert r.json()["role"] == "magazzino"
    # restore
    r = requests.post(f"{API}/auth/admin/set-role/{uid}", json={"role": "user"}, headers=admin_h)
    assert r.status_code == 200
    r = requests.post(f"{API}/auth/admin/set-role/{uid}", json={"role": "bad"}, headers=admin_h)
    assert r.status_code == 400


# ----- magazzino access to notes -----
def test_magazzino_notes_access(mag_h):
    r = requests.get(f"{API}/notes", headers=mag_h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ----- teardown users -----
def test_zzz_cleanup(admin_h, tech_ctx, mag_ctx):
    for uid in (tech_ctx["id"], mag_ctx["id"]):
        requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_h)
