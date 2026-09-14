"""Backend tests for free-form tipo tag feature on /api/inventory/serials + /api/inventory/tags."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # Fallback attempt to read frontend/.env
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                    break
    except Exception:
        pass

ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASSWORD = "Mucchetta4!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def created_serials():
    return []


def _delete(sid, headers):
    try:
        requests.delete(f"{BASE_URL}/api/inventory/serials/{sid}", headers=headers, timeout=10)
    except Exception:
        pass


def test_tags_endpoint_200_and_sorted(headers):
    r = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tags" in data and isinstance(data["tags"], list)
    assert data["tags"] == sorted(data["tags"])
    # no empty strings
    assert "" not in data["tags"]


def test_tags_endpoint_requires_auth():
    r = requests.get(f"{BASE_URL}/api/inventory/tags", timeout=10)
    assert r.status_code in (401, 403)


def test_create_serial_with_freeform_tipo(headers, created_serials):
    ts = int(time.time())
    payload = {"serial": f"TEST_SFP_{ts}", "tipo": "SFP", "note": "test"}
    r = requests.post(f"{BASE_URL}/api/inventory/serials", headers=headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tipo"] == "SFP"
    assert item["serial"] == payload["serial"]
    created_serials.append(item["id"])
    # Verify tags endpoint includes it
    r2 = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15)
    assert r2.status_code == 200
    assert "SFP" in r2.json()["tags"]


def test_create_serial_with_empty_tipo(headers, created_serials):
    ts = int(time.time())
    payload = {"serial": f"TEST_EMPTY_{ts}", "tipo": "", "note": ""}
    r = requests.post(f"{BASE_URL}/api/inventory/serials", headers=headers, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["tipo"] == ""
    created_serials.append(item["id"])
    r2 = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15)
    assert "" not in r2.json()["tags"]


def test_patch_serial_tipo_updates_and_tags(headers, created_serials):
    ts = int(time.time())
    # Create a unique tag serial
    payload = {"serial": f"TEST_PATCH_{ts}", "tipo": f"UniqueOld_{ts}"}
    r = requests.post(f"{BASE_URL}/api/inventory/serials", headers=headers, json=payload, timeout=15)
    assert r.status_code == 200
    sid = r.json()["id"]
    created_serials.append(sid)

    old_tag = f"UniqueOld_{ts}"
    new_tag = "Router Wi-Fi"

    tags_before = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15).json()["tags"]
    assert old_tag in tags_before

    # Patch tipo
    r2 = requests.patch(f"{BASE_URL}/api/inventory/serials/{sid}",
                        headers=headers, json={"tipo": new_tag}, timeout=15)
    assert r2.status_code == 200, r2.text

    # Verify via list
    r3 = requests.get(f"{BASE_URL}/api/inventory/serials?search={payload['serial']}",
                      headers=headers, timeout=15)
    assert r3.status_code == 200
    items = r3.json().get("items", []) if isinstance(r3.json(), dict) else r3.json()
    found = [it for it in items if it["id"] == sid]
    assert found and found[0]["tipo"] == new_tag

    tags_after = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15).json()["tags"]
    assert new_tag in tags_after
    assert old_tag not in tags_after, f"old unique tag should be gone but is in {tags_after}"


def test_bulk_serials_with_tipo(headers, created_serials):
    ts = int(time.time())
    tag = f"NuovoModelloXyz_{ts}"
    serials = [f"TEST_BULK_{ts}_{i}" for i in range(3)]
    payload = {"serials": serials, "tipo": tag}
    r = requests.post(f"{BASE_URL}/api/inventory/serials/bulk", headers=headers, json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    # Response has created items ids
    items = body.get("items", [])
    assert len(items) == 3
    for it in items:
        created_serials.append(it["id"])
        assert it["tipo"] == tag
    r2 = requests.get(f"{BASE_URL}/api/inventory/tags", headers=headers, timeout=15).json()
    assert tag in r2["tags"]


def test_cleanup(headers, created_serials):
    for sid in created_serials:
        _delete(sid, headers)
    # also cleanup TEST_ serials just in case
    r = requests.get(f"{BASE_URL}/api/inventory/serials?search=TEST_", headers=headers, timeout=15)
    if r.status_code == 200:
        j = r.json()
        items = j.get("items", []) if isinstance(j, dict) else j
        for it in items:
            if it.get("serial", "").startswith("TEST_"):
                _delete(it["id"], headers)
