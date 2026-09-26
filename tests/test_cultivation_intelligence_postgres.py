"""Opt-in PostgreSQL 17 release gate against an already migrated disposable DB.

Never reads DATABASE_URL/COMAN_DATABASE_URL, creates roles, stamps, or migrates.
Ordinary fixtures and downgrade attempts are rolled back. Concurrency tests
commit uniquely scoped synthetic fixtures only in this disposable database.
Approved fixtures remain until the CI database is destroyed; no guard is disabled.
"""
import importlib.util
import ipaddress
import os
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0086_cultivation_intelligence"
TABLES = (
    "cultivation_recipes", "cultivation_environment_zones", "cultivation_recipe_stages",
    "cultivation_telemetry_connections", "cultivation_devices", "cultivation_recipe_targets",
    "cultivation_crop_cycles", "cultivation_device_mappings", "cultivation_sensors",
    "cultivation_crop_cycle_plants", "cultivation_crop_cycle_rooms", "cultivation_operational_events",
)


def validated_test_url(environ):
    if environ.get("DOOBIELOGIC_PG_RELEASE_TEST") != "1":
        raise ValueError("Explicit disposable PostgreSQL opt-in is required")
    raw = environ.get("DOOBIELOGIC_TEST_POSTGRES_URL", "")
    try:
        url = make_url(raw)
        host = url.host or ""
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except (ValueError, sa.exc.ArgumentError):
        raise ValueError("A valid loopback disposable PostgreSQL URL is required") from None
    if url.get_backend_name() != "postgresql" or not loopback or url.database != "doobielogic_release_test" or url.query:
        # URL query overrides (host/service/options) could redirect a safe URL.
        raise ValueError("Only the exact loopback disposable test database is permitted")
    return url


@pytest.mark.parametrize("opt,url", [
    (None, "postgresql://localhost/doobielogic_release_test"),
    ("0", "postgresql://localhost/doobielogic_release_test"),
    ("1", "postgresql://example.com/doobielogic_release_test"),
    ("1", "postgresql://127.0.0.1/production"),
    ("1", "postgresql:///doobielogic_release_test"),
    ("1", "postgresql://127.0.0.1/doobielogic_release_test?host=example.com"),
    ("1", "sqlite:///doobielogic_release_test"),
    ("1", ""),
])
def test_postgres_safety_gate_rejects_before_connect(opt, url):
    with pytest.raises(ValueError):
        validated_test_url({"DOOBIELOGIC_PG_RELEASE_TEST": opt, "DOOBIELOGIC_TEST_POSTGRES_URL": url})


