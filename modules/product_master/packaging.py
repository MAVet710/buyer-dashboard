"""First-class package/content and label-print semantics for Product Master."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from modules.coman.models import Base, Product, TimestampMixin


LABEL_LAYOUTS = {"compact_single", "compact_duo", "bulk_barcode"}
DEFAULT_LABEL_WIDTH_IN = 3.5
DEFAULT_LABEL_HEIGHT_IN = 2.1


class ProductPackagingProfile(TimestampMixin, Base):
    __tablename__ = "product_packaging_profiles"

    product_id: Mapped[str] = mapped_column(
        ForeignKey("coman_products.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("coman_organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    net_content: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    net_content_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    units_per_package: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sellable_unit: Mapped[str] = mapped_column(String(32), nullable=False, default="each")
    case_pack: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    warning_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    label_layout: Mapped[str] = mapped_column(String(32), nullable=False, default="compact_single")
    label_width_in: Mapped[float] = mapped_column(Float, nullable=False, default=DEFAULT_LABEL_WIDTH_IN)
    label_height_in: Mapped[float] = mapped_column(Float, nullable=False, default=DEFAULT_LABEL_HEIGHT_IN)


class ProductPackagingService:
    @staticmethod
    def upsert(
        session: Session,
        *,
        organization_id: str,
        product_id: str,
        net_content: float,
        net_content_unit: str,
        units_per_package: float = 1.0,
        sellable_unit: str = "each",
        case_pack: float = 0.0,
        warning_text: str | None = None,
        label_layout: str = "compact_single",
        label_width_in: float = DEFAULT_LABEL_WIDTH_IN,
        label_height_in: float = DEFAULT_LABEL_HEIGHT_IN,
    ) -> ProductPackagingProfile:
        product = session.get(Product, product_id)
        if not product or product.organization_id != organization_id:
            raise ValueError("Product was not found in this organization.")
        if float(net_content) < 0 or float(units_per_package) <= 0 or float(case_pack) < 0:
            raise ValueError("Packaging quantities must be non-negative and units per package must be positive.")
        layout = str(label_layout or "compact_single").strip().casefold()
        if layout not in LABEL_LAYOUTS:
            raise ValueError("Label layout must be compact_single, compact_duo, or bulk_barcode.")
        width = float(label_width_in)
        height = float(label_height_in)
        if width <= 0 or height <= 0 or width > 12 or height > 12:
            raise ValueError("Label width and height must be greater than zero and no larger than 12 inches.")
        row = session.get(ProductPackagingProfile, product_id)
        if row is None:
            row = ProductPackagingProfile(product_id=product_id, organization_id=organization_id)
            session.add(row)
        row.net_content = float(net_content)
        row.net_content_unit = str(net_content_unit or "").strip().casefold()
        row.units_per_package = float(units_per_package)
        row.sellable_unit = str(sellable_unit or "each").strip().casefold() or "each"
        row.case_pack = float(case_pack)
        if warning_text is not None:
            row.warning_text = str(warning_text or "").strip()
        row.label_layout = layout
        row.label_width_in = width
        row.label_height_in = height
        return row

    @staticmethod
    def get(session: Session, organization_id: str, product_id: str) -> ProductPackagingProfile | None:
        row = session.get(ProductPackagingProfile, product_id)
        if row and row.organization_id == organization_id:
            return row
        return None
