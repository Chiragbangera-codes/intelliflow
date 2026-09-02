"""
Notifications API routes — Phase 10.

Endpoints:
  POST   /api/v1/notifications            — Create & deliver a notification (Admin/Manager)
  GET    /api/v1/notifications            — List own notifications (all authenticated)
  GET    /api/v1/notifications/count      — Get unread count (all authenticated)
  GET    /api/v1/notifications/{id}       — Get a single notification (owner or Admin)
  PATCH  /api/v1/notifications/{id}/read  — Mark single notification as read (owner)
  PATCH  /api/v1/notifications/read-all  — Mark all notifications as read (owner)
  DELETE /api/v1/notifications/{id}       — Delete a notification (owner or Admin)

IMPORTANT: /count and /read-all MUST be declared before /{id} so FastAPI
does not interpret "count" and "read-all" as UUID path parameters.

Route handlers are thin: validate → delegate to NotificationService → respond.
Business logic and RBAC enforcement live in the service layer.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.notification import NotificationChannel
from app.models.user import User
from app.schemas.notification import NotificationCreate
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def _get_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    """Provide a NotificationService with the injected DB session."""
    return NotificationService(db)


def _get_ip(request: Request) -> str | None:
    """Extract the client IP from the request for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ---------------------------------------------------------------------------
# POST /notifications — Create notification (Admin / Manager only)
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create notification",
    description=(
        "Create and optionally deliver a notification for a specific user. "
        "Requires Admin or Manager role. "
        "For channel='email', SMTP delivery is attempted after the record is persisted. "
        "For channel='sms', the record is saved but no external delivery is made "
        "(no SMS provider is configured). "
        "For channel='in_app', the notification is persisted for polling."
    ),
    responses={
        201: {"description": "Notification created."},
        401: {"description": "Not authenticated."},
        403: {"description": "Insufficient role."},
        404: {"description": "Recipient user not found."},
        422: {"description": "Validation error."},
    },
)
async def create_notification(
    data: NotificationCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """Create and deliver a notification. Admin/Manager only."""
    notification = await svc.create_notification(
        data,
        actor=current_user,
        ip_address=_get_ip(request),
    )
    return {
        "success": True,
        "message": "Notification created successfully.",
        "data": notification.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# GET /notifications/count — Unread count  (MUST be before /{id})
# ---------------------------------------------------------------------------


@router.get(
    "/count",
    status_code=status.HTTP_200_OK,
    summary="Get unread notification count",
    description="Returns the number of unread notifications for the authenticated user.",
    responses={
        200: {"description": "Unread count returned."},
        401: {"description": "Not authenticated."},
    },
)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """Return the authenticated user's unread notification count."""
    result = await svc.get_unread_count(actor=current_user)
    return {
        "success": True,
        "message": "Unread count retrieved.",
        "data": result.model_dump(),
    }


# ---------------------------------------------------------------------------
# PATCH /notifications/read-all — Mark all as read  (MUST be before /{id})
# ---------------------------------------------------------------------------


@router.patch(
    "/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
    description="Marks all unread notifications for the authenticated user as read.",
    responses={
        200: {"description": "All notifications marked as read."},
        401: {"description": "Not authenticated."},
    },
)
async def mark_all_read(
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """Mark all of the current user's notifications as read."""
    result = await svc.mark_all_read(actor=current_user, ip_address=_get_ip(request))
    return {
        "success": True,
        "message": f"{result.updated} notification(s) marked as read.",
        "data": result.model_dump(),
    }


# ---------------------------------------------------------------------------
# GET /notifications — List notifications
# ---------------------------------------------------------------------------


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List notifications",
    description=(
        "Returns a paginated list of the authenticated user's notifications. "
        "Use unread_only=true to filter to unread items. "
        "Use channel= to filter by delivery channel."
    ),
    responses={
        200: {"description": "Notifications retrieved."},
        401: {"description": "Not authenticated."},
    },
)
async def list_notifications(
    skip: int = Query(default=0, ge=0, description="Records to skip."),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return."),
    unread_only: bool = Query(default=False, description="Return only unread notifications."),
    channel: NotificationChannel | None = Query(default=None, description="Filter by channel."),
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """List the authenticated user's notifications with optional filtering."""
    result = await svc.list_notifications(
        actor=current_user,
        skip=skip,
        limit=limit,
        unread_only=unread_only,
        channel=channel,
    )
    return {
        "success": True,
        "message": "Notifications retrieved successfully.",
        "data": [n.model_dump(mode="json") for n in result.data],
        "meta": result.meta,
        "unread_count": result.unread_count,
    }


# ---------------------------------------------------------------------------
# GET /notifications/{id} — Get single notification
# ---------------------------------------------------------------------------


@router.get(
    "/{notification_id}",
    status_code=status.HTTP_200_OK,
    summary="Get notification",
    description="Returns a single notification. Admin may access any; others only their own.",
    responses={
        200: {"description": "Notification retrieved."},
        401: {"description": "Not authenticated."},
        404: {"description": "Notification not found or not accessible."},
    },
)
async def get_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """Retrieve a notification by ID."""
    notification = await svc.get_notification(notification_id, actor=current_user)
    return {
        "success": True,
        "message": "Notification retrieved successfully.",
        "data": notification.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# PATCH /notifications/{id}/read — Mark single notification as read
# ---------------------------------------------------------------------------


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark notification as read",
    description="Marks a single notification as read. Only the owner may perform this action.",
    responses={
        200: {"description": "Notification marked as read."},
        401: {"description": "Not authenticated."},
        404: {"description": "Notification not found."},
    },
)
async def mark_read(
    notification_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> dict[str, Any]:
    """Mark a single notification as read."""
    notification = await svc.mark_read(
        notification_id,
        actor=current_user,
        ip_address=_get_ip(request),
    )
    return {
        "success": True,
        "message": "Notification marked as read.",
        "data": notification.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# DELETE /notifications/{id} — Delete a notification
# ---------------------------------------------------------------------------


@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete notification",
    description="Deletes a notification. Admin may delete any; others only their own.",
    responses={
        204: {"description": "Notification deleted."},
        401: {"description": "Not authenticated."},
        404: {"description": "Notification not found or not owned."},
    },
)
async def delete_notification(
    notification_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    svc: NotificationService = Depends(_get_service),
) -> Response:
    """Delete a notification by ID."""
    await svc.delete_notification(
        notification_id,
        actor=current_user,
        ip_address=_get_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
