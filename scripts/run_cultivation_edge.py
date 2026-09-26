"""One-shot offline JSON/CSV collection. No listener, scheduler or network IO."""
import argparse
import json
from pathlib import Path
import sys

# Avoid application package initialization, ORM registration and environment
# loading. Only this repository's standalone edge and metric modules are used.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from edge_store import EdgeError, EdgeStore, Scope  # noqa: E402
from adapters.normalized import NormalizedExportAdapter  # noqa: E402
from adapters.base import AdapterError  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--facility", required=True)
    parser.add_argument("--connection", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--contract", required=True, help="Local JSON columns/metric_mappings contract, never credentials")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args(argv)
    try:
        with open(args.contract, "rb") as handle:
            content = handle.read(65537)
        if len(content) > 65536:
            raise EdgeError("contract_byte_limit")
        contract = json.loads(content)
        if not isinstance(contract, dict) or set(contract) - {"columns", "metric_mappings", "rows_key"}:
            raise EdgeError("invalid_export_contract")
        adapter = NormalizedExportAdapter(**contract)
        with open(args.input, "rb") as handle:
            content = handle.read(adapter.max_bytes + 1)
        parsed = adapter.parse(content, format=args.format)
        store = EdgeStore(args.database)
        scope = Scope(args.organization, args.facility, args.connection)
        # Offline import cannot authorize historical room/cycle relationships.
        # Backend retry_pending resolves them later against validated snapshots.
        result = store.ingest(scope, parsed["readings"])
        print(json.dumps({"committed": result["committed"], "accepted": result["accepted"], "pending": result["pending"], "duplicates": result["duplicates"], "conflicts": result["conflicts"], "quarantined": result["quarantined"], "raw_stays_local": True}))
        return 0
    except (OSError, ValueError, TypeError, AdapterError):
        print(json.dumps({"committed": False, "error": "local_export_rejected"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
