"""Iteration 10 — split status buttons, notifications, serial history, CSV export."""
import os, uuid, time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASSWORD = "Mucchetta4!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def tech_user(admin_headers):
    """Create + approve a regular user."""
    email = f"testi10_tech_{uuid.uuid4().hex[:6]}@example.com"
    password = "TestPass123"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "TestTech"}, timeout=30)
    assert r.status_code == 200, r.text
    # find id
    p = requests.get(f"{API}/auth/admin/pending", headers=admin_headers, timeout=30).json()
    uid = next(u["id"] for u in p if u["email"] == email)
    assert requests.post(f"{API}/auth/admin/approve/{uid}", headers=admin_headers, timeout=30).status_code == 200
    tok = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30).json()["access_token"]
    yield {"id": uid, "email": email, "token": tok, "headers": {"Authorization": f"Bearer {tok}"}}
    requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_headers, timeout=30)


# ---------- Serial history: created/assigned/unassigned/deleted events ----------
def test_serial_history_events(admin_headers, tech_user):
    serial = f"TESTi10-{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{API}/inventory/serials", headers=admin_headers,
                      json={"serial": serial, "tipo": "CPE"}, timeout=30)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]

    # history contains created
    h = requests.get(f"{API}/inventory/serials/{sid}/history", headers=admin_headers, timeout=30)
    assert h.status_code == 200
    events = h.json()["events"]
    assert any(e["event_type"] == "created" for e in events)

    # assign -> assigned event
    r = requests.patch(f"{API}/inventory/serials/{sid}", headers=admin_headers,
                       json={"assigned_to_user_id": tech_user["id"]}, timeout=30)
    assert r.status_code == 200
    events = requests.get(f"{API}/inventory/serials/{sid}/history", headers=admin_headers).json()["events"]
    assert any(e["event_type"] == "assigned" for e in events)

    # clear -> unassigned (frontend sends "" for clearing)
    r = requests.patch(f"{API}/inventory/serials/{sid}", headers=admin_headers,
                       json={"assigned_to_user_id": ""}, timeout=30)
    assert r.status_code == 200
    events = requests.get(f"{API}/inventory/serials/{sid}/history", headers=admin_headers).json()["events"]
    assert any(e["event_type"] == "unassigned" for e in events)

    # delete
    r = requests.delete(f"{API}/inventory/serials/{sid}", headers=admin_headers, timeout=30)
    assert r.status_code == 200

    # events survive deletion — re-create and query history
    r2 = requests.post(f"{API}/inventory/serials", headers=admin_headers,
                       json={"serial": serial, "tipo": "CPE"}, timeout=30)
    assert r2.status_code == 200
    sid2 = r2.json()["id"]
    h2 = requests.get(f"{API}/inventory/serials/{sid2}/history", headers=admin_headers).json()["events"]
    types = [e["event_type"] for e in h2]
    assert "deleted" in types, f"expected deleted in {types}"
    # cleanup
    requests.delete(f"{API}/inventory/serials/{sid2}", headers=admin_headers)


