"""Canonical Streamlit entrypoint with the living demo runtime installed first."""

import streamlit as st

from services.demo_data import install_demo_runtime

install_demo_runtime(st)

import app  # noqa: E402,F401
