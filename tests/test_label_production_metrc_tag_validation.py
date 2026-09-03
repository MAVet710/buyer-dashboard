import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.label_studio_workflow import LabelProductionWorkflowService
from modules.regulatory.metrc_process_models import MetrcTagInventory


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    MetrcTagInventory.__table__.create(engine)
    return engine


def test_label_tag_validation_is_local_until_trusted_environment_has_synced_tags():
    engine = _engine()
    service = LabelProductionWorkflowService(engine)
    with Session(engine) as session:
        assert service._validate_synced_package_tag(session, "org-1", "facility-1", "TAG-1", "") == "local_uniqueness_only"
        assert service._validate_synced_package_tag(session, "org-1", "facility-1", "TAG-1", "production") == "local_uniqueness_only"


def test_label_tag_validation_uses_synced_available_package_tags_and_fails_closed():
    engine = _engine()
    service = LabelProductionWorkflowService(engine)
    with Session(engine) as session:
        session.add_all([
            MetrcTagInventory(
                organization_id="org-1",
                facility_id="facility-1",
                jurisdiction_code="MA",
                license_number="MP281234",
                environment="production",
                tag_type="package",
                label="AVAILABLE-TAG",
                status="available",
            ),
            MetrcTagInventory(
                organization_id="org-1",
                facility_id="facility-1",
                jurisdiction_code="MA",
                license_number="MP281234",
                environment="production",
                tag_type="package",
                label="USED-TAG",
                status="used",
            ),
        ])
        session.commit()

        assert service._validate_synced_package_tag(
            session, "org-1", "facility-1", "AVAILABLE-TAG", "production"
        ) == "synced_metrc_available"
        with pytest.raises(ValueError, match="not available in the synchronized METRC package-tag inventory"):
            service._validate_synced_package_tag(
                session, "org-1", "facility-1", "USED-TAG", "production"
            )
        with pytest.raises(ValueError, match="not available in the synchronized METRC package-tag inventory"):
            service._validate_synced_package_tag(
                session, "org-1", "facility-1", "UNKNOWN-TAG", "production"
            )
        # A separately configured sandbox is not treated as synced merely because
        # production tag inventory exists for the same facility.
        assert service._validate_synced_package_tag(
            session, "org-1", "facility-1", "UNKNOWN-TAG", "sandbox"
        ) == "local_uniqueness_only"
