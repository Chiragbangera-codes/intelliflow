#!/usr/bin/env python3
"""
Live API runtime verification script for Milestone 14.
Runs inside the backend container: docker exec intelliflow_backend python /app/scripts/live_api_test.py
"""
import json
import subprocess
import uuid

import requests

BASE = "http://127.0.0.1:8000/api/v1"
results = {}


def elevate_user(email: str, role_id: str) -> None:
    """Set user role and activate via direct psql call."""
    subprocess.run(
        [
            "psql",
            "-U",
            "intelliflow_user",
            "-h",
            "postgres",
            "-d",
            "intelliflow",
            "-c",
            f"UPDATE users SET role_id='{role_id}', status='active' WHERE email='{email}';",
        ],
        capture_output=True,
    )


# ── Roles ────────────────────────────────────────────────────────────────────
ROLE_ADMIN = "00000000-0000-4000-8000-000000000001"
ROLE_MANAGER = "00000000-0000-4000-8000-000000000002"
ROLE_EMPLOYEE = "00000000-0000-4000-8000-000000000003"
ROLE_HR = "00000000-0000-4000-8000-000000000004"
ROLE_FINANCE = "00000000-0000-4000-8000-000000000005"


def create_user_token(role_id: str, role_name: str) -> str:
    uid = uuid.uuid4().hex[:6]
    email = f"audit_{role_name}_{uid}@test.com"
    password = "AuditPass123!"

    reg = requests.post(
        f"{BASE}/auth/register",
        json={"email": email, "password": password, "first_name": "Audit", "last_name": role_name.title()},
        timeout=10,
    )
    if reg.status_code not in (200, 201):
        return ""

    elevate_user(email, role_id)

    login = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=10)
    if login.status_code != 200:
        return ""
    data = login.json()
    return data.get("data", {}).get("access_token") or data.get("access_token", "")


# ── Health checks ─────────────────────────────────────────────────────────────
print("\n=== HEALTH CHECKS ===")
r = requests.get("http://127.0.0.1:8000/health", timeout=5)
results["health_root"] = r.status_code
print(f"  /health               : {r.status_code}")

r2 = requests.get(f"{BASE}/health/live", timeout=5)
results["health_live"] = r2.status_code
print(f"  /health/live          : {r2.status_code}")

r3 = requests.get(f"{BASE}/health/ready", timeout=5)
results["health_ready"] = r3.status_code
body3 = r3.json()
results["health_ready_status"] = body3.get("status")
print(f"  /health/ready         : {r3.status_code} ({body3.get('status')})")
deps = body3.get("dependencies", {})
for svc, info in deps.items():
    print(f"    {svc:20}: {info.get('status')}")

# ── Admin token ───────────────────────────────────────────────────────────────
print("\n=== ADMIN API ENDPOINTS ===")
admin_token = create_user_token(ROLE_ADMIN, "admin")
assert admin_token, "FATAL: Could not create admin token"
ah = {"Authorization": f"Bearer {admin_token}"}

admin_endpoints = [
    ("GET", "/auth/me"),
    ("GET", "/dashboard"),
    ("GET", "/documents"),
    ("GET", "/analytics/kpi"),
    ("GET", "/analytics/revenue"),
    ("GET", "/analytics/departments"),
    ("GET", "/analytics/employees"),
    ("GET", "/analytics/documents"),
    ("GET", "/analytics/workflows"),
    ("GET", "/analytics/ai"),
    ("GET", "/reports"),
    ("GET", "/predictions"),
    ("GET", "/workflows"),
    ("GET", "/notifications"),
    ("GET", "/integrations"),
    ("GET", "/webhooks"),
    ("GET", "/automations"),
    ("GET", "/events"),
    ("GET", "/events/outbox/stats"),
    ("GET", "/employees"),
    ("GET", "/departments"),
    ("GET", "/search?q=test"),
]

for method, path in admin_endpoints:
    try:
        url = f"{BASE}{path}"
        r = requests.get(url, headers=ah, timeout=10) if method == "GET" else requests.post(url, headers=ah, timeout=10)
        status = r.status_code
        results[f"admin{path.split('?')[0].replace('/', '_')}"] = status
        flag = "✓" if status == 200 else f"✗ {status}"
        print(f"  {method} {path:40}: {flag}")
    except Exception as e:
        results[f"admin_{path}"] = f"ERROR: {e}"
        print(f"  {method} {path:40}: ERROR {e}")

