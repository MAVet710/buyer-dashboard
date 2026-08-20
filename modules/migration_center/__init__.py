"""Switch to Buyer Dash migration command center."""

from .models import MigrationBatch, MigrationRecord, MigrationSalesHistory
from .service import MigrationCenterService, detect_source_system, normalize_import_row
from .transaction_safe import install_transaction_safe_match

install_transaction_safe_match(MigrationCenterService)

__all__ = [
    "MigrationBatch",
    "MigrationRecord",
    "MigrationSalesHistory",
    "MigrationCenterService",
    "detect_source_system",
    "normalize_import_row",
]
