"""Iteration 13 tests: notes/stats, note_type sync, multi-serial, thresholds, team, users/approved, suspend-email, compose_note."""
import os
import time
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://openfiber-notes.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASS = "Mucchetta4!"

TS = str(int(time.time()))


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- notes/stats ----------
def test_notes_stats_structure(h):
    r = requests.get(f"{BASE_URL}/api/notes/stats", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("totals", "avg_completed_per_working_day", "avg_faults_per_working_day", "working_days_count", "daily"):
        assert k in j, f"missing key {k}"
    for k in ("limbo", "espletato", "sospeso", "guasto", "migrazione"):
        assert k in j["totals"]
    # Saturday flag
    sats = [d for d in j["daily"] if d["is_saturday"]]
    for s in sats:
        assert s["is_saturday"] is True
    # working_days_count should equal non-saturday days in daily
    non_sat = [d for d in j["daily"] if not d["is_saturday"]]
    assert j["working_days_count"] == len(non_sat)


def test_notes_stats_date_range(h):
    r = requests.get(f"{BASE_URL}/api/notes/stats?from=2026-01-05&to=2026-01-11", headers=h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    # 2026-01-10 is Saturday
    days = {d["date"]: d for d in j["daily"]}
    assert "2026-01-10" in days
    assert days["2026-01-10"]["is_saturday"] is True
    assert days["2026-01-05"]["is_saturday"] is False
    # 7 days total, 6 working (excluding Sat)
    assert len(j["daily"]) == 7
    assert j["working_days_count"] == 6


# ---------- Note patch: note_type / status sync ----------
@pytest.fixture(scope="module")
def note_id(h):
    """Create a note directly via mongo (no direct API endpoint for note creation)."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    mc = MongoClient(mongo_url)
    d = mc[db_name]
    # get admin user
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=10).json()
    nid = str(_uuid.uuid4())
    doc = {
        "id": nid, "user_id": me["id"], "shared_with": [],
        "wr": f"WRTEST{TS}", "cliente": "orig", "olo": "OLO1",
        "splitter": "", "via": "", "n_porta_perm": "", "porta_pte": "",
        "cpe": "", "ont_sfp": "", "status": "limbo", "note_type": "limbo",
        "note_date": datetime.now(timezone.utc).date().isoformat(),
        "materials": [],
        "note_text": "WR: WRTEST", "note_text_manual": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    d.notes.insert_one(doc)
    yield nid
    try:
        d.notes.delete_one({"id": nid})
    except Exception:
        pass
    mc.close()


def test_patch_note_type_migrazione_syncs_status(h, note_id):
    r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=h, json={"note_type": "migrazione"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("note_type") == "migrazione"
    assert d.get("status") == "migrazione"


def test_patch_status_espletato_syncs_note_type(h, note_id):
    r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=h, json={"status": "espletato"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("status") == "espletato"
    assert d.get("note_type") == "espletato"


def test_patch_note_type_guasto(h, note_id):
    r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=h, json={"note_type": "guasto"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("note_type") == "guasto"


# ---------- Send suspend email ----------
def test_suspend_email_400_when_not_sospeso(h, note_id):
    # currently guasto from previous test
    r = requests.post(f"{BASE_URL}/api/notes/{note_id}/send-suspend-email",
                      headers=h, json={"to": "test@example.com"}, timeout=15)
    assert r.status_code == 400


def test_suspend_email_ok_when_sospeso(h, note_id):
    r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=h,
                       json={"note_type": "sospeso", "suspend_reason": "R123", "olo": "OLO9"}, timeout=15)
    assert r.status_code == 200
    r = requests.post(f"{BASE_URL}/api/notes/{note_id}/send-suspend-email",
                      headers=h, json={"to": "test@example.com"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["to"] == "test@example.com"
    assert "OLO9" in j["body"]
    assert "R123" in j["body"]


# ---------- Compose note: empty fields skipped, materials ----------
def test_compose_note_materials_and_empty_fields(h, note_id):
    # Set empty cliente/olo and add materials
    r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=h,
                       json={"cliente": "", "olo": "", "cpe": "", "ont_sfp": "",
                             "materials": [{"tipo": "EXT", "serial": "123ABC"}]}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    txt = d.get("note_text", "")
    # Empty lines should not be present
    assert "\n\n" not in txt.strip()
    assert "EXT: 123ABC" in txt


# ---------- Multi-serial paste ----------
def test_multi_serial_paste_and_cleanup(h):
    ser_prefix = f"TESTI13_{TS}_"
    payload = {"serial": f"{ser_prefix}A {ser_prefix}B {ser_prefix}C", "tipo": "TESTI13"}
    r = requests.post(f"{BASE_URL}/api/inventory/serials", headers=h, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("multi") is True
    assert j.get("created_count") == 3
    assert len(j.get("created", [])) == 3
    # cleanup
    for s in j["created"]:
        rr = requests.get(f"{BASE_URL}/api/inventory/serials?search={s}", headers=h, timeout=15)
        if rr.status_code == 200:
            for it in rr.json():
                if it["serial"] == s:
                    requests.delete(f"{BASE_URL}/api/inventory/serials/{it['id']}", headers=h, timeout=15)


# ---------- Thresholds ----------
def test_thresholds_crud_and_alert(h):
    # Set a very high threshold — should always trigger alert
    r = requests.post(f"{BASE_URL}/api/inventory/thresholds", headers=h,
                      json={"tag": "CPE", "threshold": 100000}, timeout=15)
    assert r.status_code == 200
    assert r.json()["threshold"] == 100000

    # List
    r = requests.get(f"{BASE_URL}/api/inventory/thresholds", headers=h, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert any(i["tag"] == "CPE" and i["threshold"] == 100000 for i in items)

    # Check notification created (kind=threshold_alert)
    r = requests.get(f"{BASE_URL}/api/notifications?limit=50", headers=h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    kinds = [n.get("kind") for n in j.get("items", [])]
    assert "threshold_alert" in kinds, f"no threshold_alert notification: {kinds[:10]}"

    # Delete threshold with 0
    r = requests.post(f"{BASE_URL}/api/inventory/thresholds", headers=h,
                      json={"tag": "CPE", "threshold": 0}, timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{BASE_URL}/api/inventory/thresholds", headers=h, timeout=15)
    assert not any(i["tag"] == "CPE" for i in r.json())


# ---------- Users approved ----------
def test_users_approved(h):
    r = requests.get(f"{BASE_URL}/api/users/approved", headers=h, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    # admin should not include self
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    for u in items:
        assert u["id"] != me["id"]


# ---------- Team ----------
def test_team_today_empty(h):
    # Clear partner first
    r = requests.post(f"{BASE_URL}/api/team/today", headers=h, json={"partner_user_id": ""}, timeout=15)
    assert r.status_code == 200
    r = requests.get(f"{BASE_URL}/api/team/today", headers=h, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j.get("partner") is None
    assert j.get("partner_ids") == []


def test_team_today_set_self_rejected(h):
    me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
    r = requests.post(f"{BASE_URL}/api/team/today", headers=h,
                      json={"partner_user_id": me["id"]}, timeout=15)
    assert r.status_code == 400
