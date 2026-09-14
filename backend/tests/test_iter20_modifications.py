"""Iteration 20 backend tests:
- GET /api/instructions sorted by 'order'
- POST /api/instructions/reorder (admin) persists new order
- POST /api/instructions/{id}/image (admin) with image file adds image
- DELETE /api/instructions/{id}/image/{imgId} (admin) removes image
- non-admin gets 403 on reorder/image upload/delete
- Auto-sync path: create note with cpe -> PATCH to espletato -> POST sync returns synced>=1
"""
import io
import os
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
    return j.get("access_token") or j["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def tech_token():
    return _login(TECH_EMAIL, TECH_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def tech_headers(tech_token):
    return {"Authorization": f"Bearer {tech_token}"}


# ---------- Instructions ----------
class TestInstructions:
    created_ids = []

    def test_list_sorted_by_order(self, admin_headers):
        r = requests.get(f"{API}/instructions", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # verify sort key ascending when order present
        orders = [it.get("order", 0) for it in items]
        assert orders == sorted(orders), f"instructions not sorted by order: {orders}"

    def test_create_two_and_reorder(self, admin_headers):
        a = requests.post(f"{API}/instructions", json={"title": "TEST_ITER20_A", "description": "a"}, headers=admin_headers, timeout=20)
        b = requests.post(f"{API}/instructions", json={"title": "TEST_ITER20_B", "description": "b"}, headers=admin_headers, timeout=20)
        assert a.status_code == 200 and b.status_code == 200
        aid, bid = a.json()["id"], b.json()["id"]
        TestInstructions.created_ids.extend([aid, bid])

        # get current list, reorder placing bid before aid (relative)
        r = requests.get(f"{API}/instructions", headers=admin_headers, timeout=20)
        items = r.json()
        ids = [x["id"] for x in items]
        assert aid in ids and bid in ids
        # build reorder ids: put bid first, then aid, then rest (excluding these two)
        rest = [i for i in ids if i not in (aid, bid)]
        new_order = [bid, aid] + rest
        rr = requests.post(f"{API}/instructions/reorder", json={"ids": new_order}, headers=admin_headers, timeout=20)
        assert rr.status_code == 200, rr.text
        assert rr.json().get("count") == len(new_order)

        # verify persisted
        r2 = requests.get(f"{API}/instructions", headers=admin_headers, timeout=20)
        ids2 = [x["id"] for x in r2.json()]
        # bid should now come before aid
        assert ids2.index(bid) < ids2.index(aid), f"reorder not persisted: {ids2}"

    def test_upload_and_delete_image(self, admin_headers):
        assert TestInstructions.created_ids, "prev test must have created ids"
        iid = TestInstructions.created_ids[0]
        # tiny 1x1 png
        png_bytes = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
        )
        files = {"file": ("t.png", io.BytesIO(png_bytes), "image/png")}
        r = requests.post(f"{API}/instructions/{iid}/image", files=files, headers=admin_headers, timeout=30)
        assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
        images = r.json().get("images", [])
        assert len(images) >= 1
        img_id = images[-1]["id"]

        # delete
        dr = requests.delete(f"{API}/instructions/{iid}/image/{img_id}", headers=admin_headers, timeout=20)
        assert dr.status_code == 200
        remaining = dr.json().get("images", [])
        assert all(im["id"] != img_id for im in remaining)

    def test_non_admin_forbidden(self, tech_headers, admin_headers):
        iid = TestInstructions.created_ids[0]
        # reorder
        r = requests.post(f"{API}/instructions/reorder", json={"ids": [iid]}, headers=tech_headers, timeout=20)
        assert r.status_code == 403
        # image upload
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
        )
        files = {"file": ("t.png", io.BytesIO(png), "image/png")}
        r2 = requests.post(f"{API}/instructions/{iid}/image", files=files, headers=tech_headers, timeout=30)
        assert r2.status_code == 403
        # image delete
        r3 = requests.delete(f"{API}/instructions/{iid}/image/fake-id", headers=tech_headers, timeout=20)
        assert r3.status_code == 403

    def test_cleanup(self, admin_headers):
        for iid in TestInstructions.created_ids:
            requests.delete(f"{API}/instructions/{iid}", headers=admin_headers, timeout=20)


# ---------- Auto-sync (backend part) ----------
class TestAutoSyncBackend:
    def test_create_note_set_cpe_espletato_and_sync(self, admin_headers):
        # Use an existing admin note (WR 17467961) - patch it with a test cpe and sync
        # first, find note id
        listr = requests.get(f"{API}/notes", headers=admin_headers, timeout=20)
        assert listr.status_code == 200, listr.text
        notes = listr.json()
        target = next((n for n in notes if n.get("wr") == "17467961"), None)
        if not target:
            target = next((n for n in notes if not n.get("cpe")), None)
        assert target, "no note available for sync test"
        nid = target["id"]
        original_cpe = target.get("cpe", "")
        original_type = target.get("note_type") or target.get("status")
        try:
            # patch cpe
            p0 = requests.patch(f"{API}/notes/{nid}", json={"cpe": "TESTCPE_ITER20_001"}, headers=admin_headers, timeout=20)
            assert p0.status_code == 200, p0.text

            # patch to espletato
            p = requests.patch(
                f"{API}/notes/{nid}",
                json={"note_type": "espletato", "status": "espletato"},
                headers=admin_headers,
                timeout=20,
            )
            assert p.status_code == 200, p.text

            # explicit sync (mimic auto-sync frontend call)
            s = requests.post(f"{API}/notes/{nid}/sync", headers=admin_headers, timeout=30)
            assert s.status_code == 200, s.text
            body = s.json()
            assert "synced" in body
            assert body["synced"] >= 1, f"expected synced>=1, got {body}"
        finally:
            # restore
            requests.patch(f"{API}/notes/{nid}", json={"cpe": original_cpe, "note_type": original_type or "limbo", "status": original_type or "limbo"}, headers=admin_headers, timeout=20)
