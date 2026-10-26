"""add amenities + hotel_amenities (1.6.1)

Revision ID: 7e4c2a9d6b15
Revises: 3c7e1a9b2d40
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e4c2a9d6b15'
down_revision: Union[str, None] = '3c7e1a9b2d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('amenities',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug'),
    sa.UniqueConstraint('name')
    )
    op.create_table('hotel_amenities',
    sa.Column('hotel_id', sa.String(length=36), nullable=False),
    sa.Column('amenity_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['amenity_id'], ['amenities.id'], ),
    sa.ForeignKeyConstraint(['hotel_id'], ['hotels.id'], ),
    sa.PrimaryKeyConstraint('hotel_id', 'amenity_id')
    )
    op.create_index(op.f('ix_hotel_amenities_hotel_id'), 'hotel_amenities', ['hotel_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hotel_amenities_hotel_id'), table_name='hotel_amenities')
    op.drop_table('hotel_amenities')
    op.drop_table('amenities')
