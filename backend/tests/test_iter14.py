"""Iteration 14 tests: warehouse bulk-delete, tags/delete, my-assigned, vacations, admin dashboard."""
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASSWORD = "Mucchetta4!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_headers(admin_headers):
    """Register+approve a non-admin user, return that user's auth headers + id."""
    email = f"test_iter14_{int(time.time())}@example.com"
    pw = "TestPass123!"
    r = requests.post(f"{BASE}/api/auth/register", json={"email": email, "password": pw, "name": "Iter14 User"})
    assert r.status_code == 200, r.text
    # approve
    pending = requests.get(f"{BASE}/api/auth/admin/pending", headers=admin_headers).json()
    uid = next(u["id"] for u in pending if u["email"] == email)
    ap = requests.post(f"{BASE}/api/auth/admin/approve/{uid}", headers=admin_headers, json={"role": "user"})
    assert ap.status_code == 200
    li = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    assert li.status_code == 200
    tok = li.json()["access_token"]
    return {"headers": {"Authorization": f"Bearer {tok}"}, "id": uid, "email": email, "token": tok}


# --------------- warehouse bulk-delete + tags/delete ---------------
class TestWarehouseBulkOps:
    def test_bulk_delete_and_tag_delete(self, admin_headers):
        tag = f"TESTI14_{int(time.time())}"
        # create 3 serials with the same tipo
        r = requests.post(f"{BASE}/api/inventory/serials/bulk",
                          headers=admin_headers,
                          json={"tipo": tag, "serials": [f"S14A_{uuid.uuid4().hex[:6]}",
                                                          f"S14B_{uuid.uuid4().hex[:6]}",
                                                          f"S14C_{uuid.uuid4().hex[:6]}"]})
        assert r.status_code == 200, r.text
        assert r.json().get("created") == 3

        # list them
        lst = requests.get(f"{BASE}/api/inventory/serials", headers=admin_headers, params={"tipo": tag}).json()
        ids = [s["id"] for s in lst]
        assert len(ids) == 3

        # bulk-delete first two
        r = requests.post(f"{BASE}/api/inventory/serials/bulk-delete",
                          headers=admin_headers, json={"ids": ids[:2]})
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] == 2

        # verify GET returns only 1 now
        remaining = requests.get(f"{BASE}/api/inventory/serials", headers=admin_headers, params={"tipo": tag}).json()
        assert len(remaining) == 1

        # set a threshold for this tag
        th = requests.post(f"{BASE}/api/inventory/thresholds", headers=admin_headers,
                           json={"tag": tag, "threshold": 5})
        assert th.status_code == 200

        # delete_tag clears tipo and removes threshold
        r = requests.post(f"{BASE}/api/inventory/tags/delete", headers=admin_headers, json={"tag": tag})
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 1

        # no more serials with that tipo
        after = requests.get(f"{BASE}/api/inventory/serials", headers=admin_headers, params={"tipo": tag}).json()
        assert len(after) == 0

        # threshold gone
        ths = requests.get(f"{BASE}/api/inventory/thresholds", headers=admin_headers).json()
        assert not any(t.get("tag") == tag for t in ths)

        # cleanup the remaining serial
        requests.post(f"{BASE}/api/inventory/serials/bulk-delete",
                      headers=admin_headers, json={"ids": [remaining[0]["id"]]})

    def test_bulk_delete_empty_ids(self, admin_headers):
        r = requests.post(f"{BASE}/api/inventory/serials/bulk-delete", headers=admin_headers, json={"ids": []})
        assert r.status_code == 200
        assert r.json()["deleted"] == 0

    def test_delete_tag_empty(self, admin_headers):
        r = requests.post(f"{BASE}/api/inventory/tags/delete", headers=admin_headers, json={"tag": ""})
        assert r.status_code == 400


# --------------- my-assigned ---------------
class TestMyAssigned:
    def test_requires_auth(self):
        r = requests.get(f"{BASE}/api/inventory/my-assigned")
        assert r.status_code in (401, 403)

    def test_returns_only_assigned_not_scaricato(self, admin_headers, user_headers):
        tag = f"MA14_{int(time.time())}"
        # create a serial and assign to the test user
        c = requests.post(f"{BASE}/api/inventory/serials", headers=admin_headers,
                          json={"tipo": tag, "serial": f"MA_{uuid.uuid4().hex[:8]}"})
        assert c.status_code == 200, c.text
        sid = c.json()["id"]
        u = requests.patch(f"{BASE}/api/inventory/serials/{sid}", headers=admin_headers,
                           json={"assigned_to_user_id": user_headers["id"], "status": "assegnato"})
        assert u.status_code == 200, u.text

        # user sees it
        r = requests.get(f"{BASE}/api/inventory/my-assigned", headers=user_headers["headers"])
        assert r.status_code == 200
        found = [s for s in r.json() if s["id"] == sid]
        assert len(found) == 1

        # with tipo filter
        r2 = requests.get(f"{BASE}/api/inventory/my-assigned",
                          headers=user_headers["headers"], params={"tipo": tag})
        assert r2.status_code == 200
        assert all(s["tipo"] == tag for s in r2.json())
        assert any(s["id"] == sid for s in r2.json())

        # mark scaricato -> should disappear
        requests.patch(f"{BASE}/api/inventory/serials/{sid}", headers=admin_headers,
                       json={"status": "scaricato"})
        r3 = requests.get(f"{BASE}/api/inventory/my-assigned", headers=user_headers["headers"])
        assert not any(s["id"] == sid for s in r3.json())

        # cleanup
        requests.delete(f"{BASE}/api/inventory/serials/{sid}", headers=admin_headers)


