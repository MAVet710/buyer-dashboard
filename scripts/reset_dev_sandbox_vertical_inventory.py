"""CLI compatibility wrapper for the production-image DEV reset job."""
from modules.coman.dev_sandbox_reset_job import _current_inventory, _engine, _scope, _validate, main, run

__all__ = ["_current_inventory", "_engine", "_scope", "_validate", "main", "run"]


if __name__ == "__main__":
    main()
