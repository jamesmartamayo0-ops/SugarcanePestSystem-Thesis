"""create pest cases table

Revision ID: e7a3c9d51f24
Revises: c41d7f2a9e33
Create Date: 2026-10-09 00:00:00.000000

Each pest case references exactly one farm. The reported affected area is a
pre-inspection estimate and must not exceed the farm's recorded sugarcane
area (enforced by the API against the live farm record). Status is a
controlled workflow starting at REPORTED; later phases extend it.

No destructive deletion: farms and reporting staff are referenced with
ON DELETE RESTRICT and no API delete endpoints exist.

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a3c9d51f24'
down_revision = 'c41d7f2a9e33'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pest_cases',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('farm_id', sa.Integer(), nullable=False),
    sa.Column('pest_name', sa.String(length=120), nullable=False),
    sa.Column('symptoms', sa.Text(), nullable=True),
    sa.Column('observed_on', sa.Date(), nullable=True),
    sa.Column('reported_area_hectares', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.String(length=24), server_default='REPORTED', nullable=False),
    sa.Column('reported_by_user_id', sa.Integer(), nullable=False),
    sa.Column('reported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('reported_area_hectares > 0', name='ck_pest_cases_area_positive'),
    sa.CheckConstraint('reported_area_hectares <= 10000', name='ck_pest_cases_area_max'),
    sa.CheckConstraint("status IN ('REPORTED', 'FOR_INSPECTION')", name='ck_pest_cases_status'),
    sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reported_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pest_cases_farm_id', 'pest_cases', ['farm_id'], unique=False)
    op.create_index('ix_pest_cases_reported_by_user_id', 'pest_cases', ['reported_by_user_id'], unique=False)


def downgrade():
    op.drop_index('ix_pest_cases_reported_by_user_id', table_name='pest_cases')
    op.drop_index('ix_pest_cases_farm_id', table_name='pest_cases')
    op.drop_table('pest_cases')
