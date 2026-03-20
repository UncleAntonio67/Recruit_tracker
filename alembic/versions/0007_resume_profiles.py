"""add resume_profiles

Revision ID: 0007_resume_profiles
Revises: 0006_job_source_kind
Create Date: 2026-03-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_resume_profiles"
down_revision = "0006_job_source_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_profiles",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("projects", sa.Text(), nullable=True),
        sa.Column("education", sa.Text(), nullable=True),
        sa.Column("links", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_user_id", name="uq_resume_profiles_owner_user_id"),
    )
    op.create_index("ix_resume_profiles_owner_user_id", "resume_profiles", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_profiles_owner_user_id", table_name="resume_profiles")
    op.drop_table("resume_profiles")

