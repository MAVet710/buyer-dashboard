"""Prepare roles only inside the explicitly authorized disposable PostgreSQL gate."""
from __future__ import annotations

import ipaddress
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_url(environ):
    if environ.get("DOOBIELOGIC_PG_RELEASE_TEST") != "1":
        raise ValueError("Explicit disposable PostgreSQL opt-in is required.")
    try:
        url = make_url(environ.get("DOOBIELOGIC_TEST_POSTGRES_URL", ""))
        host = url.host or ""
        local = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except Exception:
        raise ValueError("A valid loopback disposable PostgreSQL URL is required.") from None
    if url.get_backend_name() != "postgresql" or not local or url.database != "doobielogic_release_test" or url.query:
        raise ValueError("Only the exact loopback disposable test database is permitted.")
    return url


def main():
    url = test_url(os.environ)  # Validate before creating an engine or issuing SQL.
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            if connection.scalar(text("SELECT current_database()")) != "doobielogic_release_test":
                raise RuntimeError("Unexpected database; no roles were changed.")
            for role, options in (
                ("anon", "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"),
                ("authenticated", "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"),
                ("doobielogic_render_runtime", "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS"),
            ):
                # Identifiers/options come solely from the fixed literals above.
                exists = connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:name)"), {"name": role})
                if not exists:
                    connection.exec_driver_sql(f"CREATE ROLE {role} {options}")
            connection.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.exec_driver_sql("REVOKE ALL ON SCHEMA public FROM doobielogic_render_runtime")
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon, authenticated, doobielogic_render_runtime")
        print("Disposable PostgreSQL role prerequisites prepared; no blanket table grants.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
