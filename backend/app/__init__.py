"""DoobieLogic HTTP API package.

A one-shot MA Metrc resume diagnostic can be enabled explicitly at runtime with
``METRC_RESUME_DIAGNOSTIC_RUN_ID``. The hook is intentionally absent unless that
value is set, performs GET-only provider discovery through the application's
existing encrypted credential path, and is idempotent by the supplied run ID.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def _start_metrc_resume_diagnostic_if_requested() -> None:
    run_id = str(os.environ.get("METRC_RESUME_DIAGNOSTIC_RUN_ID") or "").strip()
    if not run_id:
        return

    def worker() -> None:
        # Let the normal FastAPI import/startup path finish before opening the
        # shared database pool or making any provider read.
        time.sleep(8)
        try:
            from .config import get_settings
            from .database import get_engine
            from .services.metrc_resume_diagnostics import run_server_resume_diagnostic

            result = run_server_resume_diagnostic(get_engine(), get_settings(), run_id)
            logger.info(
                "METRC_RESUME_DIAGNOSTIC_COMPLETE run_id=%s status=%s facilities=%s",
                run_id,
                result.get("status", "complete"),
                result.get("facility_count", 0),
            )
        except Exception:
            logger.exception("METRC_RESUME_DIAGNOSTIC_FAILED run_id=%s", run_id)

    threading.Thread(
        target=worker,
        name="metrc-resume-diagnostic",
        daemon=True,
    ).start()


_start_metrc_resume_diagnostic_if_requested()
