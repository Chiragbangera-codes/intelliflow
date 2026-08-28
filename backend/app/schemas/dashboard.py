"""
Dashboard statistics Pydantic schemas.

Dashboard stats only include metrics that can be answered from tables
created in Milestones 1-3. Revenue, workflow, AI, and notification stats
belong to future milestones (5-10) and are deliberately excluded.

Per PRD.md §11 (Dashboard): "Document statistics", "Workflow statistics" —
only document and employee/department counts are available at this milestone.
"""

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    """
    Key metrics for the authenticated dashboard.

    Only includes counts answerable from M1-3 schema:
      - departments: active department count
      - employees:   active employee profile count
      - documents:   documents owned by this user (or all, for admin/hr)
    """

    total_departments: int
    total_employees: int
    total_documents: int
