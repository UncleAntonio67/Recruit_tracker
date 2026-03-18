"""add source_kind to job_sources

Revision ID: 0006_job_source_kind
Revises: 0005_job_salary_fields
Create Date: 2026-03-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_job_source_kind"
down_revision = "0005_job_salary_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_sources") as batch:
        batch.add_column(sa.Column("source_kind", sa.Text(), nullable=True))
        batch.create_index("ix_job_sources_source_kind", ["source_kind"])


def downgrade() -> None:
    with op.batch_alter_table("job_sources") as batch:
        batch.drop_index("ix_job_sources_source_kind")
        batch.drop_column("source_kind")

