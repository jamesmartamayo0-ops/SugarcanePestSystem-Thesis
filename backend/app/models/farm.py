from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from app.models.farmer import normalize_barangay

MAX_AREA_HECTARES = Decimal("10000")
COORDINATE_SCALE = Decimal("0.000001")


def normalize_plot_identifier(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Plot identifier must be 1-120 characters.")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 120:
        raise ValueError("Plot identifier must be 1-120 characters.")
    return cleaned


def normalize_area_hectares(value: object) -> Decimal:
    """Accept int/float/Decimal/numeric strings; require 0 < area <= 10000."""
    if isinstance(value, bool):
        raise ValueError("Sugarcane area must be greater than 0 and at most 10000 hectares.")
    try:
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("invalid")
            area = Decimal(str(value))
        elif isinstance(value, Decimal):
            area = value
        elif isinstance(value, int):
            area = Decimal(value)
        elif isinstance(value, str):
            cleaned = value.strip()
            if not cleaned or len(cleaned) > 32:
                raise ValueError("invalid")
            area = Decimal(cleaned)
        else:
            raise ValueError("invalid")
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError("Sugarcane area must be greater than 0 and at most 10000 hectares.") from None
    if area <= 0 or area > MAX_AREA_HECTARES:
        raise ValueError("Sugarcane area must be greater than 0 and at most 10000 hectares.")
    if area.as_tuple().exponent < -2:
        raise ValueError("Sugarcane area may have at most 2 decimal places.")
    return area.quantize(Decimal("0.01"))


def normalize_coordinate(value: object, *, latitude: bool) -> Decimal | None:
    """Normalize an optional coordinate with six-decimal-place precision."""
    label = "Latitude" if latitude else "Longitude"
    minimum = Decimal("-90") if latitude else Decimal("-180")
    maximum = Decimal("90") if latitude else Decimal("180")
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    try:
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("invalid")
            coordinate = Decimal(str(value))
        elif isinstance(value, Decimal):
            coordinate = value
        elif isinstance(value, int):
            coordinate = Decimal(value)
        elif isinstance(value, str):
            cleaned = value.strip()
            if not cleaned or len(cleaned) > 32:
                raise ValueError("invalid")
            coordinate = Decimal(cleaned)
        else:
            raise ValueError("invalid")
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError(f"{label} must be between {minimum} and {maximum}.") from None
    if not coordinate.is_finite() or coordinate < minimum or coordinate > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    if coordinate.as_tuple().exponent < -6:
        raise ValueError(f"{label} may have at most 6 decimal places.")
    return coordinate.quantize(COORDINATE_SCALE)


class Farm(db.Model):
    __tablename__ = "farms"
    __table_args__ = (
        UniqueConstraint("farmer_id", "plot_identifier", name="uq_farms_farmer_plot"),
        CheckConstraint("area_hectares > 0", name="ck_farms_area_positive"),
        CheckConstraint("area_hectares <= 10000", name="ck_farms_area_max"),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_farms_latitude_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_farms_longitude_range",
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_farms_coordinates_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    farmer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    plot_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    barangay: Mapped[str] = mapped_column(String(120), nullable=False)
    area_hectares: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    farmer: Mapped["Farmer"] = relationship("Farmer", back_populates="farms")

    @validates("farmer_id")
    def _validate_farmer_id(self, _key: str, value: int) -> int:
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            raise ValueError("Farmer reference is invalid.")
        return value

    @validates("plot_identifier")
    def _validate_plot_identifier(self, _key: str, value: str) -> str:
        return normalize_plot_identifier(value)

    @validates("barangay")
    def _validate_barangay(self, _key: str, value: str) -> str:
        return normalize_barangay(value)

    @validates("area_hectares")
    def _validate_area_hectares(self, _key: str, value: object) -> Decimal:
        return normalize_area_hectares(value)

    @validates("latitude")
    def _validate_latitude(self, _key: str, value: object) -> Decimal | None:
        return normalize_coordinate(value, latitude=True)

    @validates("longitude")
    def _validate_longitude(self, _key: str, value: object) -> Decimal | None:
        return normalize_coordinate(value, latitude=False)

    def __repr__(self) -> str:
        return f"<Farm id={self.id}>"