@pytest.fixture
def pg():
    if os.environ.get("DOOBIELOGIC_PG_RELEASE_TEST") != "1":
        pytest.skip("Disposable PostgreSQL gate requires DOOBIELOGIC_PG_RELEASE_TEST=1")
    url = validated_test_url(os.environ)  # Must precede create_engine and all SQL.
    engine = sa.create_engine(url, connect_args={
        "connect_timeout": 5, "options": "-c statement_timeout=10000 -c lock_timeout=8000",
    }, hide_parameters=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert connection.scalar(sa.text("SELECT current_database()")) == "doobielogic_release_test"
                assert connection.scalar(sa.text("SHOW server_version_num"))[:2] == "17"
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@pytest.fixture
def fixture_rows(pg):
    return _fixture_rows(pg)


def _fixture_rows(pg):
    from modules.coman.models import AppUser, Facility, Organization
    from modules.cultivation.models import CultivationRoom
    # Import real models to install their canonical relationship metadata.
    from modules.cultivation import intelligence_models  # noqa: F401
    with Session(bind=pg, join_transaction_mode="create_savepoint", expire_on_commit=False) as session:
        with session.begin():
            org = Organization(name="Release acceptance", slug=str(uuid4()))
            other = Organization(name="Other acceptance", slug=str(uuid4()))
            session.add_all([org, other])
            session.flush()
            facility = Facility(organization_id=org.id, code=str(uuid4()), name="Acceptance", cultivation_enabled=True)
            user = AppUser(organization_id=org.id, username=str(uuid4()), normalized_username=str(uuid4()), password_hash="unusable-fixture", role="admin")
            session.add_all([facility, user])
            session.flush()
            room = CultivationRoom(organization_id=org.id, facility_id=facility.id, room_code=str(uuid4()), display_name="Fixture")
            session.add(room)
            session.flush()
        return {"org": org.id, "other_org": other.id, "facility": facility.id, "user": user.id, "room": room.id}


def test_actual_migration_head_columns_scoped_foreign_keys_and_rls(pg):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(cfg)
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == "0085_cultivation_telemetry"
    assert pg.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all() == [REVISION]
    inspector = sa.inspect(pg)
    from modules.coman.models import Base
    from modules.cultivation import intelligence_models  # noqa: F401
    for name in TABLES:
        assert {c.name for c in Base.metadata.tables[name].columns} <= {c["name"] for c in inspector.get_columns(name)}
        foreign_keys = inspector.get_foreign_keys(name)
        assert any(fk["constrained_columns"] == ["organization_id", "facility_id"] and fk["referred_table"] == "coman_facilities" for fk in foreign_keys), name
        assert pg.scalar(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)"), {"name": "public." + name}) is True
    for name, columns in {
        "cultivation_devices": ["organization_id", "facility_id", "connection_id"],
        "cultivation_device_mappings": ["organization_id", "facility_id", "room_id"],
        "cultivation_crop_cycle_plants": ["organization_id", "facility_id", "plant_id"],
        "cultivation_crop_cycle_rooms": ["organization_id", "facility_id", "stage_id"],
    }.items():
        assert any(f["constrained_columns"] == columns for f in inspector.get_foreign_keys(name)), name
    columns = {c["name"]: c for c in inspector.get_columns("cultivation_environment_observations")}
    assert all(columns[name]["nullable"] for name in ("source_metric", "original_value", "original_unit", "raw_reference"))


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_read_or_insert_any_new_table(pg, role):
    assert pg.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}), "CI must create browser roles before migration"
    for name in TABLES:
        for command in (f"SELECT * FROM public.{name} LIMIT 1", f"INSERT INTO public.{name} DEFAULT VALUES"):
            with pg.begin_nested() as savepoint:
                pg.exec_driver_sql(f"SET LOCAL ROLE {role}")
                with pytest.raises(DBAPIError) as error:
                    pg.exec_driver_sql(command)
                assert getattr(error.value.orig, "sqlstate", None) == "42501", "Must fail permission checking, not merely a NOT NULL constraint"
                savepoint.rollback()


