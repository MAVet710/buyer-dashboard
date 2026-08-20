"""Canonical Streamlit entrypoint with durable runtime bridges installed first."""

import streamlit as st

from services.demo_data import install_demo_runtime
from services.extraction_runtime import (
    finalize_extraction_runtime,
    prepare_extraction_runtime,
)
from services.market_takeover_runtime import prepare_market_takeover_runtime

install_demo_runtime(st)
prepare_extraction_runtime(st)
prepare_market_takeover_runtime(st)

import app  # noqa: E402,F401

finalize_extraction_runtime(st)
