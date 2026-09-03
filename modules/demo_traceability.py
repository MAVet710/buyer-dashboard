"""Deterministic, realistic-looking traceability identifiers for DEV-only fixtures.

These values deliberately resemble the shape of Metrc tags so operator screens and
printed-label layouts are exercised realistically. They are synthetic and must never
be represented as provider-issued identifiers or used outside the canonical DEV
Sandbox.
"""
from __future__ import annotations

from hashlib import sha256
import re

SYNTHETIC_METRC_PREFIX = "1A40D03"
SYNTHETIC_METRC_TAG_PATTERN = re.compile(r"^1A40D03\d{17}$")


def synthetic_metrc_tag(seed: object) -> str:
    """Return a stable 24-character numeric-heavy DEV traceability tag."""
    digest = sha256(str(seed).encode("utf-8")).digest()
    numeric = int.from_bytes(digest[:10], "big") % (10**17)
    return f"{SYNTHETIC_METRC_PREFIX}{numeric:017d}"


def is_synthetic_metrc_tag(value: object) -> bool:
    return bool(SYNTHETIC_METRC_TAG_PATTERN.fullmatch(str(value or "").strip().upper()))


__all__ = ["SYNTHETIC_METRC_PREFIX", "SYNTHETIC_METRC_TAG_PATTERN", "synthetic_metrc_tag", "is_synthetic_metrc_tag"]