def test_runtime_permitted_operations_no_schema_create_and_wrong_tenant_fk(pg, fixture_rows):
    f = fixture_rows
    role = pg.execute(sa.text("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname='doobielogic_render_runtime'")).first()
    assert role and role[0] and not role[1], "CI must establish production-pattern runtime role before migration"
    assert not pg.scalar(sa.text("SELECT has_schema_privilege('doobielogic_render_runtime','public','CREATE')"))
    mutable = {"cultivation_crop_cycles", "cultivation_crop_cycle_plants", "cultivation_crop_cycle_rooms", "cultivation_recipes", "cultivation_telemetry_connections", "cultivation_devices"}
    for name in TABLES:
        for privilege in ("SELECT", "INSERT"):
            assert pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime',:name,:privilege)"), {"name": "public." + name, "privilege": privilege})
        can_update = pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime',:name,'UPDATE')"), {"name": "public." + name})
        assert bool(can_update) == (name in mutable), f"Unexpected UPDATE privilege on {name}"
        assert not pg.scalar(sa.text("SELECT has_table_privilege('doobielogic_render_runtime',:name,'DELETE')"), {"name": "public." + name})
    pg.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
    params = dict(f, id=str(uuid4()))
    pg.execute(sa.text("""INSERT INTO cultivation_telemetry_connections
        (id,organization_id,facility_id,provider,label,mode,status,created_by,version,created_at,updated_at)
        VALUES (:id,:org,:facility,'json','release-fixture','file','configured',:user,1,now(),now())"""), params)
    pg.execute(sa.text("UPDATE cultivation_telemetry_connections SET version=2 WHERE id=:id"), params)
    assert pg.scalar(sa.text("SELECT version FROM cultivation_telemetry_connections WHERE id=:id"), params) == 2
    device = dict(params, device=str(uuid4()))
    pg.execute(sa.text("""INSERT INTO cultivation_devices
        (id,organization_id,facility_id,connection_id,source_device_id,display_name,active,version)
        VALUES (:device,:org,:facility,:id,'sensor','Fixture',true,1)"""), device)
    assert pg.scalar(sa.text("SELECT connection_id FROM cultivation_devices WHERE id=:device"), device) == params["id"]
    with pg.begin_nested() as savepoint:
        with pytest.raises(IntegrityError) as error:
            pg.execute(sa.text("""INSERT INTO cultivation_devices
                (id,organization_id,facility_id,connection_id,source_device_id,display_name,active,version)
                VALUES (:device,:other_org,:facility,:id,'wrong-tenant','Rejected',true,1)"""), dict(device, device=str(uuid4())))
        assert getattr(error.value.orig, "sqlstate", None) == "23503"
        savepoint.rollback()
    with pg.begin_nested() as savepoint:
        with pytest.raises(DBAPIError) as error:
            pg.exec_driver_sql(f'CREATE TABLE public."acceptance_{uuid4().hex}" (id integer)')
        assert getattr(error.value.orig, "sqlstate", None) == "42501"
        savepoint.rollback()
    pg.exec_driver_sql("RESET ROLE")


