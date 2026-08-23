from pathlib import Path
from types import SimpleNamespace

from backend.app.routers.admin import _metadata_context


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class FakeSession:
    def __init__(self, facility=None):
        self.facility = facility
        self.scalar_calls = 0

    def scalar(self, _statement):
        self.scalar_calls += 1
        return self.facility


def test_zero_facility_assignment_is_binding_streamlit_admin_behavior():
    streamlit = read("modules/admin/user_management.py")
    react = read("frontend/src/pages/AdminPage.tsx")
    backend = read("backend/app/routers/admin.py")

    phrase = "No selections means the user has no facility workspace access."
    assert phrase in streamlit
    assert phrase in react
    assert "Choose at least one facility for this account." not in react
    assert "Assign at least one facility so the user has an operational access context." not in backend
    assert backend.count("_metadata_context(") >= 3


def test_standard_zero_facility_account_does_not_invent_workspace_access():
    session = FakeSession()
    context = SimpleNamespace(organization_id="creator-org", facility_id="creator-facility")
    organization = SimpleNamespace(id="assigned-org")

    organization_id, facility_id = _metadata_context(session, context, "buyer", organization, [])

    assert organization_id == "assigned-org"
    assert facility_id == ""
    assert session.scalar_calls == 0


def test_admin_zero_explicit_facilities_keeps_org_wide_access_context():
    session = FakeSession(SimpleNamespace(id="first-active-facility"))
    context = SimpleNamespace(organization_id="creator-org", facility_id="creator-facility")
    organization = SimpleNamespace(id="assigned-org")

    organization_id, facility_id = _metadata_context(session, context, "admin", organization, [])

    assert organization_id == "assigned-org"
    assert facility_id == "first-active-facility"
    assert session.scalar_calls == 1


def test_signed_in_zero_facility_account_stops_before_workspace_api_gates():
    auth_gate = read("frontend/src/components/AuthGate.tsx")

    assert "No facility workspace access" in auth_gate
    assert "refreshSession" in auth_gate
    assert "buyer-dash-facility" in auth_gate
    no_access = auth_gate.index("No facility workspace access")
    legal_gate = auth_gate.rindex("<PasswordGate><LegalGate>")
    assert no_access < legal_gate
