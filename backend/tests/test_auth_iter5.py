"""Iteration 5 — Auth + Notes scoping tests.

Covers:
  - Admin seed + login
  - User register / duplicate / short pw
  - Login denied for pending user (403)
  - /auth/me protected
  - /auth/admin/{pending,users,approve,revoke,delete} + non-admin 403
  - Notes/PDF endpoints require Bearer; scoped by user_id
  - Bulk-delete only deletes caller's ids
  - PDF parse under authed user → 4 numeric WR notes, 1 alphanumeric skipped
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASSWORD = "Mucchetta4!"

SAMPLE_PDF = "/tmp/sample.pdf" if os.path.exists("/tmp/sample.pdf") else "/app/backend/tests/fixtures/sample.pdf"


def _u(prefix: str) -> str:
    return f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["role"] == "admin"
    assert data["user"]["is_approved"] is True
    return data["access_token"]


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def user_a(admin_h):
    """Approved user A."""
    email = _u("A")
    pw = "PassAaaa1"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "User A"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    r = requests.post(f"{API}/auth/admin/approve/{uid}", headers=admin_h)
    assert r.status_code == 200
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    token = r.json()["access_token"]
    yield {"id": uid, "email": email, "token": token, "h": {"Authorization": f"Bearer {token}"}}
    # cleanup
    requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_h)


@pytest.fixture(scope="module")
def user_b(admin_h):
    email = _u("B")
    pw = "PassBbbb1"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 200
    uid = r.json()["id"]
    requests.post(f"{API}/auth/admin/approve/{uid}", headers=admin_h)
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    token = r.json()["access_token"]
    yield {"id": uid, "email": email, "token": token, "h": {"Authorization": f"Bearer {token}"}}
    requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_h)


# ---------- Admin login ----------
class TestAdminAuth:
    def test_admin_login_success(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_admin_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_admin_me(self, admin_h):
        r = requests.get(f"{API}/auth/me", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        assert "password_hash" not in data


# ---------- Register ----------
class TestRegister:
    def test_register_creates_pending(self, admin_h):
        email = _u("pending")
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "abcdef"})
        assert r.status_code == 200
        assert r.json()["is_approved"] is False
        uid = r.json()["id"]
        # Login must be 403
        r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "abcdef"})
        assert r2.status_code == 403
        assert "attesa" in r2.json().get("detail", "").lower()
        # Admin sees in pending
        r3 = requests.get(f"{API}/auth/admin/pending", headers=admin_h)
        assert r3.status_code == 200
        assert any(u["id"] == uid for u in r3.json())
        # Approve → can login
        assert requests.post(f"{API}/auth/admin/approve/{uid}", headers=admin_h).status_code == 200
        r4 = requests.post(f"{API}/auth/login", json={"email": email, "password": "abcdef"})
        assert r4.status_code == 200
        # Revoke
        assert requests.post(f"{API}/auth/admin/revoke/{uid}", headers=admin_h).status_code == 200
        r5 = requests.post(f"{API}/auth/login", json={"email": email, "password": "abcdef"})
        assert r5.status_code == 403
        # Delete
        assert requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_h).status_code == 200

    def test_register_duplicate(self):
        email = _u("dup")
        assert requests.post(f"{API}/auth/register", json={"email": email, "password": "abcdef"}).status_code == 200
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "abcdef"})
        assert r.status_code == 400

    def test_register_short_password(self):
        r = requests.post(f"{API}/auth/register", json={"email": _u("short"), "password": "abc"})
        assert r.status_code == 400


# ---------- Admin protection ----------
class TestAdminProtection:
    def test_pending_requires_admin(self, user_a):
        r = requests.get(f"{API}/auth/admin/pending", headers=user_a["h"])
        assert r.status_code == 403

    def test_users_requires_admin(self, user_a):
        r = requests.get(f"{API}/auth/admin/users", headers=user_a["h"])
        assert r.status_code == 403

    def test_no_token_pending(self):
        r = requests.get(f"{API}/auth/admin/pending")
        assert r.status_code == 401


# ---------- Notes require auth ----------
class TestNotesAuth:
    def test_notes_no_token(self):
        for path in ["/notes", "/notes/xxx"]:
            r = requests.get(f"{API}{path}")
            assert r.status_code == 401, path

    def test_notes_bad_token(self):
        r = requests.get(f"{API}/notes", headers={"Authorization": "Bearer bad.token.here"})
        assert r.status_code == 401

    def test_pdf_parse_no_token(self):
        with open(SAMPLE_PDF, "rb") as f:
            r = requests.post(f"{API}/pdf/parse", files={"file": ("s.pdf", f, "application/pdf")})
        assert r.status_code == 401


# ---------- PDF parse + scoping ----------
class TestNotesScoping:
    def test_pdf_parse_and_isolation(self, user_a, user_b, admin_h):
        # Parse under A
        with open(SAMPLE_PDF, "rb") as f:
            r = requests.post(f"{API}/pdf/parse", headers=user_a["h"],
                              files={"file": ("s.pdf", f, "application/pdf")})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["created_count"] == 4, f"expected 4 notes, got {data['created_count']}"
        # 1 alphanumeric skipped
        assert len(data.get("skipped_wr", [])) >= 1
        assert all(not w.isdigit() for w in data["skipped_wr"])
        notes = data["notes"]
        assert all(n["user_id"] == user_a["id"] for n in notes)
        # note_text sanity: contains WR line
        for n in notes:
            assert n["note_text"].startswith(f"WR: {n['wr']}")

        # A sees them
        rA = requests.get(f"{API}/notes", headers=user_a["h"])
        assert rA.status_code == 200
        ids_a = {n["id"] for n in rA.json()}
        assert all(n["id"] in ids_a for n in notes)

        # B does NOT see them
        rB = requests.get(f"{API}/notes", headers=user_b["h"])
        assert rB.status_code == 200
        ids_b = {n["id"] for n in rB.json()}
        assert not (ids_a & ids_b)

        target_id = notes[0]["id"]
        # B cannot GET
        assert requests.get(f"{API}/notes/{target_id}", headers=user_b["h"]).status_code == 404
        # B cannot PATCH
        assert requests.patch(f"{API}/notes/{target_id}", headers=user_b["h"],
                              json={"cliente": "hax"}).status_code == 404
        # B cannot DELETE
        assert requests.delete(f"{API}/notes/{target_id}", headers=user_b["h"]).status_code == 404
        # B cannot upload photo
        r = requests.post(f"{API}/notes/{target_id}/photos", headers=user_b["h"],
                          files=[("files", ("x.jpg", b"fakejpg", "image/jpeg"))])
        assert r.status_code == 404
        # B cannot regenerate
        assert requests.post(f"{API}/notes/{target_id}/regenerate", headers=user_b["h"]).status_code == 404

        # Bulk-delete: mix A ids + B nonexistent id; call from B → 0 deleted
        rBD = requests.post(f"{API}/notes/bulk-delete", headers=user_b["h"],
                            json={"ids": list(ids_a)})
        assert rBD.status_code == 200 and rBD.json()["deleted"] == 0

        # A still sees notes
        rA2 = requests.get(f"{API}/notes", headers=user_a["h"])
        assert len({n["id"] for n in rA2.json()} & ids_a) == len(ids_a)

        # A can bulk-delete
        rBD2 = requests.post(f"{API}/notes/bulk-delete", headers=user_a["h"],
                             json={"ids": list(ids_a)})
        assert rBD2.status_code == 200
        assert rBD2.json()["deleted"] == len(ids_a)


# ---------- Admin cascade delete ----------
class TestAdminCascade:
    def test_delete_user_cascades_notes(self, admin_h):
        email = _u("cascade")
        pw = "abcdef1"
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": pw})
        uid = r.json()["id"]
        requests.post(f"{API}/auth/admin/approve/{uid}", headers=admin_h)
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        with open(SAMPLE_PDF, "rb") as f:
            pr = requests.post(f"{API}/pdf/parse", headers=h,
                               files={"file": ("s.pdf", f, "application/pdf")})
        assert pr.status_code == 200
        assert pr.json()["created_count"] == 4
        # Delete user
        dr = requests.delete(f"{API}/auth/admin/users/{uid}", headers=admin_h)
        assert dr.status_code == 200
        # Cannot login
        assert requests.post(f"{API}/auth/login", json={"email": email, "password": pw}).status_code == 401
        # Token now invalid (user gone → 401)
        assert requests.get(f"{API}/notes", headers=h).status_code == 401
