# DoobieLogic Hardware Capture Architecture

## Purpose

Hardware is an input layer to existing DoobieLogic workflows. A scan, weight, or RFID observation never authorizes an inventory, production, commercial, or regulatory mutation by itself.

The platform normalizes physical observations first, then existing domain workflows decide what the observation means and whether a human is authorized to act on it.

## Canonical capture types

### Identifier

Used for package IDs, lot codes, UPCs, SKUs, barcodes, QR payloads, and other exact identifiers.

Supported sources:

- phone/browser camera
- Bluetooth or USB keyboard-wedge scanner
- manual typed entry
- RFID-originated identifier when a workflow intentionally treats a tag EPC as an identifier

All identifier sources normalize into the same event shape while retaining the raw value and source metadata.

### Weight

A weight observation retains its source unit and also produces deterministic grams for cross-workflow calculations.

Supported foundation transports:

- manual entry
- Bluetooth SIG Weight Scale Service (`0x181D`) / Weight Measurement (`0x2A9D`)

DoobieLogic does not guess proprietary scale protocols. A scale that does not implement the published Bluetooth SIG service requires a documented device-family adapter.

### RFID

RFID observations use the RAIN/UHF EPC Gen2 air-protocol identity model and may include reader metadata such as RSSI and antenna.

RFID capabilities are explicit rather than inferred:

- `single_read` — receive one EPC at a time
- `inventory` — continuous/multi-tag inventory sweep
- `rssi` — reader returns usable signal strength
- `locate` — reader exposes a documented tag-location/continuous observation mode

**Seek & Find requires both `locate` and `rssi`.** A reader that only emits an EPC cannot be marketed or displayed as supporting Seek & Find.

## Reader transport strategy

### Keyboard-wedge RFID

Many readers can be configured by their manufacturer to emit EPC values as keyboard input. DoobieLogic supports this as a low-cost single-tag validation path.

Keyboard-wedge mode does **not** prove support for:

- multi-tag inventory sweeps
- RSSI
- antenna selection
- Locate / Seek & Find

Those capabilities require a richer documented reader protocol.

### Vendor/device-family RFID adapters

There is no Bluetooth SIG universal GATT service for UHF/RAIN reader inventory, RSSI, and Locate operations. DoobieLogic therefore exposes a vendor-neutral adapter contract rather than hard-coding a fake universal Bluetooth UUID.

A reader-specific adapter may be added only when the hardware protocol is documented and testable. It must accurately advertise only the capabilities it can prove.

An adapter that advertises `locate` must provide continuous observations with signal strength suitable for a directional/proximity experience. An adapter that advertises `inventory` must support start/stop inventory behavior rather than simulated repeated single reads.

## Workflow safety

Hardware capture does not bypass:

- organization and facility isolation
- user roles and permissions
- approval workflows
- offline replay allowlists and idempotency
- inventory availability checks
- QA/release gates
- traceability/provider capability gates
- Metrc verification and reconciliation

For example, scanning a package in Warehouse Pick/Pack may prove package identity, but the existing warehouse service still owns reservation and shipment posting. A scale measurement in Extraction may populate a reviewed weight field, but the extraction lifecycle still owns the stage event and any downstream compliance action.

## Offline behavior

The capture model itself can operate while disconnected when the browser/device transport allows it. Whether an action may be queued is a separate decision enforced by the offline mutation allowlist.

Current approved automatic offline mutation remains the exactly-once inventory audit count replay workflow. Adding a scanner, scale, or RFID reader does not automatically make other POST operations replayable.

## Implementation sequence

1. Normalize camera, keyboard-wedge, manual, weight, and RFID observations.
2. Keep the current camera scanner backward compatible while emitting normalized events.
3. Add standards-based Bluetooth scale capture.
4. Add RFID adapter registry and capability gating.
5. Wire shared identifier capture into Inventory Audit and Warehouse Pick/Pack.
6. Wire reviewed scale capture into Extraction and Production measurements.
7. Add real RFID device-family adapters for hardware selected for testing.
8. Add inventory sweep and Seek & Find UI only for readers that prove the required capabilities.
9. Extend approved offline workflows independently, with server idempotency before replay is enabled.

## Non-goals of the foundation

This foundation does not claim that every Bluetooth scale works, that a phone is a UHF RFID reader, that every RFID reader supports Seek & Find, or that any captured hardware observation has already changed operational or regulatory state.
