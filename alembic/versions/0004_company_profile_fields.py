"""Add company profile fields (hq_location, focus_directions).

Revision ID: 0004_company_profile_fields
Revises: 0003_company_fields
Create Date: 2026-03-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_company_profile_fields"
down_revision = "0003_company_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("hq_location", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("focus_directions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "focus_directions")
    op.drop_column("companies", "hq_location")