# --------------- Vacations ---------------
class TestVacations:
    def test_full_flow_create_list_decide_delete(self, admin_headers, user_headers):
        # user creates
        payload = {"from_date": "2030-01-10", "to_date": "2030-01-15", "reason": "TEST iter14"}
        c = requests.post(f"{BASE}/api/vacations", headers=user_headers["headers"], json=payload)
        assert c.status_code == 200, c.text
        vac = c.json()
        assert vac["status"] == "pending"
        assert vac["user_id"] == user_headers["id"]
        vid = vac["id"]

        # user list = only theirs
        ul = requests.get(f"{BASE}/api/vacations", headers=user_headers["headers"]).json()
        assert all(v["user_id"] == user_headers["id"] for v in ul)
        assert any(v["id"] == vid for v in ul)

        # admin list = all
        al = requests.get(f"{BASE}/api/vacations", headers=admin_headers).json()
        assert any(v["id"] == vid for v in al)

        # notification created for admin
        notifs = requests.get(f"{BASE}/api/notifications", headers=admin_headers).json().get("items", [])
        assert any(n.get("kind") == "vacation_request" and n.get("note_id") == vid for n in notifs)

        # non-admin cannot decide
        bad = requests.post(f"{BASE}/api/vacations/{vid}/decision",
                            headers=user_headers["headers"],
                            json={"decision": "approved", "admin_note": "x"})
        assert bad.status_code == 403

        # admin approves
        dec = requests.post(f"{BASE}/api/vacations/{vid}/decision",
                            headers=admin_headers,
                            json={"decision": "approved", "admin_note": "OK"})
        assert dec.status_code == 200
        assert dec.json()["status"] == "approved"
        assert dec.json()["admin_note"] == "OK"

        # user gets a vacation_decision notification
        un = requests.get(f"{BASE}/api/notifications", headers=user_headers["headers"]).json().get("items", [])
        assert any(n.get("kind") == "vacation_decision" and n.get("note_id") == vid for n in un)

        # user cannot delete non-pending
        del_u = requests.delete(f"{BASE}/api/vacations/{vid}", headers=user_headers["headers"])
        assert del_u.status_code == 404

        # admin can delete any
        del_a = requests.delete(f"{BASE}/api/vacations/{vid}", headers=admin_headers)
        assert del_a.status_code == 200

    def test_invalid_dates(self, user_headers):
        r = requests.post(f"{BASE}/api/vacations", headers=user_headers["headers"],
                          json={"from_date": "2030-05-10", "to_date": "2030-05-01"})
        assert r.status_code == 400

        r2 = requests.post(f"{BASE}/api/vacations", headers=user_headers["headers"],
                           json={"from_date": "not-a-date", "to_date": "2030-05-01"})
        assert r2.status_code == 400

    def test_invalid_decision(self, admin_headers, user_headers):
        c = requests.post(f"{BASE}/api/vacations", headers=user_headers["headers"],
                          json={"from_date": "2030-06-01", "to_date": "2030-06-02"}).json()
        vid = c["id"]
        r = requests.post(f"{BASE}/api/vacations/{vid}/decision", headers=admin_headers,
                          json={"decision": "maybe"})
        assert r.status_code == 400
        requests.delete(f"{BASE}/api/vacations/{vid}", headers=admin_headers)

    def test_user_pending_delete_own(self, admin_headers, user_headers):
        c = requests.post(f"{BASE}/api/vacations", headers=user_headers["headers"],
                          json={"from_date": "2030-07-01", "to_date": "2030-07-02"}).json()
        vid = c["id"]
        r = requests.delete(f"{BASE}/api/vacations/{vid}", headers=user_headers["headers"])
        assert r.status_code == 200


# --------------- Admin dashboard ---------------
class TestAdminDashboard:
    def test_requires_admin(self, user_headers):
        r = requests.get(f"{BASE}/api/admin/dashboard", headers=user_headers["headers"])
        assert r.status_code == 403

    def test_shape(self, admin_headers):
        r = requests.get(f"{BASE}/api/admin/dashboard", headers=admin_headers,
                        params={"from": "2026-01-01", "to": "2026-01-31"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "users" in data and "working_days" in data
        assert data["from"] == "2026-01-01"
        assert data["to"] == "2026-01-31"
        assert isinstance(data["working_days"], int) and data["working_days"] >= 1
        assert isinstance(data["users"], list)
        if data["users"]:
            u = data["users"][0]
            for k in ("id", "email", "name", "role", "totals", "avg_completed", "stock"):
                assert k in u, f"missing {k}"
            for k in ("limbo", "espletato", "sospeso", "guasto", "migrazione"):
                assert k in u["totals"]
            for k in ("in_stock", "assegnato", "scaricato"):
                assert k in u["stock"]

    def test_default_date_range(self, admin_headers):
        r = requests.get(f"{BASE}/api/admin/dashboard", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["from"] and data["to"]