# ---------- CSV export ----------
def test_csv_export(admin_headers):
    r = requests.get(f"{API}/inventory/export.csv", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    assert "text/csv" in ctype and "utf-8" in ctype.lower(), ctype
    text = r.text
    assert text.startswith("\ufeff"), "must start with BOM"
    first_line = text.lstrip("\ufeff").split("\n")[0]
    assert first_line == "seriale,tipo,stato,assegnato_a,scaricato_da,data_scarico,note,creato_il,aggiornato_il"


def test_csv_export_requires_role(tech_user):
    r = requests.get(f"{API}/inventory/export.csv", headers=tech_user["headers"], timeout=30)
    assert r.status_code == 403, r.status_code


# ---------- Notifications: sync creates them, read + read-all ----------
def test_sync_creates_notifications_and_read_flow(admin_headers, tech_user):
    # Create a note as tech user with cpe/ont serials
    wr = f"WRTESTi10{uuid.uuid4().hex[:6]}"
    cpe = f"TESTi10CPE{uuid.uuid4().hex[:6]}"
    ont = f"TESTi10ONT{uuid.uuid4().hex[:6]}"
    note = {
        "wr": wr, "cpe": cpe, "ont_sfp": ont,
        "content_md": "test", "customer_name": "X", "address": "Y",
    }
    # Insert note directly via notes API — there's no POST /notes; use PDF parse? use PATCH after creating fake.
    # Simpler: use bulk-insert workaround — create serial and manually build a note via internal endpoint if exists.
    # Fallback: use PDF parse fixture. But simplest is to hit /notes GET first to see structure.
    # We know sync requires an existing note. Use pdf/parse with sample.pdf.
    fx = "/app/backend/tests/fixtures/sample.pdf"
    if not os.path.exists(fx):
        pytest.skip("no sample.pdf")
    with open(fx, "rb") as f:
        r = requests.post(f"{API}/pdf/parse", headers=tech_user["headers"],
                          files={"file": ("s.pdf", f, "application/pdf")}, timeout=60)
    assert r.status_code == 200, r.text
    notes_list = requests.get(f"{API}/notes", headers=tech_user["headers"], timeout=30).json()
    assert notes_list, "no notes created"
    nid = notes_list[0]["id"]
    # PATCH cpe/ont (wr is not patchable; use the parsed wr)
    r = requests.patch(f"{API}/notes/{nid}", headers=tech_user["headers"],
                       json={"cpe": cpe, "ont_sfp": ont}, timeout=30)
    assert r.status_code == 200
    actual_wr = r.json().get("wr", "")

    # Snapshot admin unread count
    before = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
    unread_before = before["unread"]

    # Sync
    r = requests.post(f"{API}/notes/{nid}/sync", headers=tech_user["headers"], timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("synced") == 2

    # Admin got a notification
    after = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
    assert after["unread"] >= unread_before + 1
    # Find our fresh notification
    fresh = next((n for n in after["items"] if actual_wr and actual_wr in n.get("message", "")), None)
    if fresh is None:
        # fallback: newest notification for admin about this tech
        fresh = next((n for n in after["items"] if n.get("from_user_name") == "TestTech"), None)
    assert fresh is not None, f"no notification for sync (wr={actual_wr})"
    nid_notif = fresh["id"]

    # Mark single read
    r = requests.post(f"{API}/notifications/{nid_notif}/read", headers=admin_headers, timeout=30)
    assert r.status_code == 200

    # Mark all read → unread==0
    r = requests.post(f"{API}/notifications/read-all", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    final = requests.get(f"{API}/notifications", headers=admin_headers, timeout=30).json()
    assert final["unread"] == 0

    # Verify serials have downloaded events + note_wr
    for s in (cpe, ont):
        sdoc = requests.get(f"{API}/inventory/serials", headers=admin_headers,
                            params={"q": s}, timeout=30).json()
        assert sdoc and any(x["serial"] == s for x in sdoc), f"missing {s}"
        sid = next(x["id"] for x in sdoc if x["serial"] == s)
        h = requests.get(f"{API}/inventory/serials/{sid}/history", headers=admin_headers).json()["events"]
        dl = [e for e in h if e["event_type"] == "downloaded"]
        assert dl, "no downloaded event"
        assert dl[0].get("note_wr") == actual_wr
        requests.delete(f"{API}/inventory/serials/{sid}", headers=admin_headers)

    # Cleanup notes
    requests.post(f"{API}/notes/bulk-delete", headers=tech_user["headers"],
                  json={"ids": [n["id"] for n in notes_list]}, timeout=30)


# ---------- Auth guards ----------
def test_notifications_requires_auth():
    r = requests.get(f"{API}/notifications", timeout=30)
    assert r.status_code in (401, 403)
