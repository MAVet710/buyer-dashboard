"""Cross-workspace inventory availability and commitment projection."""

from .service import InventoryAvailabilityService
from .coman_guard import install_coman_availability_guard

install_coman_availability_guard()

__all__ = ["InventoryAvailabilityService"]
