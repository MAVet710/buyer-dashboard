# DoobieLogic Canonical Operations Foundation

Last reviewed: 2026-09-06

## Purpose

DoobieLogic should feel simple to an operator while preserving deep cannabis genealogy, compliance provenance, financial continuity, and provider reconciliation underneath. This foundation adapts the strongest patterns observed in open cannabis software without creating competing sources of truth or copying another product's architecture wholesale.

## Decisions

### 1. DoobieLogic owns the cannabis domain

Metrc, BioTrack, Dutchie, accounting platforms, laboratories, scanners, and future integrations are external providers. They do not define DoobieLogic's internal business vocabulary.

`modules/canonical_cannabis.py` provides a semantic translation contract for concepts such as:

- plant and plant batch
- harvest
- inventory lot/package
- product/item
- production and extraction run
- laboratory result / COA
- transfer / manifest
- purchase and sales order
- trade partner
- audit and traceability transaction

This is not a new persistence model. Existing authoritative tables remain authoritative.

### 2. Material genealogy remains one graph

`modules/material_lineage` remains the canonical transformation graph. Quantity remains authoritative in the append-only inventory transaction ledger. Cultivation, harvest allocation, production, extraction, Package Studio, labels and downstream detail views should add/query durable lineage edges rather than copying source metadata into disconnected records.

The desired query remains:

`plant -> harvest -> source lot -> transformation/run -> output lot -> packaged product`

and the reverse path must remain queryable from a finished package.

### 3. Audit evidence remains one ledger

`coman_audit_events` remains the general operational audit ledger. `modules/coman/audit.py` adds a backward-compatible `_event` envelope inside `changes_json` with:

- schema version
- source (`user`, `api`, `import`, `system`, `ai_agent`, `rfid`, `scanner`, `provider`, etc.)
- reason
- correlation ID
- before/after state where useful
- provider provenance
- device context
- additional metadata

Legacy top-level change keys are preserved so existing UI/report readers do not break.

Specialized immutable ledgers remain authoritative for their own domain. For example, traceability status/attempt evidence stays in the traceability ledger and inventory quantities stay in the inventory ledger. The general audit event may reference those records; it must not replace them.

### 4. Regulated providers use one contract

`modules/traceability/provider_contract.py` defines a provider-neutral capability and execution-result vocabulary. Registering a provider or declaring a write capability never grants permission to execute it.

The existing fail-closed traceability pipeline remains mandatory:

1. tenant/facility/license scope
2. permission and operating-mode checks
3. trusted provider credential/facility mapping
4. reviewed state/environment write contract
5. deterministic payload validation
6. queued durable transaction
7. provider execution
8. immutable attempt/result evidence
9. provider readback
10. reconciliation / verification

Metrc is the currently implemented regulated provider. BioTrack and future adapters must plug into the same lifecycle rather than introducing parallel business workflows.

### 5. COAs stay normalized and provider-neutral

`modules/inventory_quality/coa.py` already follows a Cannlytics-compatible normalized sample/analyte vocabulary while keeping DoobieLogic provider-neutral. Continue strengthening that one parser/model pipeline rather than adding lab-specific label data stores.

Label Studio should resolve authoritative structured lab values from the selected lot/package genealogy. It should not silently scrape or copy unverified values into a label.

### 6. Purchasing and receiving are one operational chain

Purchase orders use the commercial order source of truth. Receiving posts authoritative lots and inventory transactions. New receipt audit events now share a batch correlation ID and reference the resulting inventory transaction, creating the foundation for one navigable chain:

`buying decision -> purchase order -> approval -> manifest/inbound -> receiving -> COA/release -> inventory -> accounting`

Future approval, manifest and accounting events should reuse the purchase/order or receipt correlation key rather than inventing isolated workflow identifiers.

### 7. RFID and AI are event sources, not privileged mutation paths

RFID/NFC/scanner hardware may observe identity, location and physical inventory. AI may analyze, recommend and draft. Neither bypasses deterministic domain services.

When either causes or supports a reviewed material action, provenance belongs in the same audit envelope (`source=rfid`, `scanner`, or `ai_agent`) and the same underlying inventory/compliance ledgers.

## Architecture shape

Keep a modular monolith unless measured operational needs justify separation. Maintain clean boundaries for:

- auth / tenant / facility context
- canonical domain vocabulary
- inventory
- cultivation
- material lineage
- production / extraction / packaging
- purchasing / commercial
- laboratories / COAs
- labels
- regulatory / traceability providers
- hardware capture
- AI actions
- finance / accounting integrations

Do not split these into independent deployed services merely to imitate another ERP.

## Adoption rule

New material or compliance work should answer four questions before adding storage:

1. Which existing domain owns the authoritative state?
2. Which canonical entity does this represent?
3. Which durable ledger records the mutation or evidence?
4. Which correlation ID lets an operator reconstruct the complete workflow?

If those answers already exist, extend them. Do not create a parallel ledger.
