"""Iteration 18 — Caposquadra role + Archive/Purge endpoints."""
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


def test_me_returns_is_team_leader_flag():
    data = _login(SUPER_EMAIL, SUPER_PW)
    assert "is_team_leader" in data["user"]
    me = requests.get(f"{BASE}/auth/me", headers=_auth(data["access_token"]), timeout=10).json()
    assert "is_team_leader" in me


def test_only_leader_can_set_team_partner():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    ts = int(time.time() * 1000)
    # Two techs
    leader_reg = _register(f"iter18_lead_{ts}@example.com", "Test1234!", "Lead")
    partner_reg = _register(f"iter18_part_{ts}@example.com", "Test1234!", "Part")
    lid, pid = leader_reg["id"], partner_reg["id"]
    requests.post(f"{BASE}/auth/admin/approve/{lid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)
    requests.post(f"{BASE}/auth/admin/approve/{pid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)

    # Partner (non-leader) → forbidden
    p_tok = _login(f"iter18_part_{ts}@example.com", "Test1234!")["access_token"]
    r = requests.post(f"{BASE}/team/today", json={"partner_user_id": lid}, headers=_auth(p_tok), timeout=10)
    assert r.status_code == 403, r.text

    # Make leader → team leader
    r = requests.post(f"{BASE}/auth/admin/set-team-leader/{lid}", json={"is_team_leader": True}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200 and r.json()["is_team_leader"] is True

    # Leader can now set the partner
    l_tok = _login(f"iter18_lead_{ts}@example.com", "Test1234!")["access_token"]
    me = requests.get(f"{BASE}/auth/me", headers=_auth(l_tok), timeout=10).json()
    assert me["is_team_leader"] is True

    r = requests.post(f"{BASE}/team/today", json={"partner_user_id": pid}, headers=_auth(l_tok), timeout=10)
    assert r.status_code == 200
    assert r.json()["partner_ids"] == [pid]

    # Partner now sees leader as partner (bidirectional)
    r = requests.get(f"{BASE}/team/today", headers=_auth(p_tok), timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["partner"] is not None
    assert d["partner"]["id"] == lid

    # Remove leader flag → clears their partnerships too
    r = requests.post(f"{BASE}/auth/admin/set-team-leader/{lid}", json={"is_team_leader": False}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{BASE}/team/today", headers=_auth(p_tok), timeout=10).json()
    assert r["partner"] is None

    # Cleanup
    requests.delete(f"{BASE}/auth/admin/users/{lid}", headers=_auth(super_tok), timeout=10)
    requests.delete(f"{BASE}/auth/admin/users/{pid}", headers=_auth(super_tok), timeout=10)


def test_archive_export_and_purge():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]

    # Export full
    r = requests.get(f"{BASE}/admin/archive/export", headers=_auth(super_tok), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "collections" in d
    for k in ("notes", "serial_events", "notifications", "vacations", "users", "serials"):
        assert k in d["collections"]

    # Export filtered (before 2020) — should be near-empty
    r = requests.get(f"{BASE}/admin/archive/export", params={"before": "2020-01-01"}, headers=_auth(super_tok), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["before"] == "2020-01-01"
    assert d["collections"]["notes"] == []

    # Bad date → 400
    r = requests.get(f"{BASE}/admin/archive/export", params={"before": "not-a-date"}, headers=_auth(super_tok), timeout=10)
    assert r.status_code == 400

    # Purge with before=2020 (should delete zero)
    r = requests.post(f"{BASE}/admin/archive/purge",
                     json={"before": "2020-01-01", "collections": ["notes", "notifications"]},
                     headers=_auth(super_tok), timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["deleted"]["notes"] == 0
    assert d["deleted"]["notifications"] == 0

    # Invalid collection → 400
    r = requests.post(f"{BASE}/admin/archive/purge",
                     json={"before": "2020-01-01", "collections": ["users"]},
                     headers=_auth(super_tok), timeout=10)
    assert r.status_code == 400


def test_archive_requires_admin():
    super_tok = _login(SUPER_EMAIL, SUPER_PW)["access_token"]
    ts = int(time.time() * 1000)
    reg = _register(f"iter18_nonadmin_{ts}@example.com", "Test1234!")
    uid = reg["id"]
    requests.post(f"{BASE}/auth/admin/approve/{uid}", json={"role": "user"}, headers=_auth(super_tok), timeout=10)

    tok = _login(f"iter18_nonadmin_{ts}@example.com", "Test1234!")["access_token"]
    r = requests.get(f"{BASE}/admin/archive/export", headers=_auth(tok), timeout=10)
    assert r.status_code == 403

    r = requests.post(f"{BASE}/admin/archive/purge", json={"before": "2020-01-01"}, headers=_auth(tok), timeout=10)
    assert r.status_code == 403

    # Cleanup
    requests.delete(f"{BASE}/auth/admin/users/{uid}", headers=_auth(super_tok), timeout=10)
