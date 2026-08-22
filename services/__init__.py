"""Buyer Dash service layer.

This file intentionally makes ``services`` an explicit Python package. The app
runs on Streamlit Community Cloud where source watching and repeated script
execution can otherwise leave PEP 420 namespace-package children in an unstable
import state during deploy/reload cycles.
"""
