from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, Organization
from modules.cultivation.batch_models import CultivationPlantGroup
from services.metrc_cultivation_materialization import MetrcCultivationMaterializer


def test_plant_batch_display_name_is_never_inferred_as_strain():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="Strain Identity", slug="strain-identity", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Cultivation Facility",
            code="MC281234",
            license_number="MC281234",
            cultivation_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        organization_id = organization.id
        facility_id = facility.id

    result = MetrcCultivationMaterializer(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="MC281234",
        actor="admin",
        locations=[],
        plant_batches=[{
            "provider": "metrc",
            "provider_id": "batch-1",
            "name": "GMO CLONES",
            "source": {
                "Id": "batch-1",
                "Name": "GMO CLONES",
                "PlantBatchTypeName": "Clone",
            },
        }],
        vegetative_plants=[],
        flowering_plants=[],
        harvests=[],
    )

    assert result["created_groups"] == 0
    assert result["conflict_count"] == 1
    assert result["conflicts"][0]["code"] == "plant_batch_missing_identity"
    with Session(engine) as session:
        assert list(session.scalars(select(CultivationPlantGroup))) == []
