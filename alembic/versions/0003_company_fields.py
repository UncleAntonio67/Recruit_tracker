"""add company industry + recruitment_url

Revision ID: 0003_company_fields
Revises: 0002_crawl_sources
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_company_fields"
down_revision = "0002_crawl_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("industry", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("recruitment_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "recruitment_url")
    op.drop_column("companies", "industry")
