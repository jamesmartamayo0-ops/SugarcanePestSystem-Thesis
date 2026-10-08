"""create inspections table and extend pest case statuses

Revision ID: f4a9c1d2e7b3
Revises: e7a3c9d51f24
Create Date: 2026-10-10 00:00:00.000000

One initial inspection per pest case (UNIQUE pest_case_id, ON DELETE
RESTRICT). Reported area stays on pest_cases; validated area is the
inspector's independent field measurement stored on inspections.
Pest case status gains INSPECTION_SCHEDULED, NOT_CONFIRMED, and
FIELD_VALIDATED; later phases own CLOSED and UNDER_INTERVENTION.

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a9c1d2e7b3'
down_revision = 'e7a3c9d51f24'
branch_labels = None
depends_on = None

_OLD_STATUS = "status IN ('REPORTED', 'FOR_INSPECTION')"
_NEW_STATUS = (
    "status IN ('REPORTED', 'FOR_INSPECTION', 'INSPECTION_SCHEDULED', "
    "'NOT_CONFIRMED', 'FIELD_VALIDATED')"
)


def upgrade():
    op.create_table('inspections',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('pest_case_id', sa.Integer(), nullable=False),
    sa.Column('scheduled_for', sa.Date(), nullable=False),
    sa.Column('assigned_to_user_id', sa.Integer(), nullable=False),
    sa.Column('scheduled_by_user_id', sa.Integer(), nullable=False),
    sa.Column('inspected_on', sa.Date(), nullable=True),
    sa.Column('findings', sa.Text(), nullable=True),
    sa.Column('pest_confirmed', sa.Boolean(), nullable=True),
    sa.Column('validated_area_hectares', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        'validated_area_hectares IS NULL OR '
        '(validated_area_hectares >= 0 AND validated_area_hectares <= 10000)',
        name='ck_inspections_validated_range',
    ),
    sa.CheckConstraint(
        '(completed_at IS NULL AND completed_by_user_id IS NULL '
        'AND inspected_on IS NULL AND findings IS NULL '
        'AND pest_confirmed IS NULL AND validated_area_hectares IS NULL) '
        'OR (completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL '
        'AND inspected_on IS NOT NULL AND findings IS NOT NULL '
        'AND pest_confirmed IS NOT NULL AND validated_area_hectares IS NOT NULL)',
        name='ck_inspections_completion_state',
    ),
    sa.CheckConstraint(
        'findings IS NULL OR length(btrim(findings)) > 0',
        name='ck_inspections_findings_nonblank',
    ),
    sa.CheckConstraint(
        'findings IS NULL OR char_length(findings) <= 2000',
        name='ck_inspections_findings_max',
    ),
    sa.CheckConstraint(
        '(pest_confirmed IS NULL AND validated_area_hectares IS NULL) '
        'OR (pest_confirmed = TRUE AND validated_area_hectares > 0) '
        'OR (pest_confirmed = FALSE AND validated_area_hectares = 0)',
        name='ck_inspections_confirmed_area',
    ),
    sa.ForeignKeyConstraint(['pest_case_id'], ['pest_cases.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['scheduled_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pest_case_id', name='uq_inspections_pest_case_id')
    )
    op.create_index('ix_inspections_pest_case_id', 'inspections', ['pest_case_id'], unique=False)
    op.create_index('ix_inspections_assigned_to_user_id', 'inspections', ['assigned_to_user_id'], unique=False)
    op.create_index('ix_inspections_scheduled_by_user_id', 'inspections', ['scheduled_by_user_id'], unique=False)
    op.create_index('ix_inspections_completed_by_user_id', 'inspections', ['completed_by_user_id'], unique=False)

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_NEW_STATUS))


def downgrade():
    # Downgrade intentionally discards inspection records and collapses every
    # Phase 3C workflow outcome back to the Phase 3B FOR_INSPECTION state. The
    # original inspection data and the distinction between these statuses
    # cannot be recovered by upgrading again.
    op.execute(
        sa.text(
            "UPDATE pest_cases SET status = 'FOR_INSPECTION' "
            "WHERE status IN ('INSPECTION_SCHEDULED', 'FIELD_VALIDATED', "
            "'NOT_CONFIRMED')"
        )
    )

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_OLD_STATUS))

    op.drop_index('ix_inspections_completed_by_user_id', table_name='inspections')
    op.drop_index('ix_inspections_scheduled_by_user_id', table_name='inspections')
    op.drop_index('ix_inspections_assigned_to_user_id', table_name='inspections')
    op.drop_index('ix_inspections_pest_case_id', table_name='inspections')
    op.drop_table('inspections')
