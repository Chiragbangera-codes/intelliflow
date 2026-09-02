"""
Dashboard statistics Pydantic schemas.

Milestone 4 additions:
  total_departments, total_employees, total_documents.

Milestone 8 additions:
  total_workflows     — active (non-deleted, is_active=True) workflow count.
  pending_executions  — executions in PENDING or RUNNING state.
"""

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    """
    Key metrics for the authenticated dashboard.

    Only includes counts answerable from the existing schema.
    """

    total_departments: int
    total_employees: int
    total_documents: int
    # Milestone 8 additions
    total_workflows: int = 0
    pending_executions: int = 0