def test_old_observation_insert_compatibility_and_evidence_protecting_downgrade(pg, fixture_rows):
    f = dict(fixture_rows, id=str(uuid4()), event=str(uuid4()))
    pg.execute(sa.text("""INSERT INTO cultivation_environment_observations
        (id,organization_id,facility_id,room_id,source,event_id,device_id,metric,value,unit,quality,observed_at,received_at)
        VALUES (:id,:org,:facility,:room,'manual',:event,'fixture','temperature',25,'C','valid',now(),now())"""), f)
    assert pg.execute(sa.text("SELECT source_metric,original_value,original_unit,raw_reference FROM cultivation_environment_observations WHERE id=:id"), f).one() == (None, None, None, None)
    pg.execute(sa.text("UPDATE cultivation_environment_observations SET original_value=77,original_unit='F' WHERE id=:id"), f)
    spec = importlib.util.spec_from_file_location("acceptance_migration_0086", ROOT / "migrations/versions/0086_cultivation_intelligence.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pg.begin_nested() as savepoint:
        with Operations.context(MigrationContext.configure(pg)):
            with pytest.raises(RuntimeError, match="evidence exists"):
                migration.downgrade()
        savepoint.rollback()
    assert pg.scalar(sa.text("SELECT original_value FROM cultivation_environment_observations WHERE id=:id"), f) == 77
    assert pg.scalar(sa.text("SELECT version_num FROM alembic_version")) == REVISION


RECIPE_INSERT = sa.text("""INSERT INTO cultivation_recipes
    (id,organization_id,facility_id,name,version,description,status,created_by,created_at,updated_at)
    VALUES (:recipe,:org,:facility,:name,1,'Synthetic guard acceptance','draft',:user,now(),now())""")
STAGE_INSERT = sa.text("""INSERT INTO cultivation_recipe_stages
    (id,organization_id,facility_id,recipe_id,stage_key,display_name,sequence)
    VALUES (:stage,:org,:facility,:recipe,:stage,'Guard acceptance',1)""")
TARGET_INSERT = sa.text("""INSERT INTO cultivation_recipe_targets
    (id,organization_id,facility_id,stage_id,metric,minimum,maximum,unit)
    VALUES (:target,:org,:facility,:stage,'temperature',20,25,'C')""")
APPROVE = sa.text("""UPDATE cultivation_recipes SET status='approved',
    approved_by=:user,approved_at=now() WHERE id=:recipe""")


def _recipe_rows(connection, scope, *, target=True):
    params = dict(scope, recipe=str(uuid4()), stage=str(uuid4()),
                  target=str(uuid4()), name="pg-guard-" + uuid4().hex)
    connection.execute(RECIPE_INSERT, params)
    connection.execute(STAGE_INSERT, params)
    if target:
        connection.execute(TARGET_INSERT, params)
    return params


def _assert_immutable(connection, statement, params, message="approved_recipe_immutable"):
    with connection.begin_nested() as savepoint:
        with pytest.raises(DBAPIError) as error:
            connection.execute(sa.text(statement) if isinstance(statement, str) else statement, params)
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"
        assert error.value.orig.diag.message_primary == message
        savepoint.rollback()


def test_approved_recipe_fields_and_all_child_operations(pg, fixture_rows):
    # Exercise creation/approval/insertion with the actual unchanged runtime grants.
    pg.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
    approved = _recipe_rows(pg, fixture_rows)
    draft = _recipe_rows(pg, fixture_rows)
    pg.execute(APPROVE, approved)
    for assignment in ("name='changed'", "description='changed'", "version=2",
                       "status='draft',approved_by=NULL,approved_at=NULL",
                       "approved_at=now()", "created_by=:user"):
        _assert_immutable(pg, f"UPDATE cultivation_recipes SET {assignment} WHERE id=:recipe", approved)
    _assert_immutable(pg, STAGE_INSERT, dict(approved, stage=str(uuid4())))
    _assert_immutable(pg, TARGET_INSERT, dict(approved, target=str(uuid4())))
    pg.exec_driver_sql("RESET ROLE")
    # Runtime intentionally cannot UPDATE/DELETE children. The migration owner
    # tests the DB invariant for privileged internal SQL without changing grants.
    for statement in (
        "DELETE FROM cultivation_recipes WHERE id=:recipe",
        "UPDATE cultivation_recipe_stages SET display_name='changed' WHERE id=:stage",
        "DELETE FROM cultivation_recipe_stages WHERE id=:stage",
        "UPDATE cultivation_recipe_targets SET minimum=21 WHERE id=:target",
        "DELETE FROM cultivation_recipe_targets WHERE id=:target",
    ):
        _assert_immutable(pg, statement, approved)
    for source, destination in ((draft, approved), (approved, draft)):
        _assert_immutable(pg, "UPDATE cultivation_recipe_stages SET recipe_id=:destination WHERE id=:stage",
                          dict(source, destination=destination["recipe"]), "recipe_parent_immutable")
        _assert_immutable(pg, "UPDATE cultivation_recipe_targets SET stage_id=:destination WHERE id=:target",
                          dict(source, destination=destination["stage"]), "recipe_parent_immutable")


@pytest.fixture
def committed_guard_rows(pg):
    # fixture_rows(pg) is not visible to independent transactions. Deliberately
    # commit a new UUID-isolated organization and pg-guard-* recipe here, only
    # after pg has checked the explicit loopback/exact-name/PG17 safety contract.
    # Never delete approved evidence or relax grants/triggers for cleanup.
    with pg.engine.begin() as connection:
        scope = _fixture_rows(connection)
        connection.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
        params = _recipe_rows(connection, scope, target=False)
    return params


def _wait_for_block(connection, future, pid, blocker):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if future.done():
            pytest.fail(f"Writer finished before locking: {future.result()!r}")
        if connection.scalar(sa.text("SELECT :blocker = ANY(pg_blocking_pids(:pid))"),
                             {"blocker": blocker, "pid": pid}):
            return
        time.sleep(0.02)
    pytest.fail("Writer did not wait on the expected parent transaction")


@pytest.mark.parametrize("child", ["stage", "target"])
@pytest.mark.parametrize("first_writer", ["approval", "child"])
def test_child_insert_and_approval_commit_race(pg, committed_guard_rows, child, first_writer):
    params = dict(committed_guard_rows, target=str(uuid4()))
    if child == "stage":
        params["stage"] = str(uuid4())
    # The committed fixture already owns sequence 1. A stage writer must be a
    # valid insertion so the test cannot fail on unrelated stage uniqueness.
    insertion = sa.text(STAGE_INSERT.text.replace("'Guard acceptance',1)", "'Guard acceptance',2)")) if child == "stage" else TARGET_INSERT
    first, second = (APPROVE, insertion) if first_writer == "approval" else (insertion, APPROVE)
    pids = Queue()

    def writer():
        with pg.engine.connect() as connection:
            try:
                connection.exec_driver_sql("SET LOCAL statement_timeout='10s'")
                connection.exec_driver_sql("SET LOCAL lock_timeout='8s'")
                connection.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
                pids.put(connection.scalar(sa.text("SELECT pg_backend_pid()")))
                connection.execute(second, params)
                connection.commit()
                return "committed", ""
            except DBAPIError as error:
                return getattr(error.orig, "sqlstate", None), error.orig.diag.message_primary
            finally:
                connection.rollback()

    # Roll back/release the blocking transaction before executor shutdown even
    # on assertion failure. Server timeouts bound all worker SQL and joins.
    with ThreadPoolExecutor(max_workers=1) as executor:
        with pg.engine.connect() as first_connection:
            try:
                first_connection.exec_driver_sql("SET LOCAL statement_timeout='10s'")
                first_connection.exec_driver_sql("SET LOCAL lock_timeout='8s'")
                first_connection.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
                blocker = first_connection.scalar(sa.text("SELECT pg_backend_pid()"))
                first_connection.execute(first, params)
                future = executor.submit(writer)
                _wait_for_block(pg, future, pids.get(timeout=5), blocker)
                first_connection.commit()
                state, message = future.result(timeout=12)
                if first_writer == "approval":
                    assert state == "P0001" and message == "approved_recipe_immutable"
                else:
                    assert state == "committed", (state, message)
            finally:
                first_connection.rollback()
    table, key = ("cultivation_recipe_stages", "stage") if child == "stage" else ("cultivation_recipe_targets", "target")
    assert pg.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE id=:id"), {"id": params[key]}) == (first_writer == "child")
    assert pg.scalar(sa.text("SELECT status FROM cultivation_recipes WHERE id=:recipe"), params) == "approved"


def test_draft_child_parent_relationships_are_immutable(pg, fixture_rows):
    # A stage never changes recipe, even while draft. This removes the nested
    # resolution race without SECURITY DEFINER or broader runtime privileges.
    source = _recipe_rows(pg, fixture_rows)
    destination = _recipe_rows(pg, fixture_rows)
    for statement, params in (
        ("UPDATE cultivation_recipe_stages SET recipe_id=:destination WHERE id=:stage",
         dict(source, destination=destination["recipe"])),
        ("UPDATE cultivation_recipe_targets SET stage_id=:destination WHERE id=:target",
         dict(source, destination=destination["stage"])),
    ):
        with pg.begin_nested() as savepoint:
            with pytest.raises(DBAPIError) as error:
                pg.execute(sa.text(statement), params)
            assert getattr(error.value.orig, "sqlstate", None) == "P0001"
            assert error.value.orig.diag.message_primary == "recipe_parent_immutable"
            savepoint.rollback()
    assert pg.scalar(sa.text("SELECT recipe_id FROM cultivation_recipe_stages WHERE id=:stage"), source) == source["recipe"]
    assert pg.scalar(sa.text("SELECT stage_id FROM cultivation_recipe_targets WHERE id=:target"), source) == source["stage"]
    pg.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
    pg.execute(APPROVE, source)
    _assert_immutable(pg, TARGET_INSERT, dict(source, target=str(uuid4())))
    pg.exec_driver_sql("RESET ROLE")


@pytest.mark.parametrize("approved", [False, True])
def test_owner_identity_and_parent_updates_rejected(pg, fixture_rows, approved):
    source = _recipe_rows(pg, fixture_rows)
    destination = _recipe_rows(pg, fixture_rows)
    if approved:
        pg.execute(APPROVE, source)
    for table, key, parent, destination_key in (
        ("cultivation_recipes", "recipe", None, None),
        ("cultivation_recipe_stages", "stage", "recipe_id", "recipe"),
        ("cultivation_recipe_targets", "target", "stage_id", "stage"),
    ):
        columns = ("id", "organization_id", "facility_id") + ((parent,) if parent else ())
        for column in columns:
            for value in (destination[destination_key] if column == parent else str(uuid4()), None):
                _assert_immutable(pg, f"UPDATE {table} SET {column}=:value WHERE id=:identity",
                                  dict(value=value, identity=source[key]), "recipe_parent_immutable")
        assert pg.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE id=:id"), {"id": source[key]}) == 1
    # Permission failures are a separate contract, never evidence of trigger execution.
    pg.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
    for table, key in (("cultivation_recipe_stages", "stage"), ("cultivation_recipe_targets", "target")):
        with pg.begin_nested() as savepoint:
            with pytest.raises(DBAPIError) as error:
                pg.execute(sa.text(f"UPDATE {table} SET id=:new WHERE id=:id"),
                           {"new": str(uuid4()), "id": source[key]})
            assert getattr(error.value.orig, "sqlstate", None) == "42501"
            savepoint.rollback()
    pg.exec_driver_sql("RESET ROLE")


def test_stage_reparent_during_target_insertion_must_fail(pg, committed_guard_rows):
    source = committed_guard_rows
    with pg.engine.begin() as connection:
        destination = _recipe_rows(connection, source)
    # Hold a real target insertion open while owner SQL attempts to move its stage.
    # Parent immutability must win without stage locks or stage UPDATE grants.
    with pg.engine.connect() as insertion, pg.engine.connect() as reparent:
        try:
            insertion.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
            insertion.execute(TARGET_INSERT, dict(source, target=str(uuid4())))
            _assert_immutable(reparent,
                "UPDATE cultivation_recipe_stages SET recipe_id=:destination WHERE id=:stage",
                dict(source, destination=destination["recipe"]), "recipe_parent_immutable")
            insertion.commit()
            reparent.rollback()
        finally:
            insertion.rollback()
            reparent.rollback()
    assert pg.scalar(sa.text("SELECT recipe_id FROM cultivation_recipe_stages WHERE id=:stage"), source) == source["recipe"]
    with pg.engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
        connection.execute(APPROVE, source)
        _assert_immutable(connection, TARGET_INSERT, dict(source, target=str(uuid4())))


def test_referenced_draft_identity_cannot_be_deleted_and_recreated(pg, fixture_rows):
    source = _recipe_rows(pg, fixture_rows)
    for table, key in (("cultivation_recipes", "recipe"), ("cultivation_recipe_stages", "stage")):
        with pg.begin_nested() as savepoint:
            with pytest.raises(DBAPIError) as error:
                pg.execute(sa.text(f"DELETE FROM {table} WHERE id=:id"), {"id": source[key]})
            assert getattr(error.value.orig, "sqlstate", None) == "23503"
            savepoint.rollback()
        assert pg.scalar(sa.text(f"SELECT count(*) FROM {table} WHERE id=:id"), {"id": source[key]}) == 1
