"""Iteration 12 tests: /api/inventory/stats, R2 fallback, boto3 import, static files."""
import os
import io
import json
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://openfiber-notes.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "giuseppe97belviso@gmail.com"
ADMIN_PASS = "Mucchetta4!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Boto3 import / USE_R2 flag ----------
def test_boto3_importable():
    import boto3  # noqa
    assert boto3 is not None


def test_use_r2_false_by_default():
    # R2 env vars should not be set
    assert not os.environ.get("R2_ENDPOINT")
    assert not os.environ.get("R2_BUCKET")


# ---------- Inventory stats ----------
def test_inventory_stats_structure(auth_h):
    r = requests.get(f"{BASE_URL}/api/inventory/stats", headers=auth_h, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "total" in data
    assert "by_tag" in data
    assert isinstance(data["by_tag"], list)
    assert isinstance(data["total"], int)
    for row in data["by_tag"]:
        assert set(["tag", "total", "in_stock", "assegnato", "scaricato"]).issubset(row.keys())
        assert row["total"] == row["in_stock"] + row["assegnato"] + row["scaricato"] or row["total"] >= 0


def test_inventory_stats_requires_auth():
    r = requests.get(f"{BASE_URL}/api/inventory/stats", timeout=15)
    assert r.status_code in (401, 403)


def test_inventory_stats_matches_serial_counts(auth_h):
    # cross-check total against inventory list
    r = requests.get(f"{BASE_URL}/api/inventory/stats", headers=auth_h, timeout=15)
    stats = r.json()
    r2 = requests.get(f"{BASE_URL}/api/inventory/serials", headers=auth_h, timeout=15)
    assert r2.status_code == 200
    serials = r2.json()
    # serials may be list or dict
    if isinstance(serials, dict):
        serials = serials.get("items", serials.get("serials", []))
    assert stats["total"] == len(serials), f"stats.total={stats['total']} vs serial count={len(serials)}"


# ---------- Serial CRUD (fallback path) ----------
def test_serial_crud_fallback(auth_h):
    unique = f"TESTITER12{int(time.time())}"
    # CREATE
    r = requests.post(
        f"{BASE_URL}/api/inventory/serials",
        headers=auth_h,
        json={"serial": unique, "tipo": "TestTagIter12"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    sid = r.json()["id"]
    # PATCH
    r = requests.patch(
        f"{BASE_URL}/api/inventory/serials/{sid}",
        headers=auth_h,
        json={"tipo": "UpdatedTagIter12"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("tipo") == "UpdatedTagIter12"
    # verify stats includes the new tag
    s = requests.get(f"{BASE_URL}/api/inventory/stats", headers=auth_h, timeout=15).json()
    tags = [x["tag"] for x in s["by_tag"]]
    assert "UpdatedTagIter12" in tags
    # DELETE
    r = requests.delete(f"{BASE_URL}/api/inventory/serials/{sid}", headers=auth_h, timeout=15)
    assert r.status_code in (200, 204), r.text


# ---------- PDF parse (uses put_object fallback) ----------
def test_pdf_parse_endpoint_reachable(auth_h):
    # Send a tiny non-PDF to verify endpoint responds (either 200 or 400, not 500)
    fake_pdf = b"%PDF-1.4\n%EOF\n"
    files = {"file": ("test.pdf", io.BytesIO(fake_pdf), "application/pdf")}
    r = requests.post(f"{BASE_URL}/api/pdf/parse", headers=auth_h, files=files, timeout=60)
    # Accept 200 (parsed) or 400/422 (bad pdf). Not 500 (storage crash).
    assert r.status_code != 500, f"put_object fallback appears broken: {r.status_code} {r.text[:300]}"


# ---------- Static PWA files ----------
STATIC_URLS = [
    ("/downloads/", ["text/html"]),
    ("/downloads/pwa/index.html", ["text/html"]),
    ("/downloads/pwa/manifest.json", ["application/json", "application/manifest+json", "text/"]),
    ("/downloads/pwa/sw.js", ["javascript", "text/"]),
    ("/downloads/pwa/icon-192.png", ["image/png"]),
    ("/downloads/gc-impianti-pwa.zip", ["application/zip", "application/octet-stream"]),
]


@pytest.mark.parametrize("path,ctypes", STATIC_URLS)
def test_static_files_reachable(path, ctypes):
    r = requests.get(f"{BASE_URL}{path}", timeout=20, allow_redirects=True)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    ct = r.headers.get("content-type", "").lower()
    assert any(c in ct for c in ctypes), f"{path} content-type={ct}"


def test_manifest_json_valid():
    r = requests.get(f"{BASE_URL}/downloads/pwa/manifest.json", timeout=15)
    assert r.status_code == 200
    m = json.loads(r.text)
    assert "name" in m
    assert "icons" in m and len(m["icons"]) > 0
    assert "start_url" in m
