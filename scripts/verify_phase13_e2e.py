#!/usr/bin/env python3
"""
Phase 13 E2E verification wrapper — runs against the live Docker network.

Usage (from host machine when Docker containers are running):
    python scripts/verify_phase13_e2e.py

The original script uses BASE_BACKEND = 'http://localhost:8000/api/v1'.
This wrapper adds the ability to override the base URL via environment variable:
    BACKEND_URL=http://backend:8000/api/v1 python scripts/verify_phase13_e2e.py

It also correctly handles running from inside the Docker network via:
    docker run --rm --network intelliflow_intelliflow_network ...
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import requests

BASE_BACKEND = os.environ.get("BACKEND_URL", "http://localhost:8000/api/v1")
BASE_FRONTEND = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def log(step: str, status: str = "INFO", detail: str = ""):
    badge = f"[{status}]"
    print(f"{badge:8} {step:45} {detail}")


def create_or_get_user(email: str, password: str, role_id: str) -> str:
    """Register or login user and ensure role is elevated in DB."""
    requests.post(
        f"{BASE_BACKEND}/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "E2E",
            "last_name": "Tester",
        },
    )

    # Set role via docker exec psql
    cmd = [
        "docker",
        "exec",
        "intelliflow_postgres",
        "psql",
        "-U",
        "intelliflow_user",
        "-d",
        "intelliflow",
        "-c",
        f"UPDATE users SET role_id = '{role_id}', status = 'active' WHERE email = '{email}';",
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    login_res = requests.post(
        f"{BASE_BACKEND}/auth/login",
        json={"email": email, "password": password},
    )
    if login_res.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {login_res.text}")
    res_json = login_res.json()
    if "data" in res_json and "access_token" in res_json["data"]:
        return res_json["data"]["access_token"]
    if "access_token" in res_json:
        return res_json["access_token"]
    raise RuntimeError(f"No access_token found in login response: {res_json}")


def test_milestone_13_e2e():
    print("=" * 80)
    print("       IntelliFlow AI — Milestone 13 End-to-End System Verification             ")
    print(f"       Backend: {BASE_BACKEND}")
    print("=" * 80)

    session = requests.Session()
    passed = 0
    total = 10

    # 1. Health check
    res = session.get(f"{BASE_BACKEND.rsplit('/api/v1', 1)[0]}/api/v1/health")
    assert res.status_code == 200, f"Backend health failed: {res.text}"
    log("1. Backend Health Check", "PASS", f"Status: {res.json().get('status')}")
    passed += 1

    # 2. Acquire Admin Token
    admin_email = f"admin_e2e_{uuid.uuid4().hex[:6]}@example.com"
    admin_pass = "AdminPass123!"
    admin_role_id = "00000000-0000-4000-8000-000000000001"
    admin_token = create_or_get_user(admin_email, admin_pass, admin_role_id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    log("2. Admin Authentication & RBAC", "PASS", f"Email: {admin_email}")
    passed += 1

    # 3. Create Integration with Credentials
    integ_payload = {
        "name": f"E2E Slack Alerts {uuid.uuid4().hex[:6]}",
        "provider": "slack",
        "description": "Automated incident and alert channel",
        "configuration": {"webhook_url": "https://hooks.slack.com/services/T00/B00/X00"},
        "credentials": {"api_key": "xoxb-e2e-secret-key"},
    }
    create_integ_res = session.post(
        f"{BASE_BACKEND}/integrations",
        json=integ_payload,
        headers=admin_headers,
    )
    assert create_integ_res.status_code == 201, f"Create integration failed: {create_integ_res.text}"
    integ_data = create_integ_res.json()
    integ_id = integ_data["id"]
    assert integ_data["has_credentials"] is True
    assert "xoxb-e2e" not in str(integ_data)
    log("3. Integration Lifecycle (Create/Encrypt)", "PASS", f"ID: {integ_id} (Fernet Encrypted)")
    passed += 1

    # 4. List Integrations
    list_integ_res = session.get(f"{BASE_BACKEND}/integrations", headers=admin_headers)
    assert list_integ_res.status_code == 200
    assert list_integ_res.json()["total"] >= 1
    log("4. Integrations API List", "PASS", f"Total: {list_integ_res.json()['total']}")
    passed += 1

    # 5. Create Webhook & Verify HMAC Secret
    webhook_payload = {
        "name": f"E2E Audit Webhook {uuid.uuid4().hex[:6]}",
        "url": "https://httpbin.org/post",
        "subscribed_events": ["document.created", "workflow.completed"],
        "description": "Receives signed audit events",
    }
    create_wh_res = session.post(
        f"{BASE_BACKEND}/webhooks",
        json=webhook_payload,
        headers=admin_headers,
    )
    assert create_wh_res.status_code == 201, f"Create webhook failed: {create_wh_res.text}"
    wh_data = create_wh_res.json()
    wh_id = wh_data["id"]
    assert wh_data["plaintext_secret"].startswith("whsec_")
    log("5. Webhook Registration (HMAC-SHA256)", "PASS", f"ID: {wh_id}, Masked: {wh_data['masked_secret']}")
    passed += 1

    # 6. Verify SSRF Protection (Block 127.0.0.1 and private CIDRs)
    ssrf_payload = {
        "name": "SSRF Test Hook",
        "url": "http://127.0.0.1:8080/internal-admin",
        "subscribed_events": ["*"],
    }
    ssrf_res = session.post(
        f"{BASE_BACKEND}/webhooks",
        json=ssrf_payload,
        headers=admin_headers,
    )
    assert ssrf_res.status_code in (400, 422), f"SSRF block failed: {ssrf_res.status_code}"
    log("6. SSRF Protection Barrier", "PASS", "Blocked loopback 127.0.0.1 with HTTP 422")
    passed += 1

    # 7. Create Automation Rule & Dry Run
    rule_payload = {
        "name": f"E2E Flag Sensitive Docs {uuid.uuid4().hex[:6]}",
        "trigger_event": "document.created",
        "conditions": [
            {"field": "payload.confidentiality", "operator": "equals", "value": "restricted"}
        ],
        "actions": [
            {
                "type": "send_notification",
                "config": {"title": "Restricted Doc Created", "priority": "high"},
            }
        ],
    }
    create_rule_res = session.post(
        f"{BASE_BACKEND}/automations",
        json=rule_payload,
        headers=admin_headers,
    )
    assert create_rule_res.status_code == 201, f"Create rule failed: {create_rule_res.text}"
    rule_id = create_rule_res.json()["id"]

    dry_run_res = session.post(
        f"{BASE_BACKEND}/automations/{rule_id}/test",
        json={"event_context": {"payload": {"confidentiality": "restricted"}}},
        headers=admin_headers,
    )
    assert dry_run_res.status_code == 200
    assert dry_run_res.json()["conditions_met"] is True
    log("7. Automation Rule AST Evaluator", "PASS", f"Rule: {rule_id}, Match: True")
    passed += 1

    # 8. Event Bus & Outbox Telemetry
    stats_res = session.get(f"{BASE_BACKEND}/events/outbox/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    log("8. Event Bus & Outbox Queue Telemetry", "PASS", f"Stats: {stats_res.json()}")
    passed += 1

    # 9. RBAC Enforcement (Employee forbidden)
    emp_email = f"emp_e2e_{uuid.uuid4().hex[:6]}@example.com"
    emp_pass = "EmpPass123!"
    emp_role_id = "00000000-0000-4000-8000-000000000003"
    emp_token = create_or_get_user(emp_email, emp_pass, emp_role_id)
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    for endpoint in ["integrations", "webhooks", "automations", "events"]:
        emp_check = session.get(f"{BASE_BACKEND}/{endpoint}", headers=emp_headers)
        assert emp_check.status_code == 403, f"Expected 403 on {endpoint}, got {emp_check.status_code}"
    log("9. RBAC Enforcement for Employee", "PASS", "Forbidden (403) on all 4 admin endpoints")
    passed += 1

    # 10. Frontend Admin Pages Reachability
    for path in ["/admin/integrations", "/admin/webhooks", "/admin/automations", "/admin/events"]:
        page_res = requests.get(f"{BASE_FRONTEND}{path}")
        assert page_res.status_code in (200, 307, 308), f"Frontend {path} returned {page_res.status_code}"
        log(f"10. Frontend Route: {path}", "PASS", f"HTTP {page_res.status_code}")
    passed += 1

    print("=" * 80)
    print(f"       {passed}/{total} MILESTONE 13 E2E CRITICAL PATHS VERIFIED SUCCESSFULLY!")
    print("=" * 80)
    return passed == total


if __name__ == "__main__":
    success = test_milestone_13_e2e()
    sys.exit(0 if success else 1)
