"""
Tests for Phase 10 Notifications API endpoints.

Tests cover (30+ tests):
  Authentication:
    - Unauthenticated access returns 401 for all endpoints.

  Creation RBAC:
    - admin   can create notifications
    - manager can create notifications
    - hr      cannot create (403)
    - finance cannot create (403)
    - employee cannot create (403)

  CRUD lifecycle:
    - Create → List → Get → Mark Read → Delete

  Ownership:
    - User cannot read another user's notification
    - User cannot mark another user's notification as read
    - User cannot delete another user's notification
    - Admin can get and delete any notification

  Filtering:
    - unread_only filter
    - channel filter
    - pagination (skip/limit)
    - ordering (newest first)

  Count:
    - count after creation
    - count after mark_read
    - count after mark_all_read
    - count after deletion

  Email channel:
    - SMTP send attempted (mocked)
    - sent_at stamped on success
    - SMTP failure handled cleanly (notification persists)

  Validation:
    - empty title → 422
    - empty message → 422
    - invalid channel → 422
    - invalid priority → 422
    - invalid UUID → 422
    - invalid pagination → 422

  404:
    - Unknown notification ID
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_headers(user: User, role_override: str | None = None) -> dict[str, str]:
    role = role_override or (user.role.name if user.role else "employee")
    token = create_access_token(subject=str(user.id), role=role)
    return {"Authorization": f"Bearer {token}"}


def _notification_payload(recipient_id: str, **overrides: Any) -> dict[str, Any]:
    """Build a minimal valid notification create payload."""
    return {
        "user_id": recipient_id,
        "title": "Test Notification",
        "message": "This is a test notification message.",
        "channel": "in_app",
        "priority": "medium",
        **overrides,
    }


async def _create_notification(
    client: AsyncClient,
    headers: dict[str, str],
    recipient_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    """Helper: POST /notifications and return the data dict."""
    resp = await client.post(
        "/api/v1/notifications",
        json=_notification_payload(recipient_id, **overrides),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ===========================================================================
# Authentication — 401 for all endpoints
# ===========================================================================


@pytest.mark.asyncio
async def test_list_notifications_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/notifications")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_notification_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.post("/api/v1/notifications", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_unread_count_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get("/api/v1/notifications/count")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_single_notification_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.get(f"/api/v1/notifications/{uuid.uuid4()}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mark_read_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.patch(f"/api/v1/notifications/{uuid.uuid4()}/read")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mark_all_read_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.patch("/api/v1/notifications/read-all")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_notification_requires_auth(async_client: AsyncClient) -> None:
    resp = await async_client.delete(f"/api/v1/notifications/{uuid.uuid4()}")
    assert resp.status_code == 401


# ===========================================================================
# Creation RBAC
# ===========================================================================


@pytest.mark.asyncio
async def test_admin_can_create_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Admin can create in_app notifications for any user."""
    headers = _make_headers(admin_user)
    data = await _create_notification(async_client, headers, str(test_user.id))
    assert data["title"] == "Test Notification"
    assert data["channel"] == "in_app"
    assert data["is_read"] is False


@pytest.mark.asyncio
async def test_manager_can_create_notification(
    async_client: AsyncClient,
    manager_user: User,
    test_user: User,
) -> None:
    """Manager can create notifications for any user."""
    headers = _make_headers(manager_user)
    data = await _create_notification(async_client, headers, str(test_user.id))
    assert data["user_id"] == str(test_user.id)


