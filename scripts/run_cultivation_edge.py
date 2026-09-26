"""Offline JSON/CSV import or continuous finalized-file collection. No network IO."""
import argparse
import json
from pathlib import Path
import sys
import signal
import threading

# Avoid application package initialization, ORM registration and environment
# loading. Only this repository's standalone edge and metric modules are used.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules" / "cultivation"))
from edge_store import EdgeError, EdgeStore, Scope  # noqa: E402
from adapters.normalized import NormalizedExportAdapter  # noqa: E402
from adapters.base import AdapterError  # noqa: E402
from collector import FileCollector, _plain_path  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--facility", required=True)
    parser.add_argument("--connection", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--contract", required=True, help="Local JSON columns/metric_mappings contract, never credentials")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="One bounded directory pass (or legacy single file)")
    mode.add_argument("--watch", action="store_true", help="Poll explicitly configured --input directory")
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--poll-seconds", type=float, default=2)
    parser.add_argument("--max-scan", type=int, default=100)
    parser.add_argument("--max-files", type=int, default=10)
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
        if args.watch or Path(args.input).is_dir():
            database = Path(args.database)
            if ".." in database.parts:
                raise EdgeError("collector_unsafe_path")
            _plain_path(database.parent)
            if database.exists() or database.is_symlink():
                _plain_path(database)
            _plain_path(args.input)
        store = EdgeStore(args.database)
        scope = Scope(args.organization, args.facility, args.connection)
        if args.watch or Path(args.input).is_dir():
            collector = FileCollector(store, scope, args.input, adapter, format=args.format,
                max_scan=args.max_scan, max_files=args.max_files, poll_seconds=args.poll_seconds)
            stop = threading.Event()
            old = {}
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    old[sig] = signal.signal(sig, lambda *_: stop.set())
                result = collector.run(once=not args.watch, max_iterations=args.max_iterations,
                    stop=stop, report=lambda status: print(json.dumps(status), flush=True))
            finally:
                for sig, handler in old.items():
                    signal.signal(sig, handler)
            return 2 if result.get("transient_errors") or result.get("held_files") else 0
        if args.max_iterations is not None:
            raise EdgeError("watch_directory_required")
        with open(args.input, "rb") as handle:
            content = handle.read(adapter.max_bytes + 1)
        parsed = adapter.parse(content, format=args.format)
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
