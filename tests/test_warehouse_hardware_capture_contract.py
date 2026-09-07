from pathlib import Path

from modules.hardware_capture_provenance import IdentifierCaptureProvenance


ROOT = Path(__file__).resolve().parents[1]


def test_warehouse_pick_pack_uses_shared_identifier_capture_without_bypassing_server_guard():
    source = (ROOT / "frontend/src/pages/WarehousePickPackPage.tsx").read_text(encoding="utf-8")

    assert 'import { IdentifierCaptureInput } from "../components/IdentifierCaptureInput";' in source
    assert "<IdentifierCaptureInput" in source
    assert "setScan(capture.value)" in source
    assert "setScanSource(capture.source)" in source
    assert "setScanDeviceId(capture.deviceId" in source
    assert "setScanSymbology(capture.symbology" in source
    assert "setScanAt(capture.capturedAt)" in source
    assert 'scan_code:scan' in source
    assert "capture_source:scanSource" in source
    assert "capture_device_id:scanDeviceId" in source
    assert "capture_symbology:scanSymbology" in source
    assert "capture_at:scanAt" in source
    assert "const scanned=selected?matches(selected,scan):false" in source
    assert 'disabled={!scanned||quantity<=0||reserve.isPending||ship.isPending}' in source
    assert "phone camera" in source
    assert "keyboard-wedge RFID reader" in source


def test_hardware_capture_remains_input_only():
    source = (ROOT / "frontend/src/components/IdentifierCaptureInput.tsx").read_text(encoding="utf-8")
    warehouse = (ROOT / "frontend/src/pages/WarehousePickPackPage.tsx").read_text(encoding="utf-8")

    assert "onCapture" in source
    assert "/api/v1/warehouse/pick" not in source
    assert '/api/v1/warehouse/pick' in warehouse
    assert "Capture provenance is audit evidence only" in warehouse


def test_warehouse_backend_preserves_server_guard_and_canonical_audit_envelope():
    source = (ROOT / "backend/app/routers/warehouse.py").read_text(encoding="utf-8")

    # Capture metadata does not replace the existing server-side lot identity check.
    assert "Scanned code does not match the selected lot. Nothing was posted." in source
    assert "matched_identifier_type" in source
    assert "IdentifierCaptureProvenance.build" in source
    assert "record_audit_event" in source
    assert 'action="warehouse_capture_verified"' in source
    assert 'action=result_action' in source
    assert 'metadata={"capture_is_authorization": False}' in source
    assert "repo.allocate_lot" in source
    assert "repo.post_fulfillment" in source


def test_capture_sources_map_to_provenance_without_granting_authority():
    rfid = IdentifierCaptureProvenance.build(
        source="rfid_reader",
        device_id="reader-7",
        symbology="EPC",
        captured_at="2026-09-06T19:30:00-04:00",
    )
    assert rfid.audit_source == "rfid"
    assert rfid.device_metadata() == {
        "capture_source": "rfid_reader",
        "device_id": "reader-7",
        "symbology": "EPC",
        "captured_at": "2026-09-06T19:30:00-04:00",
    }
    assert IdentifierCaptureProvenance.build(source="camera").audit_source == "scanner"
    assert IdentifierCaptureProvenance.build(source="keyboard_wedge").audit_source == "scanner"
    assert IdentifierCaptureProvenance.build(source="manual").audit_source == "user"