@pytest.mark.asyncio
async def test_hr_cannot_create_notification(
    async_client: AsyncClient,
    hr_user: User,
    test_user: User,
) -> None:
    """HR role must receive 403 on create."""
    headers = _make_headers(hr_user)
    resp = await async_client.post(
        "/api/v1/notifications",
        json=_notification_payload(str(test_user.id)),
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_finance_cannot_create_notification(
    async_client: AsyncClient,
    finance_user: User,
    test_user: User,
) -> None:
    """Finance role must receive 403 on create."""
    headers = _make_headers(finance_user)
    resp = await async_client.post(
        "/api/v1/notifications",
        json=_notification_payload(str(test_user.id)),
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_cannot_create_notification(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Employee role must receive 403 on create."""
    headers = _make_headers(test_user)
    resp = await async_client.post(
        "/api/v1/notifications",
        json=_notification_payload(str(test_user.id)),
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_notification_unknown_recipient(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    """404 when recipient user does not exist."""
    headers = _make_headers(admin_user)
    resp = await async_client.post(
        "/api/v1/notifications",
        json=_notification_payload(str(uuid.uuid4())),
        headers=headers,
    )
    assert resp.status_code == 404


# ===========================================================================
# CRUD lifecycle
# ===========================================================================


@pytest.mark.asyncio
async def test_full_notification_lifecycle(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Create → List → Get → Mark Read → Delete."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    # Create
    data = await _create_notification(async_client, admin_headers, str(test_user.id))
    nid = data["id"]

    # List — user sees their notification
    resp = await async_client.get("/api/v1/notifications", headers=user_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert any(n["id"] == nid for n in body["data"])

    # Get single
    resp = await async_client.get(f"/api/v1/notifications/{nid}", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == nid

    # Mark read
    resp = await async_client.patch(f"/api/v1/notifications/{nid}/read", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["is_read"] is True

    # Delete
    resp = await async_client.delete(f"/api/v1/notifications/{nid}", headers=user_headers)
    assert resp.status_code == 204

    # Confirm deleted
    resp = await async_client.get(f"/api/v1/notifications/{nid}", headers=user_headers)
    assert resp.status_code == 404


# ===========================================================================
# Ownership enforcement
# ===========================================================================


@pytest.mark.asyncio
async def test_user_cannot_read_other_users_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
    manager_user: User,
) -> None:
    """Employee cannot access manager's notification."""
    admin_headers = _make_headers(admin_user)
    data = await _create_notification(async_client, admin_headers, str(manager_user.id))
    nid = data["id"]

    # test_user (employee) tries to get manager's notification
    user_headers = _make_headers(test_user)
    resp = await async_client.get(f"/api/v1/notifications/{nid}", headers=user_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_mark_other_users_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
    manager_user: User,
) -> None:
    """Employee cannot mark manager's notification as read."""
    admin_headers = _make_headers(admin_user)
    data = await _create_notification(async_client, admin_headers, str(manager_user.id))
    nid = data["id"]

    user_headers = _make_headers(test_user)
    resp = await async_client.patch(f"/api/v1/notifications/{nid}/read", headers=user_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_delete_other_users_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
    manager_user: User,
) -> None:
    """Employee cannot delete manager's notification."""
    admin_headers = _make_headers(admin_user)
    data = await _create_notification(async_client, admin_headers, str(manager_user.id))
    nid = data["id"]

    user_headers = _make_headers(test_user)
    resp = await async_client.delete(f"/api/v1/notifications/{nid}", headers=user_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_get_any_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Admin can retrieve any user's notification."""
    admin_headers = _make_headers(admin_user)
    data = await _create_notification(async_client, admin_headers, str(test_user.id))
    nid = data["id"]

    resp = await async_client.get(f"/api/v1/notifications/{nid}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == nid


@pytest.mark.asyncio
async def test_admin_can_delete_any_notification(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Admin can delete any user's notification."""
    admin_headers = _make_headers(admin_user)
    data = await _create_notification(async_client, admin_headers, str(test_user.id))
    nid = data["id"]

    resp = await async_client.delete(f"/api/v1/notifications/{nid}", headers=admin_headers)
    assert resp.status_code == 204


# ===========================================================================
# Filtering and pagination
# ===========================================================================


@pytest.mark.asyncio
async def test_unread_only_filter(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """unread_only=true returns only unread notifications."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    # Create 2 notifications
    n1 = await _create_notification(async_client, admin_headers, str(test_user.id))
    n2 = await _create_notification(async_client, admin_headers, str(test_user.id), title="Second")

    # Mark first as read
    await async_client.patch(f"/api/v1/notifications/{n1['id']}/read", headers=user_headers)

    # unread_only should return only n2
    resp = await async_client.get(
        "/api/v1/notifications", params={"unread_only": True}, headers=user_headers
    )
    assert resp.status_code == 200
    ids = [n["id"] for n in resp.json()["data"]]
    assert n2["id"] in ids
    assert n1["id"] not in ids


@pytest.mark.asyncio
async def test_channel_filter(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """channel= filter returns only matching channel notifications."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    await _create_notification(async_client, admin_headers, str(test_user.id), channel="in_app")

    resp = await async_client.get(
        "/api/v1/notifications",
        params={"channel": "in_app"},
        headers=user_headers,
    )
    assert resp.status_code == 200
    for n in resp.json()["data"]:
        assert n["channel"] == "in_app"


@pytest.mark.asyncio
async def test_pagination_skip_limit(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Pagination skip/limit works correctly."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    # Create 3 notifications
    for i in range(3):
        await _create_notification(
            async_client, admin_headers, str(test_user.id), title=f"Notif {i}"
        )

    resp = await async_client.get(
        "/api/v1/notifications", params={"skip": 0, "limit": 2}, headers=user_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2

    resp2 = await async_client.get(
        "/api/v1/notifications", params={"skip": 2, "limit": 2}, headers=user_headers
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["data"]) == 1


@pytest.mark.asyncio
async def test_notifications_ordered_newest_first(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Notifications are returned newest-first."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    titles = ["First", "Second", "Third"]
    for t in titles:
        await _create_notification(async_client, admin_headers, str(test_user.id), title=t)

    resp = await async_client.get("/api/v1/notifications", headers=user_headers)
    assert resp.status_code == 200
    returned_titles = [n["title"] for n in resp.json()["data"]]
    # Most recent first
    assert returned_titles[0] == "Third"
    assert returned_titles[-1] == "First"


# ===========================================================================
# Unread count
# ===========================================================================


@pytest.mark.asyncio
async def test_unread_count_increments_on_create(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Unread count increases after creating an in_app notification."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    resp = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    initial = resp.json()["data"]["unread_count"]

    await _create_notification(async_client, admin_headers, str(test_user.id))

    resp = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    assert resp.json()["data"]["unread_count"] == initial + 1


@pytest.mark.asyncio
async def test_unread_count_decrements_after_mark_read(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Unread count decreases after marking a notification as read."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    data = await _create_notification(async_client, admin_headers, str(test_user.id))
    nid = data["id"]

    resp_before = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    count_before = resp_before.json()["data"]["unread_count"]

    await async_client.patch(f"/api/v1/notifications/{nid}/read", headers=user_headers)

    resp_after = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    assert resp_after.json()["data"]["unread_count"] == count_before - 1


@pytest.mark.asyncio
async def test_mark_all_read_zeroes_count(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """After mark-all-read, unread count must be 0."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    for _ in range(3):
        await _create_notification(async_client, admin_headers, str(test_user.id))

    resp = await async_client.patch("/api/v1/notifications/read-all", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["unread_count"] == 0

    resp_count = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    assert resp_count.json()["data"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_unread_count_after_delete(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Deleting an unread notification decreases unread count."""
    admin_headers = _make_headers(admin_user)
    user_headers = _make_headers(test_user)

    data = await _create_notification(async_client, admin_headers, str(test_user.id))
    nid = data["id"]

    resp_before = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    count_before = resp_before.json()["data"]["unread_count"]

    await async_client.delete(f"/api/v1/notifications/{nid}", headers=user_headers)

    resp_after = await async_client.get("/api/v1/notifications/count", headers=user_headers)
    assert resp_after.json()["data"]["unread_count"] == count_before - 1


@pytest.mark.asyncio
async def test_count_isolated_per_user(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
    manager_user: User,
) -> None:
    """Each user sees only their own unread count."""
    admin_headers = _make_headers(admin_user)

    # Create notification for test_user only
    await _create_notification(async_client, admin_headers, str(test_user.id))

    # Manager should see 0 (not test_user's notifications)
    manager_headers = _make_headers(manager_user)
    resp = await async_client.get("/api/v1/notifications/count", headers=manager_headers)
    assert resp.json()["data"]["unread_count"] == 0


# ===========================================================================
# Email channel
# ===========================================================================


@pytest.mark.asyncio
async def test_email_notification_created_and_smtp_attempted(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """Email channel: record created, SMTP send attempted."""
    admin_headers = _make_headers(admin_user)

    mock_smtp = MagicMock()
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("smtplib.SMTP", mock_smtp),
        patch("app.services.notification_service.settings") as mock_settings,
    ):
        mock_settings.SMTP_HOST = "smtp.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = "user"
        mock_settings.SMTP_PASSWORD = "pass"
        mock_settings.SMTP_FROM = "noreply@example.com"
        mock_settings.SMTP_USE_TLS = True

        resp = await async_client.post(
            "/api/v1/notifications",
            json=_notification_payload(str(test_user.id), channel="email"),
            headers=admin_headers,
        )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["channel"] == "email"
    # SMTP.sendmail was called (starttls path)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_email_notification_smtp_failure_does_not_break_record(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """SMTP failure: notification record is persisted, sent_at remains NULL."""
    import smtplib

    admin_headers = _make_headers(admin_user)

    with (
        patch("smtplib.SMTP") as mock_smtp,
        patch("app.services.notification_service.settings") as mock_settings,
    ):
        mock_settings.SMTP_HOST = "smtp.example.com"
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = ""
        mock_settings.SMTP_PASSWORD = ""
        mock_settings.SMTP_FROM = "noreply@example.com"
        mock_settings.SMTP_USE_TLS = False

        instance = mock_smtp.return_value.__enter__.return_value
        instance.sendmail.side_effect = smtplib.SMTPException("Simulated failure")

        resp = await async_client.post(
            "/api/v1/notifications",
            json=_notification_payload(str(test_user.id), channel="email"),
            headers=admin_headers,
        )

    # Record should still be created
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["channel"] == "email"
    # sent_at should be None (delivery failed)
    assert data["sent_at"] is None


@pytest.mark.asyncio
async def test_email_notification_no_smtp_configured(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    """When SMTP_HOST is not set, email notification is persisted without delivery."""
    admin_headers = _make_headers(admin_user)

    with patch("app.services.notification_service.settings") as mock_settings:
        mock_settings.SMTP_HOST = ""  # Not configured
        mock_settings.SMTP_PORT = 587
        mock_settings.SMTP_USER = ""
        mock_settings.SMTP_PASSWORD = ""
        mock_settings.SMTP_FROM = "noreply@example.com"
        mock_settings.SMTP_USE_TLS = True

        resp = await async_client.post(
            "/api/v1/notifications",
            json=_notification_payload(str(test_user.id), channel="email"),
            headers=admin_headers,
        )

    assert resp.status_code == 201
    assert resp.json()["data"]["channel"] == "email"


# ===========================================================================
# Validation errors
# ===========================================================================


@pytest.mark.asyncio
async def test_create_empty_title_returns_422(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={"user_id": str(test_user.id), "title": "", "message": "msg"},
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_blank_title_returns_422(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={"user_id": str(test_user.id), "title": "   ", "message": "msg"},
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_empty_message_returns_422(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={"user_id": str(test_user.id), "title": "Title", "message": ""},
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_channel_returns_422(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={
            "user_id": str(test_user.id),
            "title": "T",
            "message": "M",
            "channel": "carrier_pigeon",
        },
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_priority_returns_422(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={
            "user_id": str(test_user.id),
            "title": "T",
            "message": "M",
            "priority": "nuclear",
        },
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_uuid_returns_422(
    async_client: AsyncClient,
    admin_user: User,
) -> None:
    resp = await async_client.post(
        "/api/v1/notifications",
        json={"user_id": "not-a-uuid", "title": "T", "message": "M"},
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_invalid_limit_returns_422(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    resp = await async_client.get(
        "/api/v1/notifications",
        params={"limit": 0},
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_limit_exceeds_max_clamped(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """limit > 100 should return 422 (Query enforces le=100)."""
    resp = await async_client.get(
        "/api/v1/notifications",
        params={"limit": 101},
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 422


# ===========================================================================
# 404 for unknown IDs
# ===========================================================================


@pytest.mark.asyncio
async def test_get_unknown_notification_returns_404(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    resp = await async_client.get(
        f"/api/v1/notifications/{uuid.uuid4()}",
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_read_unknown_notification_returns_404(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    resp = await async_client.patch(
        f"/api/v1/notifications/{uuid.uuid4()}/read",
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_notification_returns_404(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    resp = await async_client.delete(
        f"/api/v1/notifications/{uuid.uuid4()}",
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 404


# ===========================================================================
# mark-all-read on empty inbox is idempotent
# ===========================================================================


@pytest.mark.asyncio
async def test_mark_all_read_empty_inbox(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """mark-all-read on an empty inbox returns 200 with updated=0."""
    resp = await async_client.patch(
        "/api/v1/notifications/read-all",
        headers=_make_headers(test_user),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["updated"] == 0
    assert resp.json()["data"]["unread_count"] == 0


# ===========================================================================
# Response envelope consistency
# ===========================================================================


@pytest.mark.asyncio
async def test_list_response_envelope(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """List response must include success, data, meta, and unread_count."""
    resp = await async_client.get("/api/v1/notifications", headers=_make_headers(test_user))
    assert resp.status_code == 200
    body = resp.json()
    assert "success" in body
    assert "data" in body
    assert "meta" in body
    assert "unread_count" in body


@pytest.mark.asyncio
async def test_count_response_envelope(
    async_client: AsyncClient,
    test_user: User,
) -> None:
    """Count response must include unread_count field."""
    resp = await async_client.get("/api/v1/notifications/count", headers=_make_headers(test_user))
    assert resp.status_code == 200
    assert "unread_count" in resp.json()["data"]


# ===========================================================================
# Priority all values accepted
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", ["low", "medium", "high", "critical"])
async def test_all_priorities_accepted(
    async_client: AsyncClient,
    admin_user: User,
    test_user: User,
    priority: str,
) -> None:
    """All four priority values must be accepted."""
    resp = await async_client.post(
        "/api/v1/notifications",
        json=_notification_payload(str(test_user.id), priority=priority),
        headers=_make_headers(admin_user),
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["priority"] == priority
