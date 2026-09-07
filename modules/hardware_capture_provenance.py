"""Provider-neutral hardware-capture provenance for reviewed operational actions.

Hardware observations are evidence, never authority. This module standardizes
where an identifier came from so warehouse, inventory audit, receiving,
production and future Seek & Find workflows can write the same audit vocabulary
without learning device-specific protocols.
"""

from __future__ import annotations

from dataclasses import dataclass


IDENTIFIER_CAPTURE_SOURCES = frozenset({"camera", "keyboard_wedge", "manual", "rfid_reader"})


@dataclass(frozen=True)
class IdentifierCaptureProvenance:
    source: str
    device_id: str = ""
    symbology: str = ""
    captured_at: str = ""

    @classmethod
    def build(
        cls,
        *,
        source: str = "manual",
        device_id: str = "",
        symbology: str = "",
        captured_at: str = "",
    ) -> "IdentifierCaptureProvenance":
        normalized = str(source or "manual").strip().casefold() or "manual"
        if normalized not in IDENTIFIER_CAPTURE_SOURCES:
            raise ValueError(f"Unsupported identifier capture source: {source}.")
        return cls(
            source=normalized,
            device_id=str(device_id or "").strip(),
            symbology=str(symbology or "").strip(),
            captured_at=str(captured_at or "").strip(),
        )

    @property
    def audit_source(self) -> str:
        if self.source == "rfid_reader":
            return "rfid"
        if self.source in {"camera", "keyboard_wedge"}:
            return "scanner"
        return "user"

    def device_metadata(self) -> dict[str, str]:
        metadata = {"capture_source": self.source}
        if self.device_id:
            metadata["device_id"] = self.device_id
        if self.symbology:
            metadata["symbology"] = self.symbology
        if self.captured_at:
            metadata["captured_at"] = self.captured_at
        return metadata
