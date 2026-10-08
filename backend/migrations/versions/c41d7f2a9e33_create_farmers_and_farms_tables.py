"""create farmers and farms tables

Revision ID: c41d7f2a9e33
Revises: b99c165cedec
Create Date: 2026-10-08 00:00:00.000000

One farmer may own multiple farms; each farm belongs to exactly one
farmer. No destructive deletion: farms reference farmers with
ON DELETE RESTRICT and no API delete endpoints exist.

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c41d7f2a9e33'
down_revision = 'b99c165cedec'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('farmers',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('full_name', sa.String(length=160), nullable=False),
    sa.Column('barangay', sa.String(length=120), nullable=False),
    sa.Column('contact_number', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('farms',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('farmer_id', sa.Integer(), nullable=False),
    sa.Column('plot_identifier', sa.String(length=120), nullable=False),
    sa.Column('barangay', sa.String(length=120), nullable=False),
    sa.Column('area_hectares', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('area_hectares > 0', name='ck_farms_area_positive'),
    sa.CheckConstraint('area_hectares <= 10000', name='ck_farms_area_max'),
    sa.ForeignKeyConstraint(['farmer_id'], ['farmers.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('farmer_id', 'plot_identifier', name='uq_farms_farmer_plot')
    )
    op.create_index('ix_farms_farmer_id', 'farms', ['farmer_id'], unique=False)


def downgrade():
    op.drop_index('ix_farms_farmer_id', table_name='farms')
    op.drop_table('farms')
    op.drop_table('farmers')
