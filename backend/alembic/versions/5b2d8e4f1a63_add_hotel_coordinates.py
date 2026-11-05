"""add hotel latitude/longitude (US1.5 distance sort)

Revision ID: 5b2d8e4f1a63
Revises: 3c7e1a9b2d40
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b2d8e4f1a63'
down_revision: Union[str, None] = '3c7e1a9b2d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hotels', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('hotels', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    # batch mode so SQLite (no DROP COLUMN before 3.35) can downgrade too.
    with op.batch_alter_table('hotels') as batch_op:
        batch_op.drop_column('longitude')
        batch_op.drop_column('latitude')
