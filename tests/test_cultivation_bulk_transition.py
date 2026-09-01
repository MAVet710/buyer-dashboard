from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.demo_data import ensure_coman_demo_dataset
from modules.coman.models import Base, Facility
from services.demo_data import build_demo_payload


def _client(role: str = "operator") -> tuple[TestClient, dict[str, str]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    seeded = ensure_coman_demo_dataset(
        state={},
        actor="bulk-cultivation-seed",
        payload=build_demo_payload(date(2026, 8, 31), scale="small"),
        engine=engine,
    )
    with Session(engine) as session, session.begin():
        facility = session.get(Facility, seeded["facility_id"])
        assert facility is not None
        facility.cultivation_enabled = True
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    headers = {
        "X-Organization-Id": seeded["organization_id"],
        "X-Facility-Id": seeded["facility_id"],
        "X-User-Id": "bulk-cultivation-operator",
        "X-User-Role": role,
    }
    return TestClient(app, raise_server_exceptions=False), headers


def _room(client: TestClient, headers: dict[str, str], code: str, phase: str, capacity: int):
    response = client.post(
        "/api/v1/inventory/production/plants/rooms",
        headers=headers,
        json={
            "room_code": code,
            "display_name": code,
            "phase": phase,
            "plant_capacity": capacity,
            "active": True,
        },
    )
    assert response.status_code == 200, response.text


def _plant(client: TestClient, headers: dict[str, str], tag: str, phase: str, room: str):
    response = client.post(
        "/api/v1/inventory/production/plants",
        headers=headers,
        json={"plant_tag": tag, "strain_name": "Atomic Kush", "phase": phase, "room_code": room},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bulk_transition_moves_all_selected_plants_atomically():
    client, headers = _client()
    try:
        _room(client, headers, "BULK-VEG", "vegetative", 2)
        first = _plant(client, headers, "BULK-001", "seedling", "NURSERY-A")
        second = _plant(client, headers, "BULK-002", "seedling", "NURSERY-A")

        moved = client.post(
            "/api/v1/inventory/production/plants/bulk-transition",
            headers=headers,
            json={
                "plant_ids": [first["id"], second["id"]],
                "phase": "vegetative",
                "room_code": "BULK-VEG",
                "reason": "Veg room move",
            },
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["count"] == 2
        assert moved.json()["changed_count"] == 2
        assert {row["phase"] for row in moved.json()["items"]} == {"vegetative"}
        assert {row["room_code"] for row in moved.json()["items"]} == {"BULK-VEG"}
    finally:
        app.dependency_overrides.clear()


def test_bulk_transition_capacity_failure_changes_nothing():
    client, headers = _client()
    try:
        _room(client, headers, "CAP-VEG", "vegetative", 1)
        existing = _plant(client, headers, "CAP-001", "vegetative", "CAP-VEG")
        candidate = _plant(client, headers, "CAP-002", "seedling", "NURSERY-B")

        blocked = client.post(
            "/api/v1/inventory/production/plants/bulk-transition",
            headers=headers,
            json={"plant_ids": [candidate["id"]], "phase": "vegetative", "room_code": "CAP-VEG"},
        )
        assert blocked.status_code == 422, blocked.text
        assert "capacity" in blocked.text.casefold()

        plants = client.get("/api/v1/inventory/production/plants", headers=headers)
        assert plants.status_code == 200
        by_id = {row["id"]: row for row in plants.json()}
        assert by_id[existing["id"]]["phase"] == "vegetative"
        assert by_id[existing["id"]]["room_code"] == "CAP-VEG"
        assert by_id[candidate["id"]]["phase"] == "seedling"
        assert by_id[candidate["id"]]["room_code"] == "NURSERY-B"
    finally:
        app.dependency_overrides.clear()


def test_one_invalid_lifecycle_transition_rolls_back_entire_selection():
    client, headers = _client()
    try:
        _room(client, headers, "FLOWER-A", "flowering", 10)
        valid = _plant(client, headers, "ROLLBACK-VEG", "vegetative", "VEG-A")
        invalid = _plant(client, headers, "ROLLBACK-SEED", "seedling", "NURSERY-C")

        blocked = client.post(
            "/api/v1/inventory/production/plants/bulk-transition",
            headers=headers,
            json={
                "plant_ids": [valid["id"], invalid["id"]],
                "phase": "flowering",
                "room_code": "FLOWER-A",
                "reason": "Atomic rollback probe",
            },
        )
        assert blocked.status_code == 422, blocked.text
        assert "cannot move from seedling to flowering" in blocked.text

        plants = client.get("/api/v1/inventory/production/plants", headers=headers)
        by_id = {row["id"]: row for row in plants.json()}
        assert by_id[valid["id"]]["phase"] == "vegetative"
        assert by_id[valid["id"]]["room_code"] == "VEG-A"
        assert by_id[invalid["id"]]["phase"] == "seedling"
        assert by_id[invalid["id"]]["room_code"] == "NURSERY-C"
    finally:
        app.dependency_overrides.clear()


def test_bulk_transition_respects_cultivation_write_roles():
    client, headers = _client(role="read_only")
    try:
        denied = client.post(
            "/api/v1/inventory/production/plants/bulk-transition",
            headers=headers,
            json={"plant_ids": ["not-used"], "phase": "vegetative"},
        )
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