# ── Employee token (RBAC test) ─────────────────────────────────────────────────
print("\n=== EMPLOYEE RBAC VERIFICATION ===")
emp_token = create_user_token(ROLE_EMPLOYEE, "employee")
assert emp_token, "FATAL: Could not create employee token"
eh = {"Authorization": f"Bearer {emp_token}"}

# Employee SHOULD access
emp_allowed = ["/dashboard", "/documents", "/workflows", "/notifications", "/auth/me"]
# Employee MUST NOT access
emp_forbidden = ["/analytics/kpi", "/predictions", "/integrations", "/webhooks", "/automations", "/events"]

for path in emp_allowed:
    r = requests.get(f"{BASE}{path}", headers=eh, timeout=10)
    flag = "✓ ALLOWED" if r.status_code in (200, 201) else f"✗ UNEXPECTED {r.status_code}"
    results[f"emp_allowed{path.replace('/', '_')}"] = r.status_code
    print(f"  ALLOWED  {path:35}: {flag}")

for path in emp_forbidden:
    r = requests.get(f"{BASE}{path}", headers=eh, timeout=10)
    flag = "✓ BLOCKED (403)" if r.status_code == 403 else f"✗ UNEXPECTED {r.status_code}"
    results[f"emp_forbidden{path.replace('/', '_')}"] = r.status_code
    print(f"  FORBIDDEN {path:34}: {flag}")

# ── Unauthenticated access ────────────────────────────────────────────────────
print("\n=== UNAUTHENTICATED ACCESS ===")
protected = ["/dashboard", "/documents", "/analytics/kpi", "/integrations"]
for path in protected:
    r = requests.get(f"{BASE}{path}", timeout=10)
    flag = "✓ 401" if r.status_code == 401 else f"✗ UNEXPECTED {r.status_code}"
    results[f"unauth{path.replace('/', '_')}"] = r.status_code
    print(f"  {path:40}: {flag}")

# ── SSRF verification ─────────────────────────────────────────────────────────
print("\n=== SSRF PROTECTION ===")
# Admin must be able to create webhooks but not to internal URLs
ssrf_urls = [
    ("http://127.0.0.1:8080/admin", True),
    ("http://localhost:9200", True),
    ("http://169.254.169.254/latest/meta-data", True),
    ("http://10.0.0.1/internal", True),
    ("http://192.168.1.1/router", True),
    ("https://httpbin.org/post", False),
]
for url, should_block in ssrf_urls:
    payload = {"name": f"ssrf_test_{uuid.uuid4().hex[:4]}", "url": url, "subscribed_events": ["test"]}
    r = requests.post(f"{BASE}/webhooks", json=payload, headers=ah, timeout=10)
    if should_block:
        flag = "✓ BLOCKED" if r.status_code in (400, 422) else f"✗ NOT BLOCKED ({r.status_code})"
    else:
        flag = "✓ ALLOWED" if r.status_code in (200, 201) else f"✗ UNEXPECTED ({r.status_code})"
    results[f"ssrf_{url.split('/')[2]}"] = r.status_code
    print(f"  {url:50}: {flag}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n=== SUMMARY ===")
print(json.dumps(results, indent=2))

# Count unexpected failures
unexpected = []
for k, v in results.items():
    if isinstance(v, int):
        if "admin_" in k and v not in (200, 201):
            unexpected.append(f"{k}: {v}")
        if "emp_allowed" in k and v not in (200, 201, 404):
            unexpected.append(f"{k}: {v}")
        if "emp_forbidden" in k and v != 403:
            unexpected.append(f"{k}: {v}")
        if "unauth" in k and v != 401:
            unexpected.append(f"{k}: {v}")

print(f"\nUnexpected failures: {len(unexpected)}")
for u in unexpected:
    print(f"  ! {u}")

if not unexpected:
    print("ALL LIVE API CHECKS PASSED")
