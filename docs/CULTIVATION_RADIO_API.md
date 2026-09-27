# Passive radio discovery and approved sensor links

Status: implementation and validation candidate. Do not infer a deployed release or physical sensor from this document. Frequency evidence is in CULTIVATION_RADIO_FREQUENCIES.md.

## Operator flow

Settings -> Integrations -> Cultivation integrations -> Find nearby sensors. Confirm authorization to identify equipment at the host facility, start a bounded scan, select a supported sensor, choose its canonical room and optional zone, and confirm read-only collection. A linked device remains waiting until a NEW post-approval reading is durably stored. No device ID, credential, JSON or receiver URL needs to be entered by the operator. Host setup of a trusted physical receiver is an administrator prerequisite, not a browser command.

## HTTP contract

Prefix `/api/v1/cultivation-radio`. All routes use normal DoobieLogic authentication and facility/cultivation scope. Host radio configuration is additionally bound to exactly one organization/facility. A different facility cannot scan the same computer, including through its own administrator.

- GET `/status`: enabled, host_matches, can_manage, configured receivers with band and availability reason, limitations and runtime_error. A configured receiver is not proof of successful RF reception.
- GET `/profiles`: exact implemented decoder profiles, units and prerequisites, not automatic support for all devices on a band.
- POST `/scans` with `{receiver_id, authorized:true}`: manager-only, bounded passive discovery; one active scan per host. GET `/scans/{id}` and POST `/scans/{id}/stop` belong to that exact initiating user and scope. Candidate values remain in bounded ephemeral memory, not telemetry history.
- POST `/connections` with `{scan_id,candidate_id,room_id,zone_id,display_name,ownership_confirmed:true}`: validate current candidate and room/zone; atomically create canonical connection/device/sensors/mapping plus RadioBinding and audit. Repeat approval of the same currently linked source reuses the existing binding. No preview measurements are backfilled.
- GET `/connections`: bounded approved links and fresh runtime delivery status. Viewers can inspect approved metadata but cannot scan, approve or disconnect.
- POST `/connections/{id}/disconnect` with `{version}`: optimistic version check and audited disable. Existing telemetry and approval evidence survive. This does not send a command to the sensor.

Scan/candidate IDs are opaque. Candidate names and radio identifiers are untrusted. Link status distinguishes waiting, receiving, review needed, stale, receiver unavailable, collection/storage unavailable and disconnected. A new runtime starts at waiting rather than inventing historical receiver continuity. Current values and receipt timestamps flow through the existing room/cycle evidence store and partial-coverage rules.

Measurement provenance is `trust=unauthenticated_broadcast` and `timestamp_basis=receiver_time`. This is a reception timestamp, not a claim that the sensor supplied a trustworthy sample clock. Radio packets lost before durable local storage cannot be recovered automatically. Equipment control, encryption bypass and automatic Work creation are absent.
