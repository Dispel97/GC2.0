"""Backend tests for the 7 modifications (iteration 19)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://gc-gestionale.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "giuseppe97belviso@gmail.com", "password": "Mucchetta4!"}
TECH = {"email": "tecnico.test@gc.it", "password": "Test1234!"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def tech_token():
    return _login(TECH)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- Notes visibility (#7 admin cross-visibility) ----------
class TestNotesVisibility:
    def test_admin_sees_tech_note(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/notes", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        wrs = [n.get("wr") for n in r.json()]
        assert "99000001" in wrs, f"Admin should see tech note WR 99000001. Got: {wrs[:10]}"

    def test_admin_sees_espletato_note(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/notes", headers=H(admin_token), timeout=15)
        wrs = [n.get("wr") for n in r.json()]
        assert "17396958" in wrs

    def test_tech_sees_own_note(self, tech_token):
        r = requests.get(f"{BASE_URL}/api/notes", headers=H(tech_token), timeout=15)
        assert r.status_code == 200
        wrs = [n.get("wr") for n in r.json()]
        assert "99000001" in wrs

    def test_tech_does_not_see_admin_note(self, tech_token):
        r = requests.get(f"{BASE_URL}/api/notes", headers=H(tech_token), timeout=15)
        wrs = [n.get("wr") for n in r.json()]
        assert "17467961" not in wrs, f"Tech should NOT see admin's note; got {wrs}"


# ---------- Email recipients (#4) ----------
class TestEmailRecipients:
    def test_get_default(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/email-recipients", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json().get("recipients"), list)

    def test_put_and_persist(self, admin_token):
        new_email = f"test_{uuid.uuid4().hex[:6]}@example.com"
        current = requests.get(f"{BASE_URL}/api/email-recipients", headers=H(admin_token)).json()["recipients"]
        updated = current + [new_email]
        r = requests.put(f"{BASE_URL}/api/email-recipients", headers=H(admin_token), json={"recipients": updated}, timeout=15)
        assert r.status_code == 200
        assert new_email in r.json()["recipients"]
        # Persist check
        r2 = requests.get(f"{BASE_URL}/api/email-recipients", headers=H(admin_token)).json()
        assert new_email in r2["recipients"]
        # Cleanup: restore
        requests.put(f"{BASE_URL}/api/email-recipients", headers=H(admin_token), json={"recipients": current})


# ---------- Instructions (#6) ----------
class TestInstructions:
    def test_list_open_to_all(self, tech_token):
        r = requests.get(f"{BASE_URL}/api/instructions", headers=H(tech_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tech_cannot_create(self, tech_token):
        r = requests.post(f"{BASE_URL}/api/instructions", headers=H(tech_token),
                          json={"title": "TEST_forbidden", "description": "x"}, timeout=15)
        assert r.status_code in (401, 403), f"expected forbidden, got {r.status_code}"

    def test_admin_crud(self, admin_token):
        # Create
        r = requests.post(f"{BASE_URL}/api/instructions", headers=H(admin_token),
                          json={"title": "TEST_iter19", "description": "desc"}, timeout=15)
        assert r.status_code == 200, r.text
        iid = r.json()["id"]
        assert r.json()["title"] == "TEST_iter19"
        # Update
        r2 = requests.patch(f"{BASE_URL}/api/instructions/{iid}", headers=H(admin_token),
                            json={"title": "TEST_iter19_upd"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["title"] == "TEST_iter19_upd"
        # Verify GET
        lst = requests.get(f"{BASE_URL}/api/instructions", headers=H(admin_token)).json()
        titles = [x["title"] for x in lst]
        assert "TEST_iter19_upd" in titles
        # Delete
        r3 = requests.delete(f"{BASE_URL}/api/instructions/{iid}", headers=H(admin_token), timeout=15)
        assert r3.status_code == 200
        assert r3.json()["deleted"] == 1
        # Verify removed
        lst2 = requests.get(f"{BASE_URL}/api/instructions", headers=H(admin_token)).json()
        assert not any(x["id"] == iid for x in lst2)

    def test_create_empty_title_rejected(self, admin_token):
        r = requests.post(f"{BASE_URL}/api/instructions", headers=H(admin_token),
                          json={"title": "  ", "description": ""}, timeout=15)
        assert r.status_code == 400


# ---------- Note edit preserves list (#3 backend contract) ----------
class TestNoteEditContract:
    def test_patch_note_returns_updated(self, admin_token):
        # Get admin's first note
        notes = requests.get(f"{BASE_URL}/api/notes", headers=H(admin_token)).json()
        admin_email = ADMIN["email"].lower()
        my = [n for n in notes if (n.get("user_email") or "").lower() == admin_email]
        if not my:
            pytest.skip("no admin-owned notes")
        note_id = my[0]["id"]
        original_cliente = my[0].get("cliente", "")
        new_val = f"TEST_{uuid.uuid4().hex[:4]}"
        r = requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=H(admin_token),
                           json={"cliente": new_val}, timeout=15)
        assert r.status_code == 200, r.text
        # restore
        requests.patch(f"{BASE_URL}/api/notes/{note_id}", headers=H(admin_token),
                       json={"cliente": original_cliente})
