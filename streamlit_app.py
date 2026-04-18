"""Canonical Streamlit entrypoint.

This wrapper ensures deployments that default to `streamlit_app.py`
load the current `app.py` implementation.
"""

import app  # noqa: F401
