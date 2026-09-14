"""Iteration 17 — Serial dropdown fix + Admin promote/demote (super-admin gating)."""
import os
import time
import requests

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001") + "/api"
SUPER_EMAIL = "giuseppe97belviso@gmail.com"
SUPER_PW = "Mucchetta4!"


def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _register(email, pw, name="T"):
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "password": pw, "name": name}, timeout=10)
    return r.json()


def test_me_and_login_return_is_super_admin_flag():
    data = _login(SUPER_EMAIL, SUPER_PW)
    assert data["user"]["is_super_admin"] is True
    me = requests.get(f"{BASE}/auth/me", headers=_auth(data["access_token"]), timeout=10).json()
    assert me["is_super_admin"] is True


def test_my_assigned_ignores_tipo_filter():
    """The dropdown should show all assigned serials regardless of the `tipo` query."""
    tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    r_all = requests.get(f"{BASE}/inventory/my-assigned", headers=_auth(tok), timeout=10).json()
    r_cpe = requests.get(f"{BASE}/inventory/my-assigned?tipo=CPE", headers=_auth(tok), timeout=10).json()
    r_ont = requests.get(f"{BASE}/inventory/my-assigned?tipo=ONT", headers=_auth(tok), timeout=10).json()
    # Regardless of tipo filter, the response is identical (filter is ignored now)
    assert len(r_cpe) == len(r_all) == len(r_ont)


def test_promote_and_demote_flow():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    ts = int(time.time() * 1000)
    email = f"promo_{ts}@example.com"
    pw = "Test1234!"
    reg = _register(email, pw)
    uid = reg["id"]

    # Approve
    r = requests.post(f"{BASE}/auth/admin/approve/{uid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200

    # Promote to admin (as super-admin)
    r = requests.post(f"{BASE}/auth/admin/promote/{uid}", headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200 and r.json()["promoted"] is True

    # New admin can now log in
    sub = _login(email, pw)
    assert sub["user"]["role"] == "admin"
    assert sub["user"]["is_super_admin"] is False
    sub_tok = sub["access_token"]

    # Sub-admin CANNOT demote the super-admin (get super-admin id first)
    users = requests.get(f"{BASE}/auth/admin/users", headers=_auth(super_tok), timeout=10).json()
    super_id = next(u["id"] for u in users if u["email"].lower() == SUPER_EMAIL.lower())
    r = requests.post(f"{BASE}/auth/admin/demote/{super_id}", json={"role": "user"}, headers=_auth(sub_tok), timeout=10)
    assert r.status_code == 403, r.text

    # Sub-admin CANNOT demote themselves either (403 - not super-admin)
    r = requests.post(f"{BASE}/auth/admin/demote/{uid}", json={"role": "user"}, headers=_auth(sub_tok), timeout=10)
    assert r.status_code == 403

    # Super-admin CANNOT demote themselves (400 protected)
    r = requests.post(f"{BASE}/auth/admin/demote/{super_id}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 400

    # Super-admin CAN demote the sub-admin
    r = requests.post(f"{BASE}/auth/admin/demote/{uid}", json={"role": "magazzino"}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200 and r.json()["role"] == "magazzino"

    # Verify role is now magazzino
    users2 = requests.get(f"{BASE}/auth/admin/users", headers=_auth(super_tok), timeout=10).json()
    demoted = next(u for u in users2 if u["id"] == uid)
    assert demoted["role"] == "magazzino"

    # Cleanup — delete the test user
    requests.delete(f"{BASE}/auth/admin/users/{uid}", headers=_auth(super_tok), timeout=10)


def test_promote_bad_input():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    # Missing user id => 404
    r = requests.post(f"{BASE}/auth/admin/promote/nonexistent-id", headers=_auth(super_tok), timeout=10)
    assert r.status_code == 404


def test_demote_bad_role():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    ts = int(time.time() * 1000)
    email = f"badrole_{ts}@example.com"
    reg = _register(email, "Test1234!")
    uid = reg["id"]
    requests.post(f"{BASE}/auth/admin/approve/{uid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)
    requests.post(f"{BASE}/auth/admin/promote/{uid}", headers=_auth(super_tok), timeout=10)

    r = requests.post(f"{BASE}/auth/admin/demote/{uid}", json={"role": "admin"}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 400

    # Cleanup
    requests.post(f"{BASE}/auth/admin/demote/{uid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)
    requests.delete(f"{BASE}/auth/admin/users/{uid}", headers=_auth(super_tok), timeout=10)
