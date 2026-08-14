"""PDF reader/writer compatibility helpers.

Production installs use the maintained ``pypdf`` package.  The guarded
fallback keeps older local development environments usable while they are
being upgraded; it is not used by CI or deployed builds.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


try:
    _pdf_module = import_module("pypdf")
except ModuleNotFoundError:  # pragma: no cover - legacy developer machines
    _pdf_module = import_module("PyPDF2")


PdfReader: Any = _pdf_module.PdfReader
PdfWriter: Any = _pdf_module.PdfWriter


__all__ = ["PdfReader", "PdfWriter"]
