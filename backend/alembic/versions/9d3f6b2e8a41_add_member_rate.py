"""add rooms.member_price_per_night (1.8.1)

Revision ID: 9d3f6b2e8a41
Revises: 7e4c2a9d6b15
Create Date: 2026-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d3f6b2e8a41'
down_revision: Union[str, None] = '7e4c2a9d6b15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode so this also runs on SQLite, which can't ALTER in a constraint.
    with op.batch_alter_table('rooms') as batch:
        batch.add_column(sa.Column('member_price_per_night', sa.Numeric(10, 2), nullable=True))
        batch.create_check_constraint(
            'ck_member_rate_below_public',
            'member_price_per_night IS NULL OR '
            '(member_price_per_night > 0 AND member_price_per_night < price_per_night)',
        )


def downgrade() -> None:
    with op.batch_alter_table('rooms') as batch:
        batch.drop_constraint('ck_member_rate_below_public', type_='check')
        batch.drop_column('member_price_per_night')
