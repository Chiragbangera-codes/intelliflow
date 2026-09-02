"""
Migration: 007_integrations_event_bus — Milestone 13 tables, enums & indexes.

Revision ID: 007_integrations_event_bus
Revises:     006_security_observability
Create Date: 2026-09-01

Changes:
  1. Create enums:
     - event_status
     - webhook_delivery_status
     - integration_provider
     - integration_status
     - automation_status
  2. Create tables:
     - events
     - outbox_events
     - webhooks
     - webhook_deliveries
     - integrations
     - automation_rules
     - automation_executions
  3. Create indexes for high-throughput event processing and audit queries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic (must be <= 32 chars).
revision: str = "007_integrations_event_bus"
down_revision: str | None = "006_security_observability"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Create Enums
    postgresql.ENUM(
        "pending", "processing", "processed", "failed", "dead_letter",
        name="event_status",
    ).create(op.get_bind(), checkfirst=True)

    event_status_col = postgresql.ENUM(
        "pending", "processing", "processed", "failed", "dead_letter",
        name="event_status",
        create_type=False,
    )

    postgresql.ENUM(
        "pending", "success", "failed",
        name="webhook_delivery_status",
    ).create(op.get_bind(), checkfirst=True)

    webhook_delivery_status_col = postgresql.ENUM(
        "pending", "success", "failed",
        name="webhook_delivery_status",
        create_type=False,
    )

    postgresql.ENUM(
        "webhook", "slack", "msteams", "email", "generic_http",
        name="integration_provider",
    ).create(op.get_bind(), checkfirst=True)

    integration_provider_col = postgresql.ENUM(
        "webhook", "slack", "msteams", "email", "generic_http",
        name="integration_provider",
        create_type=False,
    )

    postgresql.ENUM(
        "active", "inactive", "error",
        name="integration_status",
    ).create(op.get_bind(), checkfirst=True)

    integration_status_col = postgresql.ENUM(
        "active", "inactive", "error",
        name="integration_status",
        create_type=False,
    )

    postgresql.ENUM(
        "success", "failure", "partial",
        name="automation_status",
    ).create(op.get_bind(), checkfirst=True)

    automation_status_col = postgresql.ENUM(
        "success", "failure", "partial",
        name="automation_status",
        create_type=False,
    )

    # 2. Table: events
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="intelliflow.core"),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("status", event_status_col, nullable=False, server_default="processed"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_events_event_type", "events", ["event_type"], unique=False)
    op.create_index("idx_events_correlation_id", "events", ["correlation_id"], unique=False)
    op.create_index("idx_events_created_at", "events", [sa.text("created_at DESC")], unique=False)
    op.create_index("idx_events_actor_id", "events", ["actor_id"], unique=False)

    # 3. Table: outbox_events
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="intelliflow.core"),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("status", event_status_col, nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_outbox_status_next_retry", "outbox_events", ["status", "next_retry_at"], unique=False)
    op.create_index("idx_outbox_created_at", "outbox_events", ["created_at"], unique=False)

    # 4. Table: webhooks
    op.create_table(
        "webhooks",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("subscribed_events", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_webhooks_is_active", "webhooks", ["is_active"], unique=False)
    op.create_index("idx_webhooks_created_by", "webhooks", ["created_by"], unique=False)

    # 5. Table: webhook_deliveries
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("webhook_id", sa.UUID(), sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.UUID(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("request_headers", sa.JSON(), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("response_headers", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", webhook_delivery_status_col, nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"], unique=False)
    op.create_index("idx_webhook_deliveries_status", "webhook_deliveries", ["status"], unique=False)
    op.create_index("idx_webhook_deliveries_created_at", "webhook_deliveries", [sa.text("created_at DESC")], unique=False)

    # 6. Table: integrations
    op.create_table(
        "integrations",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("provider", integration_provider_col, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("status", integration_status_col, nullable=False, server_default="active"),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_integrations_provider", "integrations", ["provider"], unique=False)
    op.create_index("idx_integrations_status", "integrations", ["status"], unique=False)
    op.create_index("idx_integrations_created_by", "integrations", ["created_by"], unique=False)

    # 7. Table: automation_rules
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("trigger_event", sa.String(100), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_automation_rules_trigger_event", "automation_rules", ["trigger_event"], unique=False)
    op.create_index("idx_automation_rules_is_active", "automation_rules", ["is_active"], unique=False)

    # 8. Table: automation_executions
    op.create_table(
        "automation_executions",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("rule_id", sa.UUID(), sa.ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", sa.UUID(), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("status", automation_status_col, nullable=False, server_default="success"),
        sa.Column("action_results", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_automation_executions_rule_id", "automation_executions", ["rule_id"], unique=False)
    op.create_index("idx_automation_executions_created_at", "automation_executions", [sa.text("created_at DESC")], unique=False)


def downgrade() -> None:
    op.drop_table("automation_executions")
    op.drop_table("automation_rules")
    op.drop_table("integrations")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
    op.drop_table("outbox_events")
    op.drop_table("events")

    # Drop Enums
    sa.Enum(name="automation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integration_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integration_provider").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="webhook_delivery_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="event_status").drop(op.get_bind(), checkfirst=True)
