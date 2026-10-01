"""Real two-connection recipe immutability gate, disposable loopback DB only."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.test_cultivation_intelligence_postgres import validated_test_url


@pytest.fixture
def committed_recipe():
    if os.environ.get("DOOBIELOGIC_PG_RELEASE_TEST") != "1":
        pytest.skip("Requires the explicit disposable PostgreSQL gate")
    url = validated_test_url(os.environ)
    engine = create_engine(url, hide_parameters=True, connect_args={"connect_timeout": 5})
    from modules.coman.models import Organization, Facility, AppUser
    from modules.cultivation.intelligence_models import CultivationRecipe, CultivationRecipeStage
    identities = None
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == "doobielogic_release_test"
            assert connection.scalar(text("SHOW server_version_num")).startswith("17")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0091_security_resilience"
        with Session(engine) as session, session.begin():
            org = Organization(name="Recipe concurrency fixture", slug=str(uuid4()))
            session.add(org)
            session.flush()
            facility = Facility(organization_id=org.id, name="Concurrency fixture", code=str(uuid4()), cultivation_enabled=True)
            user = AppUser(organization_id=org.id, username=str(uuid4()), normalized_username=str(uuid4()), password_hash="unusable-fixture", role="admin")
            session.add_all([facility, user])
            session.flush()
            recipe = CultivationRecipe(organization_id=org.id, facility_id=facility.id, name="Concurrency fixture", version=1, status="draft", created_by=user.id)
            session.add(recipe)
            session.flush()
            stage = CultivationRecipeStage(organization_id=org.id, facility_id=facility.id, recipe_id=recipe.id, stage_key="fixture", display_name="Fixture", sequence=1)
            session.add(stage)
            session.flush()
            identities = {"org": org.id, "facility": facility.id, "user": user.id, "recipe": recipe.id, "stage": stage.id}
        # Committed synthetic parent rows are necessary for independent connections.
        yield engine, identities
    finally:
        if identities is not None:
            with engine.begin() as connection:
                for table, column, value in (
                    ("cultivation_recipe_targets", "stage_id", identities["stage"]),
                    ("cultivation_recipe_stages", "recipe_id", identities["recipe"]),
                    ("cultivation_recipes", "id", identities["recipe"]),
                    ("coman_facilities", "id", identities["facility"]),
                    ("app_users", "id", identities["user"]),
                    ("coman_organizations", "id", identities["org"]),
                ):
                    connection.execute(text(f"DELETE FROM {table} WHERE {column}=:id"), {"id": value})
        engine.dispose()


@pytest.mark.parametrize("child", ["stage", "target"])
@pytest.mark.parametrize("first_writer", ["approval", "child"])
def test_approval_serializes_with_child_insertion(committed_recipe, child, first_writer):
    engine, scope = committed_recipe
    params = dict(scope, id=str(uuid4()))
    approval = text("UPDATE cultivation_recipes SET status='approved', approved_by=:user, approved_at=now() WHERE id=:recipe")
    insertion = text(
        "INSERT INTO cultivation_recipe_stages (id,organization_id,facility_id,recipe_id,stage_key,display_name,sequence) "
        "VALUES (:id,:org,:facility,:recipe,'new-stage','New stage',2)"
        if child == "stage" else
        "INSERT INTO cultivation_recipe_targets (id,organization_id,facility_id,stage_id,metric,minimum,maximum,unit) "
        "VALUES (:id,:org,:facility,:stage,'temperature',20,24,'C')"
    )
    first, second = (approval, insertion) if first_writer == "approval" else (insertion, approval)
    with engine.connect() as a, engine.connect() as b:
        ta, tb = a.begin(), b.begin()
        try:
            for connection in (a, b):
                connection.exec_driver_sql("SET LOCAL ROLE doobielogic_render_runtime")
                connection.exec_driver_sql("SET LOCAL lock_timeout = '500ms'")
            a.execute(first, params)
            with pytest.raises(DBAPIError) as failure:
                b.execute(second, params)
            assert getattr(failure.value.orig, "sqlstate", None) == "55P03", "Must serialize on the recipe lock, not fail an unrelated constraint"
        finally:
            tb.rollback()
            ta.rollback()
