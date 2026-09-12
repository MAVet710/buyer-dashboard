"""DoobieLogic HTTP API package.

One-shot Massachusetts Metrc resume helpers are explicitly runtime-gated. The
resume diagnostics are GET-only. The package-evaluation hook may perform the
reviewed MA sandbox prerequisite tag generation plus workbook tasks 25-26 only;
it is absent unless ``METRC_PACKAGE_EVAL_RUN_ID`` is deliberately set and its
service remains fail-closed/idempotent by run ID.
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

    threading.Thread(target=worker, name="metrc-resume-diagnostic", daemon=True).start()


def _start_metrc_resume_detail_if_requested() -> None:
    run_id = str(os.environ.get("METRC_RESUME_DETAIL_RUN_ID") or "").strip()
    if not run_id:
        return

    def worker() -> None:
        time.sleep(8)
        try:
            from .config import get_settings
            from .database import get_engine
            from .services.metrc_resume_live_detail import run_server_resume_detail

            result = run_server_resume_detail(get_engine(), get_settings(), run_id)
            logger.info(
                "METRC_RESUME_DETAIL_COMPLETE run_id=%s status=%s facilities=%s active_packages=%s",
                run_id,
                result.get("status", "complete"),
                result.get("facility_count", 0),
                result.get("active_package_total", 0),
            )
        except Exception:
            logger.exception("METRC_RESUME_DETAIL_FAILED run_id=%s", run_id)

    threading.Thread(target=worker, name="metrc-resume-detail", daemon=True).start()


def _start_metrc_package_eval_if_requested() -> None:
    run_id = str(os.environ.get("METRC_PACKAGE_EVAL_RUN_ID") or "").strip()
    if not run_id:
        return
    mode = str(os.environ.get("METRC_PACKAGE_EVAL_MODE") or "preflight").strip()
    logger.warning("METRC_PACKAGE_EVAL_SCHEDULED run_id=%s mode=%s", run_id, mode)

    def worker() -> None:
        time.sleep(8)
        logger.warning("METRC_PACKAGE_EVAL_STARTED run_id=%s mode=%s", run_id, mode)
        try:
            from .config import get_settings
            from .database import get_engine
            from .services.metrc_package_eval_lockfix import run_package_tasks_25_26

            result = run_package_tasks_25_26(get_engine(), get_settings(), run_id)
            logger.warning(
                "METRC_PACKAGE_EVAL_COMPLETE run_id=%s mode=%s status=%s task25=%s task26=%s",
                run_id,
                mode,
                result.get("status", "unknown"),
                bool((result.get("task25") or {}).get("passed")),
                bool((result.get("task26") or {}).get("passed")),
            )
        except Exception:
            logger.exception("METRC_PACKAGE_EVAL_FAILED run_id=%s mode=%s", run_id, mode)

    threading.Thread(target=worker, name="metrc-package-eval", daemon=True).start()


_start_metrc_resume_diagnostic_if_requested()
_start_metrc_resume_detail_if_requested()
_start_metrc_package_eval_if_requested()
