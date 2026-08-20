"""Canonical Streamlit entrypoint with durable runtime bridges installed first."""

import streamlit as st

from services.demo_data import install_demo_runtime
from services.extraction_runtime import (
    finalize_extraction_runtime,
    prepare_extraction_runtime,
)
from services.market_takeover_runtime import prepare_market_takeover_runtime
from services.sandbox_market_runtime import install_sandbox_market_hydration_runtime
from services.sandbox_scope_guard import install_dev_sandbox_scope_guard
from services.ux_cohesion_runtime import prepare_ux_cohesion_runtime

# Synthetic full-company data requires both DEV role and a positively hydrated
# canonical sandbox tenant. Elevated access alone can never activate demo data.
install_dev_sandbox_scope_guard()
install_demo_runtime(st)
install_sandbox_market_hydration_runtime(st)
prepare_extraction_runtime(st)
prepare_market_takeover_runtime(st)
prepare_ux_cohesion_runtime(st)

import app  # noqa: E402,F401

finalize_extraction_runtime(st)
