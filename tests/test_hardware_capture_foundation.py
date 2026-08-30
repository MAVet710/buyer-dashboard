from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_camera_scanner_uses_normalized_capture_model_without_breaking_on_code_contract():
    camera = (ROOT / "frontend/src/components/CameraScanner.tsx").read_text(encoding="utf-8")
    capture = (ROOT / "frontend/src/lib/hardwareCapture.ts").read_text(encoding="utf-8")
    identifier_input = (ROOT / "frontend/src/components/IdentifierCaptureInput.tsx").read_text(encoding="utf-8")

    assert "createIdentifierCapture" in camera
    assert "onCode(capture.value)" in camera
    assert "onCapture?.(capture)" in camera
    assert 'source: IdentifierCaptureSource' in capture
    assert '"camera" | "keyboard_wedge" | "manual" | "rfid_reader"' in capture
    assert "CameraScanner" in identifier_input
    assert 'emit("keyboard_wedge")' in identifier_input
    assert 'emit("manual")' in identifier_input


def test_bluetooth_scale_adapter_uses_published_sig_service_and_never_guesses_vendor_protocol():
    scale = (ROOT / "frontend/src/lib/bluetoothWeightScale.ts").read_text(encoding="utf-8")
    scale_ui = (ROOT / "frontend/src/components/BluetoothScaleInput.tsx").read_text(encoding="utf-8")

    assert "WEIGHT_SCALE_SERVICE = 0x181d" in scale
    assert "WEIGHT_MEASUREMENT_CHARACTERISTIC = 0x2a9d" in scale
    assert "rawWeight * 0.005" in scale
    assert "rawWeight * 0.01" in scale
    assert "published standard only" in scale
    assert "separate adapters" in scale
    assert "Vendor-specific protocols are not guessed." in scale_ui
    assert "Capture only" in scale_ui


def test_rfid_contract_is_rain_uhf_vendor_neutral_and_seek_find_is_capability_gated():
    rfid = (ROOT / "frontend/src/lib/rfidReaders.ts").read_text(encoding="utf-8")
    capture = (ROOT / "frontend/src/lib/hardwareCapture.ts").read_text(encoding="utf-8")

    assert '"single_read" | "inventory" | "rssi" | "locate"' in rfid
    assert 'reader.capabilities.has("locate") && reader.capabilities.has("rssi")' in rfid
    assert "KeyboardWedgeRfidReader" in rfid
    assert "inventory sweeps, RSSI, or Seek & Find support" in rfid
    assert "There is no Bluetooth SIG GATT profile for UHF/RAIN RFID reader inventory" in rfid
    assert 'airProtocol: "RAIN_UHF_EPC_GEN2"' in capture
