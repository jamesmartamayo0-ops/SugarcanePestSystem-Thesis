"""add optional farm coordinates

Revision ID: d6b8f2a1c4e7
Revises: c9d4e6a8b2f1
Create Date: 2026-10-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d6b8f2a1c4e7"
down_revision = "c9d4e6a8b2f1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "farms", sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True)
    )
    op.add_column(
        "farms", sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True)
    )
    op.create_check_constraint(
        "ck_farms_latitude_range",
        "farms",
        sa.text("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)"),
    )
    op.create_check_constraint(
        "ck_farms_longitude_range",
        "farms",
        sa.text("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)"),
    )
    op.create_check_constraint(
        "ck_farms_coordinates_pair",
        "farms",
        sa.text(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)"
        ),
    )


def downgrade():
    op.drop_constraint("ck_farms_coordinates_pair", "farms", type_="check")
    op.drop_constraint("ck_farms_longitude_range", "farms", type_="check")
    op.drop_constraint("ck_farms_latitude_range", "farms", type_="check")
    op.drop_column("farms", "longitude")
    op.drop_column("farms", "latitude")
