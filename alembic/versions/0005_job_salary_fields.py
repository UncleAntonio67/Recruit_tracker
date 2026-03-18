"""add salary fields to job_postings

Revision ID: 0005_job_salary_fields
Revises: 0004_company_profile_fields
Create Date: 2026-03-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_job_salary_fields"
down_revision = "0004_company_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_postings") as batch:
        batch.add_column(sa.Column("salary_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("salary_min_k", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("salary_max_k", sa.Integer(), nullable=True))
        batch.create_index("ix_job_postings_salary_min_k", ["salary_min_k"])
        batch.create_index("ix_job_postings_salary_max_k", ["salary_max_k"])


def downgrade() -> None:
    with op.batch_alter_table("job_postings") as batch:
        batch.drop_index("ix_job_postings_salary_max_k")
        batch.drop_index("ix_job_postings_salary_min_k")
        batch.drop_column("salary_max_k")
        batch.drop_column("salary_min_k")
        batch.drop_column("salary_text")

