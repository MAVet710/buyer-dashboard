"""First-class package/content semantics for Product Master."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from modules.coman.models import Base, Product, TimestampMixin


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
    ) -> ProductPackagingProfile:
        product = session.get(Product, product_id)
        if not product or product.organization_id != organization_id:
            raise ValueError("Product was not found in this organization.")
        if float(net_content) < 0 or float(units_per_package) <= 0 or float(case_pack) < 0:
            raise ValueError("Packaging quantities must be non-negative and units per package must be positive.")
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
        return row

    @staticmethod
    def get(session: Session, organization_id: str, product_id: str) -> ProductPackagingProfile | None:
        row = session.get(ProductPackagingProfile, product_id)
        if row and row.organization_id == organization_id:
            return row
        return None
