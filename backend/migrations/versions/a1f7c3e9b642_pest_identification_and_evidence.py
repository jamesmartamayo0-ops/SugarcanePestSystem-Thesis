"""add suspected-pest optionality, confirmed pest, and evidence photos

Revision ID: a1f7c3e9b642
Revises: d6b8f2a1c4e7
Create Date: 2026-11-11 00:00:00.000000

Initial report keeps an optional suspected pest; field validation records the
technician-confirmed pest on inspections so the original report is never
rewritten. Evidence photos are stored on disk and referenced here.

Forward-only: existing pest names and all workflow records are preserved.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1f7c3e9b642"
down_revision = "d6b8f2a1c4e7"
branch_labels = None
depends_on = None


def upgrade():
    # Existing non-null pest names remain untouched; only the constraint is
    # relaxed so a report can be filed before the pest is identified.
    op.alter_column(
        "pest_cases",
        "pest_name",
        existing_type=sa.String(length=120),
        nullable=True,
    )

    op.add_column(
        "inspections",
        sa.Column("confirmed_pest_name", sa.String(length=120), nullable=True),
    )
    op.create_check_constraint(
        "ck_inspections_confirmed_pest_name",
        "inspections",
        "confirmed_pest_name IS NULL OR "
        "(pest_confirmed = TRUE AND length(btrim(confirmed_pest_name)) > 0)",
    )

    op.create_table(
        "pest_case_evidence_photos",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("pest_case_id", sa.Integer(), nullable=False),
        sa.Column("stored_name", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_evidence_photos_size_positive"),
        sa.CheckConstraint("byte_size <= 5242880", name="ck_evidence_photos_size_max"),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_evidence_photos_content_type",
        ),
        sa.ForeignKeyConstraint(
            ["pest_case_id"], ["pest_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(
        "ix_pest_case_evidence_photos_pest_case_id",
        "pest_case_evidence_photos",
        ["pest_case_id"],
        unique=False,
    )
    op.create_index(
        "ix_pest_case_evidence_photos_uploaded_by_user_id",
        "pest_case_evidence_photos",
        ["uploaded_by_user_id"],
        unique=False,
    )


def downgrade():
    # Forward-only by policy: dropping evidence rows would destroy uploaded
    # client records. Restore from a backup if a rollback is ever required.
    raise NotImplementedError("Forward-only migration.")
