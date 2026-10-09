"""create follow-ups table and extend pest case statuses to Phase 3E

Revision ID: c9d4e6a8b2f1
Revises: e8f2a4c6d1b3
Create Date: 2026-10-09 00:00:00.000000

Phase 3E follow-up, reassessment, reintervention, and case closure.
One follow-up per completed intervention is enforced with a UNIQUE
constraint on follow_ups.intervention_id, so every reassessment cycle is
preserved as history. Pest case status gains REINTERVENTION_REQUIRED and
CLOSED. The repeat cycle is FIELD_VALIDATED -> UNDER_INTERVENTION ->
FOLLOW_UP_DUE -> REINTERVENTION_REQUIRED -> UNDER_INTERVENTION ->
FOLLOW_UP_DUE -> CLOSED.

Downgrade intentionally discards follow-up history and collapses both new
statuses back to FOLLOW_UP_DUE before restoring the seven-status Phase 3D
check constraint. Recorded reassessments and their outcomes cannot be
recovered by upgrading again.

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d4e6a8b2f1'
down_revision = 'e8f2a4c6d1b3'
branch_labels = None
depends_on = None

_OLD_STATUS = (
    "status IN ('REPORTED', 'FOR_INSPECTION', 'INSPECTION_SCHEDULED', "
    "'NOT_CONFIRMED', 'FIELD_VALIDATED', 'UNDER_INTERVENTION', "
    "'FOLLOW_UP_DUE')"
)
_NEW_STATUS = (
    "status IN ('REPORTED', 'FOR_INSPECTION', 'INSPECTION_SCHEDULED', "
    "'NOT_CONFIRMED', 'FIELD_VALIDATED', 'UNDER_INTERVENTION', "
    "'FOLLOW_UP_DUE', 'REINTERVENTION_REQUIRED', 'CLOSED')"
)


def upgrade():
    op.create_table('follow_ups',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('intervention_id', sa.Integer(), nullable=False),
    sa.Column('observed_on', sa.Date(), nullable=False),
    sa.Column('pest_observed', sa.Boolean(), nullable=False),
    sa.Column('observed_affected_area_hectares', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('assessment_notes', sa.Text(), nullable=False),
    sa.Column('outcome', sa.String(length=24), nullable=False),
    sa.Column('recorded_by_user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(
        "outcome IN ('RESOLVED', 'REINTERVENTION_REQUIRED')",
        name='ck_follow_ups_outcome',
    ),
    sa.CheckConstraint(
        'length(btrim(assessment_notes)) > 0',
        name='ck_follow_ups_notes_nonblank',
    ),
    sa.CheckConstraint(
        'char_length(assessment_notes) <= 2000',
        name='ck_follow_ups_notes_max',
    ),
    sa.CheckConstraint(
        'observed_affected_area_hectares IS NULL OR '
        '(observed_affected_area_hectares >= 0 AND observed_affected_area_hectares <= 10000)',
        name='ck_follow_ups_area_range',
    ),
    sa.ForeignKeyConstraint(['intervention_id'], ['interventions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('intervention_id', name='uq_follow_ups_intervention_id')
    )
    op.create_index('ix_follow_ups_intervention_id', 'follow_ups', ['intervention_id'], unique=False)
    op.create_index('ix_follow_ups_observed_on', 'follow_ups', ['observed_on'], unique=False)
    op.create_index('ix_follow_ups_outcome', 'follow_ups', ['outcome'], unique=False)
    op.create_index('ix_follow_ups_recorded_by_user_id', 'follow_ups', ['recorded_by_user_id'], unique=False)

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_NEW_STATUS))


def downgrade():
    # Downgrade intentionally discards follow-up records and collapses both
    # Phase 3E workflow outcomes back to the Phase 3D FOLLOW_UP_DUE state.
    # Recorded reassessments and their RESOLVED / REINTERVENTION_REQUIRED
    # outcomes cannot be recovered by upgrading again.
    # Convert while the expanded constraint still permits the Phase 3E values.
    op.execute(
        sa.text(
            "UPDATE pest_cases SET status = 'FOLLOW_UP_DUE' "
            "WHERE status IN ('REINTERVENTION_REQUIRED', 'CLOSED')"
        )
    )

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_OLD_STATUS))

    op.drop_index('ix_follow_ups_recorded_by_user_id', table_name='follow_ups')
    op.drop_index('ix_follow_ups_outcome', table_name='follow_ups')
    op.drop_index('ix_follow_ups_observed_on', table_name='follow_ups')
    op.drop_index('ix_follow_ups_intervention_id', table_name='follow_ups')
    op.drop_table('follow_ups')
