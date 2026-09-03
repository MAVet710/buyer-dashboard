#!/usr/bin/env python3
"""Create or inspect the Metrc Massachusetts sandbox integrator setup.

The vendor key is read from METRC_INTEGRATOR_API_KEY and sent only in the
x-metrc-key header. It is never printed. If Metrc returns a sandbox User API Key,
the script prints it once so the operator can immediately place it into
DoobieLogic's encrypted credential storage.
"""

from __future__ import annotations

import argparse
import os

from services.metrc_sandbox_bootstrap import setup_ma_sandbox_integrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the MA Metrc sandbox user.")
    parser.add_argument(
        "--user-key",
        default="",
        help="Optional existing sandbox User API Key to look up setup state. Omit for first-time creation.",
    )
    args = parser.parse_args()

    vendor_key = str(os.environ.get("METRC_INTEGRATOR_API_KEY") or "").strip()
    if not vendor_key:
        raise SystemExit("Set METRC_INTEGRATOR_API_KEY in the runtime environment before running this command.")

    result = setup_ma_sandbox_integrator(vendor_api_key=vendor_key, user_key=args.user_key)
    print(f"HTTP: {result['http_status']}")
    print(result["message"])
    if result.get("user_key"):
        print("Sandbox User API Key returned by Metrc:")
        print(result["user_key"])
        print("Store this immediately in DoobieLogic encrypted Metrc user credentials; do not commit it.")
    elif result.get("ok"):
        print("No User API Key was returned in this response. Check the Metrc Connect contact email for the generated sandbox key.")
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
