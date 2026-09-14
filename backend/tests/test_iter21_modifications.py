"""Iteration 21 backend tests:
- POST /api/notes/{id}/unsync reverts serial statuses & marks note synced=False
- POST /api/inventory/serials/bulk-update: tag only, assign, unassign
- 403 for technician on bulk-update
"""
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


def _get_tech_user_id(admin_h):
    r = requests.get(f"{API}/users/approved", headers=admin_h, timeout=20)
    assert r.status_code == 200
    for u in r.json():
        if u.get("email") == TECH_EMAIL:
            return u["id"]
    pytest.skip("tech user not found")


class TestBulkUpdate:
    def _create_serials(self, admin_h, n=3, tipo="TEST_ITER21_TAG"):
        ids = []
        serials = []
        for _ in range(n):
            s = f"TEST21-{uuid.uuid4().hex[:10].upper()}"
            r = requests.post(f"{API}/inventory/serials", json={"serial": s, "tipo": tipo}, headers=admin_h, timeout=20)
            assert r.status_code == 200, r.text
            body = r.json()
            ids.append(body["id"])
            serials.append(s)
        return ids, serials

    def _cleanup(self, admin_h, ids):
        try:
            requests.post(f"{API}/inventory/serials/bulk-delete", json={"ids": ids}, headers=admin_h, timeout=20)
        except Exception:
            pass

    def test_bulk_update_tag(self, admin_h):
        ids, serials = self._create_serials(admin_h, 2, tipo="TEST_ITER21_OLD")
        try:
            r = requests.post(f"{API}/inventory/serials/bulk-update",
                              json={"ids": ids, "tipo": "TEST_ITER21_NEW"}, headers=admin_h, timeout=20)
            assert r.status_code == 200, r.text
            assert r.json().get("updated") == 2
            # verify via GET
            g = requests.get(f"{API}/inventory/serials", headers=admin_h, timeout=20)
            docs = {d["id"]: d for d in g.json() if d["id"] in ids}
            for did in ids:
                assert docs[did]["tipo"] == "TEST_ITER21_NEW"
        finally:
            self._cleanup(admin_h, ids)

    def test_bulk_assign_and_unassign(self, admin_h):
        tech_id = _get_tech_user_id(admin_h)
        ids, _ = self._create_serials(admin_h, 2, tipo="TEST_ITER21_ASSIGN")
        try:
            # assign
            r = requests.post(f"{API}/inventory/serials/bulk-update",
                              json={"ids": ids, "assigned_to_user_id": tech_id}, headers=admin_h, timeout=20)
            assert r.status_code == 200, r.text
            assert r.json().get("updated") == 2
            g = requests.get(f"{API}/inventory/serials", headers=admin_h, timeout=20)
            docs = {d["id"]: d for d in g.json() if d["id"] in ids}
            for did in ids:
                assert docs[did]["assigned_to_user_id"] == tech_id
                assert docs[did]["status"] == "assegnato"

            # unassign
            r2 = requests.post(f"{API}/inventory/serials/bulk-update",
                               json={"ids": ids, "assigned_to_user_id": ""}, headers=admin_h, timeout=20)
            assert r2.status_code == 200, r2.text
            g2 = requests.get(f"{API}/inventory/serials", headers=admin_h, timeout=20)
            docs2 = {d["id"]: d for d in g2.json() if d["id"] in ids}
            for did in ids:
                assert docs2[did]["assigned_to_user_id"] == ""
                assert docs2[did]["status"] == "in_stock"
        finally:
            self._cleanup(admin_h, ids)

    def test_bulk_update_forbidden_for_tech(self, admin_h, tech_h):
        ids, _ = self._create_serials(admin_h, 1)
        try:
            r = requests.post(f"{API}/inventory/serials/bulk-update",
                              json={"ids": ids, "tipo": "X"}, headers=tech_h, timeout=20)
            assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"
        finally:
            self._cleanup(admin_h, ids)


class TestUnsyncNote:
    def test_unsync_reverts_serials_and_note(self, admin_h):
        # Create a serial assigned to admin (so it's assegnato), then create a note with matching cpe? 
        # Simpler: use existing sync flow — find or set up a note with cpe, sync it, then unsync
        # Get admin id
        me = requests.get(f"{API}/auth/me", headers=admin_h, timeout=20).json()
        admin_id = me["id"]

        # Create a serial assigned to admin
        s_val = f"TEST21U-{uuid.uuid4().hex[:8].upper()}"
        cr = requests.post(f"{API}/inventory/serials",
                           json={"serial": s_val, "tipo": "ONT", "assigned_to_user_id": admin_id},
                           headers=admin_h, timeout=20)
        assert cr.status_code == 200, cr.text
        serial_id = cr.json()["id"]

        # find an admin-owned note (WR 17467961 preferred)
        notes = requests.get(f"{API}/notes", headers=admin_h, timeout=20).json()
        target = next((n for n in notes if n.get("wr") == "17467961"), None) or \
                 next((n for n in notes if not n.get("cpe") and not n.get("synced")), None)
        assert target, "no note available"
        nid = target["id"]
        original_cpe = target.get("cpe", "")
        original_ont = target.get("ont_sfp", "")
        original_type = target.get("note_type") or target.get("status") or "limbo"

        try:
            # patch cpe = the serial we created and ont_sfp too for good measure
            requests.patch(f"{API}/notes/{nid}", json={"cpe": s_val}, headers=admin_h, timeout=20)
            # sync
            s = requests.post(f"{API}/notes/{nid}/sync", headers=admin_h, timeout=30)
            assert s.status_code == 200, s.text
            assert s.json().get("synced") >= 1

            # verify serial status is scaricato
            g = requests.get(f"{API}/inventory/serials", headers=admin_h, timeout=20).json()
            our = next((d for d in g if d["id"] == serial_id), None)
            assert our and our["status"] == "scaricato", f"expected scaricato, got {our}"

            # now unsync
            u = requests.post(f"{API}/notes/{nid}/unsync", headers=admin_h, timeout=30)
            assert u.status_code == 200, u.text
            body = u.json()
            assert body.get("unsynced") >= 1
            # note synced flag
            assert body["note"]["synced"] is False

            # serial should be back to assegnato
            g2 = requests.get(f"{API}/inventory/serials", headers=admin_h, timeout=20).json()
            our2 = next((d for d in g2 if d["id"] == serial_id), None)
            assert our2 and our2["status"] == "assegnato", f"expected assegnato after unsync, got {our2}"
            assert our2.get("downloaded_note_id", "") == ""
        finally:
            # restore
            requests.patch(f"{API}/notes/{nid}",
                           json={"cpe": original_cpe, "ont_sfp": original_ont,
                                 "note_type": original_type, "status": original_type},
                           headers=admin_h, timeout=20)
            requests.post(f"{API}/inventory/serials/bulk-delete", json={"ids": [serial_id]},
                          headers=admin_h, timeout=20)

    def test_unsync_on_note_with_no_synced_serials(self, admin_h):
        # find any note owned by admin
        notes = requests.get(f"{API}/notes", headers=admin_h, timeout=20).json()
        target = next((n for n in notes if not n.get("synced")), None)
        assert target
        r = requests.post(f"{API}/notes/{target['id']}/unsync", headers=admin_h, timeout=20)
        assert r.status_code == 200
        assert r.json().get("unsynced") == 0
