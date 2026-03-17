"""init (sqlite-compatible)

Revision ID: 0001_init
Revises:
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_company_id", sa.Text(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_type", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_companies_name", "companies", ["name"], unique=True)

    op.create_table(
        "job_postings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("company_id", sa.Text(), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("seniority", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fingerprint", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_postings_company_id", "job_postings", ["company_id"], unique=False)
    op.create_index("ix_job_postings_city", "job_postings", ["city"], unique=False)
    op.create_index("ix_job_postings_status", "job_postings", ["status"], unique=False)
    op.create_index("ix_job_postings_fingerprint", "job_postings", ["fingerprint"], unique=False)

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("job_posting_id", sa.Text(), sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_sources_job_posting_id", "job_sources", ["job_posting_id"], unique=False)
    op.create_index("ix_job_sources_source_url", "job_sources", ["source_url"], unique=True)

    op.create_table(
        "applications",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_posting_id", sa.Text(), sa.ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_text", sa.Text(), nullable=True),
        sa.Column("title_text", sa.Text(), nullable=False),
        sa.Column("city_text", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage", sa.Text(), nullable=False, server_default=sa.text("'not_applied'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_applications_owner_user_id", "applications", ["owner_user_id"], unique=False)
    op.create_index("ix_applications_stage", "applications", ["stage"], unique=False)
    op.create_index("ix_applications_job_posting_id", "applications", ["job_posting_id"], unique=False)

    op.create_table(
        "application_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("application_id", sa.Text(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_application_events_application_id", "application_events", ["application_id"], unique=False)
    op.create_index("ix_application_events_event_type", "application_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_table("application_events")
    op.drop_table("applications")
    op.drop_table("job_sources")
    op.drop_table("job_postings")
    op.drop_table("companies")
    op.drop_table("user_sessions")
    op.drop_table("users")
