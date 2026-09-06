from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_warehouse_pick_pack_uses_shared_identifier_capture_without_bypassing_server_guard():
    source = (ROOT / "frontend/src/pages/WarehousePickPackPage.tsx").read_text(encoding="utf-8")

    assert 'import { IdentifierCaptureInput } from "../components/IdentifierCaptureInput";' in source
    assert "<IdentifierCaptureInput" in source
    assert "setScan(capture.value)" in source
    assert "setScanSource(capture.source)" in source
    assert 'scan_code:scan' in source
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
