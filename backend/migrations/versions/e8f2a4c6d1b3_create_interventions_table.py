"""create interventions table and extend pest case statuses to Phase 3D

Revision ID: e8f2a4c6d1b3
Revises: f4a9c1d2e7b3
Create Date: 2026-10-09 00:00:00.000000

Phase 3D intervention management. One pending intervention per pest case is
enforced with a partial unique index on pest_case_id WHERE completed_at IS
NULL, so historical reintervention cycles remain possible. Pest case status
gains UNDER_INTERVENTION and FOLLOW_UP_DUE.

Downgrade intentionally discards intervention history and collapses both new
statuses back to FIELD_VALIDATED. The distinction between planned, active,
and follow-up-pending work cannot be recovered by upgrading again.

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f2a4c6d1b3'
down_revision = 'f4a9c1d2e7b3'
branch_labels = None
depends_on = None

_OLD_STATUS = (
    "status IN ('REPORTED', 'FOR_INSPECTION', 'INSPECTION_SCHEDULED', "
    "'NOT_CONFIRMED', 'FIELD_VALIDATED')"
)
_NEW_STATUS = (
    "status IN ('REPORTED', 'FOR_INSPECTION', 'INSPECTION_SCHEDULED', "
    "'NOT_CONFIRMED', 'FIELD_VALIDATED', 'UNDER_INTERVENTION', "
    "'FOLLOW_UP_DUE')"
)


def upgrade():
    op.create_table('interventions',
    sa.Column('id', sa.Integer(), sa.Identity(always=False), nullable=False),
    sa.Column('pest_case_id', sa.Integer(), nullable=False),
    sa.Column('method_category', sa.String(length=16), nullable=False),
    sa.Column('method_description', sa.Text(), nullable=False),
    sa.Column('scheduled_for', sa.Date(), nullable=False),
    sa.Column('assigned_to_user_id', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=False),
    sa.Column('performed_on', sa.Date(), nullable=True),
    sa.Column('completion_notes', sa.Text(), nullable=True),
    sa.Column('follow_up_due_on', sa.Date(), nullable=True),
    sa.Column('completed_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "method_category IN ('CULTURAL', 'MECHANICAL', 'BIOLOGICAL', 'CHEMICAL', 'OTHER')",
        name='ck_interventions_method_category',
    ),
    sa.CheckConstraint(
        'length(btrim(method_description)) > 0',
        name='ck_interventions_description_nonblank',
    ),
    sa.CheckConstraint(
        'char_length(method_description) <= 2000',
        name='ck_interventions_description_max',
    ),
    sa.CheckConstraint(
        '(completed_at IS NULL AND completed_by_user_id IS NULL '
        'AND performed_on IS NULL AND completion_notes IS NULL) '
        'OR (completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL '
        'AND performed_on IS NOT NULL AND completion_notes IS NOT NULL)',
        name='ck_interventions_completion_state',
    ),
    sa.CheckConstraint(
        'completion_notes IS NULL OR length(btrim(completion_notes)) > 0',
        name='ck_interventions_notes_nonblank',
    ),
    sa.CheckConstraint(
        'completion_notes IS NULL OR char_length(completion_notes) <= 2000',
        name='ck_interventions_notes_max',
    ),
    sa.CheckConstraint(
        'completed_at IS NULL OR follow_up_due_on IS NOT NULL',
        name='ck_interventions_follow_up_required',
    ),
    sa.CheckConstraint(
        'completed_at IS NULL OR follow_up_due_on >= performed_on',
        name='ck_interventions_follow_up_order',
    ),
    sa.ForeignKeyConstraint(['pest_case_id'], ['pest_cases.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['assigned_to_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['completed_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_interventions_pest_case_id', 'interventions', ['pest_case_id'], unique=False)
    op.create_index('ix_interventions_assigned_to_user_id', 'interventions', ['assigned_to_user_id'], unique=False)
    op.create_index('ix_interventions_created_by_user_id', 'interventions', ['created_by_user_id'], unique=False)
    op.create_index('ix_interventions_completed_by_user_id', 'interventions', ['completed_by_user_id'], unique=False)
    op.create_index('ix_interventions_scheduled_for', 'interventions', ['scheduled_for'], unique=False)
    op.create_index('ix_interventions_follow_up_due_on', 'interventions', ['follow_up_due_on'], unique=False)
    op.create_index('ix_interventions_completed_at', 'interventions', ['completed_at'], unique=False)
    op.create_index(
        'uq_interventions_pending_case', 'interventions', ['pest_case_id'],
        unique=True, postgresql_where=sa.text('completed_at IS NULL'),
    )

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_NEW_STATUS))


def downgrade():
    # Downgrade intentionally discards intervention records and collapses both
    # Phase 3D workflow outcomes back to the Phase 3C FIELD_VALIDATED state.
    # The intervention history and the distinction between UNDER_INTERVENTION
    # and FOLLOW_UP_DUE cannot be recovered by upgrading again.
    # Convert while the expanded constraint still permits the Phase 3D values.
    op.execute(
        sa.text(
            "UPDATE pest_cases SET status = 'FIELD_VALIDATED' "
            "WHERE status IN ('UNDER_INTERVENTION', 'FOLLOW_UP_DUE')"
        )
    )

    op.drop_constraint('ck_pest_cases_status', 'pest_cases', type_='check')
    op.create_check_constraint('ck_pest_cases_status', 'pest_cases', sa.text(_OLD_STATUS))

    op.drop_index('uq_interventions_pending_case', table_name='interventions', postgresql_where=sa.text('completed_at IS NULL'))
    op.drop_index('ix_interventions_completed_at', table_name='interventions')
    op.drop_index('ix_interventions_follow_up_due_on', table_name='interventions')
    op.drop_index('ix_interventions_scheduled_for', table_name='interventions')
    op.drop_index('ix_interventions_completed_by_user_id', table_name='interventions')
    op.drop_index('ix_interventions_created_by_user_id', table_name='interventions')
    op.drop_index('ix_interventions_assigned_to_user_id', table_name='interventions')
    op.drop_index('ix_interventions_pest_case_id', table_name='interventions')
    op.drop_table('interventions')
