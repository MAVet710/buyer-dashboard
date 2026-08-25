"""Provider-neutral sandbox integration runtime.

This module deliberately exercises the same durable cursor, raw-record, normalization,
deduplication, retry, and reconciliation seams that production adapters will use,
without making external writes. The built-in adapters are deterministic sandbox
fixtures until a vendor's authenticated sandbox API transport is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping
import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Facility, utc_now
from .models import IntegrationSyncAttempt, IntegrationSyncRecord, IntegrationSyncState
from .service import IntegrationConfigurationService


PROVIDER_IDS = {
    "metrc": "metrc_sandbox",
    "dutchie": "dutchie_sandbox",
    "biotrack": "biotrack_sandbox",
    "quickbooks": "quickbooks_sandbox",
}

SENSITIVE_TOKENS = {
    "authorization",
    "apikey",
    "clientsecret",
    "password",
    "secret",
    "token",
    "accesstoken",
    "refreshtoken",
}


def _key_token(value: Any) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _key_token(key) in SENSITIVE_TOKENS else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(sanitize(dict(value)), sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, scope_seed: str, index: int) -> str:
    digest = hashlib.sha256(f"{prefix}:{scope_seed}:{index}".encode("utf-8")).hexdigest()[:14].upper()
    return f"{prefix}-{digest}"


@dataclass(frozen=True)
class SandboxFetchResult:
    records: list[dict[str, Any]]
    next_cursor: str
    transport: str = "deterministic_fixture"


class SandboxAdapter:
    provider: str = ""
    resources: tuple[str, ...] = ()

    def fetch(
        self,
        *,
        resource: str,
        cursor: str,
        configuration: Mapping[str, Any],
        secret: str,
        scope_seed: str,
    ) -> SandboxFetchResult:
        if resource not in self.resources:
            raise ValueError(f"{self.provider} sandbox does not expose resource {resource!r}.")
        if not str(secret or "").strip():
            raise ValueError(f"{self.provider} sandbox credential is not configured.")
        records = self.fixture_records(resource=resource, configuration=configuration, scope_seed=scope_seed)
        return SandboxFetchResult(records=records, next_cursor="fixture-v1")

    def fixture_records(
        self,
        *,
        resource: str,
        configuration: Mapping[str, Any],
        scope_seed: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def normalize(self, resource: str, record: Mapping[str, Any]) -> dict[str, Any]:
        external_id = str(record.get("id") or record.get("external_id") or record.get("label") or "").strip()
        if not external_id:
            raise ValueError("Sandbox provider record is missing a stable external identifier.")
        return {
            "provider": self.provider,
            "resource": resource,
            "external_id": external_id,
            "environment": "sandbox",
            "payload": sanitize(record),
        }


class MetrcSandboxAdapter(SandboxAdapter):
    provider = "metrc"
    resources = ("packages", "transfers", "items")

    def fixture_records(self, *, resource: str, configuration: Mapping[str, Any], scope_seed: str) -> list[dict[str, Any]]:
        state = str(configuration.get("state") or "MA").upper()
        license_number = str(configuration.get("license_number") or "SANDBOX")
        if resource == "packages":
            return [
                {
                    "id": _stable_id("METRC-PKG", scope_seed, index),
                    "label": _stable_id("1A4", scope_seed, index),
                    "item": name,
                    "quantity": quantity,
                    "unit": "g",
                    "status": "Active",
                    "license_number": license_number,
                    "state": state,
                }
                for index, (name, quantity) in enumerate((("Sandbox Flower", 1250.0), ("Sandbox Distillate", 420.0), ("Sandbox Live Resin", 210.0)), 1)
            ]
        if resource == "transfers":
            return [
                {
                    "id": _stable_id("METRC-XFER", scope_seed, index),
                    "manifest_number": _stable_id("MAN", scope_seed, index),
                    "direction": "incoming" if index == 1 else "outgoing",
                    "status": "Scheduled",
                    "license_number": license_number,
                    "state": state,
                }
                for index in range(1, 3)
            ]
        return [
            {"id": _stable_id("METRC-ITEM", scope_seed, index), "name": name, "category": category, "state": state}
            for index, (name, category) in enumerate((("Sandbox Flower", "Buds"), ("Sandbox Distillate", "Concentrate"), ("Sandbox Live Resin", "Concentrate")), 1)
        ]


class DutchieSandboxAdapter(SandboxAdapter):
    provider = "dutchie"
    resources = ("sales", "inventory", "catalog")

    def fixture_records(self, *, resource: str, configuration: Mapping[str, Any], scope_seed: str) -> list[dict[str, Any]]:
        location_id = str(configuration.get("location_id") or "sandbox-location")
        products = (("DL-SBX-001", "Sandbox Blue Dream", 34.0), ("DL-SBX-002", "Sandbox GMO Pre-Roll", 14.0), ("DL-SBX-003", "Sandbox Live Resin Cart", 42.0))
        if resource == "sales":
            return [
                {
                    "id": _stable_id("DUTCHIE-SALE", scope_seed, index),
                    "location_id": location_id,
                    "sold_at": f"2026-08-{20 + index:02d}T15:00:00Z",
                    "sku": sku,
                    "product_name": name,
                    "quantity": float(index),
                    "net_sales": price * index,
                }
                for index, (sku, name, price) in enumerate(products, 1)
            ]
        if resource == "inventory":
            return [
                {
                    "id": _stable_id("DUTCHIE-INV", scope_seed, index),
                    "location_id": location_id,
                    "sku": sku,
                    "product_name": name,
                    "on_hand": float(20 * index),
                    "unit_cost": round(price * 0.45, 2),
                    "retail_price": price,
                }
                for index, (sku, name, price) in enumerate(products, 1)
            ]
        return [
            {
                "id": _stable_id("DUTCHIE-CAT", scope_seed, index),
                "location_id": location_id,
                "sku": sku,
                "name": name,
                "price": price,
                "active": True,
            }
            for index, (sku, name, price) in enumerate(products, 1)
        ]

    def normalize(self, resource: str, record: Mapping[str, Any]) -> dict[str, Any]:
        normalized = super().normalize(resource, record)
        if resource == "sales":
            normalized["sale"] = {
                "source_record_id": str(record["id"]),
                "sold_at": str(record.get("sold_at") or ""),
                "sku": str(record.get("sku") or ""),
                "product_name": str(record.get("product_name") or ""),
                "quantity": float(record.get("quantity") or 0),
                "net_sales": float(record.get("net_sales") or 0),
            }
        elif resource == "inventory":
            normalized["inventory"] = {
                "sku": str(record.get("sku") or ""),
                "product_name": str(record.get("product_name") or ""),
                "on_hand": float(record.get("on_hand") or 0),
                "unit_cost": float(record.get("unit_cost") or 0),
                "retail_price": float(record.get("retail_price") or 0),
            }
        return normalized


class BioTrackSandboxAdapter(SandboxAdapter):
    provider = "biotrack"
    resources = ("inventory", "transfers", "plants")

    def fixture_records(self, *, resource: str, configuration: Mapping[str, Any], scope_seed: str) -> list[dict[str, Any]]:
        state = str(configuration.get("state") or "sandbox").upper()
        license_number = str(configuration.get("license_number") or "SANDBOX")
        if resource == "inventory":
            return [
                {"id": _stable_id("BT-INV", scope_seed, i), "name": name, "quantity": qty, "unit": "g", "state": state, "license_number": license_number}
                for i, (name, qty) in enumerate((("Sandbox Bulk Flower", 1800.0), ("Sandbox Oil", 560.0), ("Sandbox WIP", 300.0)), 1)
            ]
        if resource == "plants":
            return [
                {"id": _stable_id("BT-PLANT", scope_seed, i), "strain": strain, "phase": phase, "state": state, "license_number": license_number}
                for i, (strain, phase) in enumerate((("Sandbox GMO", "flower"), ("Sandbox Blue Dream", "vegetative"), ("Sandbox OG", "flower")), 1)
            ]
        return [
            {"id": _stable_id("BT-XFER", scope_seed, i), "status": "pending", "direction": direction, "state": state, "license_number": license_number}
            for i, direction in enumerate(("incoming", "outgoing"), 1)
        ]


class QuickBooksSandboxAdapter(SandboxAdapter):
    provider = "quickbooks"
    resources = ("invoices", "payments", "items")

    def fixture_records(self, *, resource: str, configuration: Mapping[str, Any], scope_seed: str) -> list[dict[str, Any]]:
        realm_id = str(configuration.get("realm_id") or "sandbox-realm")
        if resource == "invoices":
            return [
                {"id": _stable_id("QB-INV", scope_seed, i), "realm_id": realm_id, "customer": customer, "total": total, "balance": balance, "status": "Open" if balance else "Paid"}
                for i, (customer, total, balance) in enumerate((("Sandbox Retailer A", 2400.0, 800.0), ("Sandbox Retailer B", 1750.0, 0.0), ("Sandbox Retailer C", 3100.0, 3100.0)), 1)
            ]
        if resource == "payments":
            return [
                {"id": _stable_id("QB-PMT", scope_seed, i), "realm_id": realm_id, "customer": customer, "amount": amount, "method": "ACH"}
                for i, (customer, amount) in enumerate((("Sandbox Retailer A", 1600.0), ("Sandbox Retailer B", 1750.0)), 1)
            ]
        return [
            {"id": _stable_id("QB-ITEM", scope_seed, i), "realm_id": realm_id, "sku": sku, "name": name, "income_account": "Cannabis Sales"}
            for i, (sku, name) in enumerate((("DL-SBX-001", "Sandbox Blue Dream"), ("DL-SBX-002", "Sandbox GMO Pre-Roll"), ("DL-SBX-003", "Sandbox Live Resin Cart")), 1)
        ]


ADAPTERS: dict[str, SandboxAdapter] = {
    "metrc": MetrcSandboxAdapter(),
    "dutchie": DutchieSandboxAdapter(),
    "biotrack": BioTrackSandboxAdapter(),
    "quickbooks": QuickBooksSandboxAdapter(),
}


class SandboxIntegrationRuntime:
    """Durable sandbox feed runner with production-write isolation."""

    def __init__(self, engine: Engine, encryption_key: str):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.configurations = IntegrationConfigurationService(engine, encryption_key)

    @staticmethod
    def scope_key(organization_id: str, facility_id: str) -> str:
        return f"{organization_id}:{facility_id}:sandbox"

    def capabilities(self, provider: str) -> dict[str, Any]:
        adapter = self._adapter(provider)
        return {
            "provider": provider,
            "provider_id": PROVIDER_IDS[provider],
            "environment": "sandbox",
            "resources": list(adapter.resources),
            "read_mode": "deterministic_fixture",
            "production_writes_enabled": False,
            "adapter_contract_ready": True,
        }

    def sync(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        actor: str,
        resource: str = "",
    ) -> dict[str, Any]:
        adapter = self._adapter(provider)
        self._validate_scope(organization_id, facility_id)
        row = self.configurations.get("facility", self.scope_key(organization_id, facility_id), PROVIDER_IDS[provider])
        if row is None or not row.encrypted_secret:
            raise ValueError(f"Save {provider} sandbox credentials before running a sandbox sync.")
        configuration = self.configurations.public(row).get("configuration") or {}
        if str(configuration.get("environment") or "").casefold() != "sandbox":
            raise ValueError("Sandbox runtime refuses non-sandbox integration configuration.")
        secret = self.configurations.secret(row)
        resources = (resource.strip().casefold(),) if resource.strip() else adapter.resources
        invalid = [name for name in resources if name not in adapter.resources]
        if invalid:
            raise ValueError(f"{provider} sandbox resource {invalid[0]!r} is not supported.")
        summaries = [
            self._sync_resource(
                organization_id=organization_id,
                facility_id=facility_id,
                provider=provider,
                resource=name,
                actor=actor,
                adapter=adapter,
                configuration=configuration,
                secret=secret,
            )
            for name in resources
        ]
        return {
            "provider": provider,
            "environment": "sandbox",
            "production_writes_enabled": False,
            "transport": "deterministic_fixture",
            "resources": summaries,
            "totals": {
                "records": sum(item["record_count"] for item in summaries),
                "accepted": sum(item["accepted_count"] for item in summaries),
                "duplicates": sum(item["duplicate_count"] for item in summaries),
                "errors": sum(item["error_count"] for item in summaries),
            },
        }

    def retry_failed(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        actor: str,
    ) -> dict[str, Any]:
        adapter = self._adapter(provider)
        with self.sessions() as session:
            failed = list(
                session.scalars(
                    select(IntegrationSyncState).where(
                        IntegrationSyncState.organization_id == organization_id,
                        IntegrationSyncState.facility_id == facility_id,
                        IntegrationSyncState.provider == PROVIDER_IDS[provider],
                        IntegrationSyncState.status == "failed",
                    )
                )
            )
        if not failed:
            return {"provider": provider, "environment": "sandbox", "retried": 0, "resources": []}
        results = []
        for state in failed:
            results.append(
                self.sync(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider=provider,
                    actor=actor,
                    resource=state.resource,
                )
            )
        return {"provider": provider, "environment": "sandbox", "retried": len(results), "resources": results}

    def status(self, *, organization_id: str, facility_id: str, provider: str) -> dict[str, Any]:
        adapter = self._adapter(provider)
        provider_id = PROVIDER_IDS[provider]
        with self.sessions() as session:
            states = list(
                session.scalars(
                    select(IntegrationSyncState)
                    .where(
                        IntegrationSyncState.organization_id == organization_id,
                        IntegrationSyncState.facility_id == facility_id,
                        IntegrationSyncState.provider == provider_id,
                    )
                    .order_by(IntegrationSyncState.resource)
                )
            )
            attempts = list(
                session.scalars(
                    select(IntegrationSyncAttempt)
                    .where(
                        IntegrationSyncAttempt.organization_id == organization_id,
                        IntegrationSyncAttempt.facility_id == facility_id,
                        IntegrationSyncAttempt.provider == provider_id,
                    )
                    .order_by(IntegrationSyncAttempt.started_at.desc())
                    .limit(12)
                )
            )
        return {
            **self.capabilities(provider),
            "states": [self._state_public(state) for state in states],
            "recent_attempts": [self._attempt_public(attempt) for attempt in attempts],
            "configured_resources": list(adapter.resources),
        }

    def _sync_resource(
        self,
        *,
        organization_id: str,
        facility_id: str,
        provider: str,
        resource: str,
        actor: str,
        adapter: SandboxAdapter,
        configuration: Mapping[str, Any],
        secret: str,
    ) -> dict[str, Any]:
        provider_id = PROVIDER_IDS[provider]
        run_id = str(uuid.uuid4())
        started = utc_now()
        with self.sessions.begin() as session:
            state = session.scalar(
                select(IntegrationSyncState).where(
                    IntegrationSyncState.organization_id == organization_id,
                    IntegrationSyncState.facility_id == facility_id,
                    IntegrationSyncState.provider == provider_id,
                    IntegrationSyncState.resource == resource,
                )
            )
            if state is None:
                state = IntegrationSyncState(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    provider=provider_id,
                    resource=resource,
                    environment="sandbox",
                    updated_by=actor,
                )
                session.add(state)
                session.flush()
            cursor_before = state.cursor
            state.status = "running"
            state.last_started_at = started
            state.last_error = ""
            state.updated_by = actor
            attempt = IntegrationSyncAttempt(
                organization_id=organization_id,
                facility_id=facility_id,
                provider=provider_id,
                resource=resource,
                run_id=run_id,
                status="running",
                cursor_before=cursor_before,
                actor=actor,
                started_at=started,
            )
            session.add(attempt)

        try:
            result = adapter.fetch(
                resource=resource,
                cursor=cursor_before,
                configuration=configuration,
                secret=secret,
                scope_seed=f"{organization_id}:{facility_id}",
            )
            accepted = 0
            duplicates = 0
            errors = 0
            with self.sessions.begin() as session:
                for record in result.records:
                    clean_record = sanitize(record)
                    fingerprint = _fingerprint(clean_record)
                    existing = session.scalar(
                        select(IntegrationSyncRecord.id).where(
                            IntegrationSyncRecord.organization_id == organization_id,
                            IntegrationSyncRecord.facility_id == facility_id,
                            IntegrationSyncRecord.provider == provider_id,
                            IntegrationSyncRecord.resource == resource,
                            IntegrationSyncRecord.fingerprint == fingerprint,
                        )
                    )
                    if existing:
                        duplicates += 1
                        continue
                    external_id = str(record.get("id") or record.get("external_id") or record.get("label") or "").strip()
                    try:
                        normalized = adapter.normalize(resource, record)
                        record_status = "accepted"
                        error_message = ""
                        accepted += 1
                    except Exception as exc:
                        normalized = {}
                        record_status = "error"
                        error_message = f"{type(exc).__name__}: {exc}"[:512]
                        errors += 1
                    session.add(
                        IntegrationSyncRecord(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            provider=provider_id,
                            resource=resource,
                            run_id=run_id,
                            external_id=external_id,
                            fingerprint=fingerprint,
                            raw_payload_json=_json(clean_record),
                            normalized_payload_json=_json(normalized),
                            status=record_status,
                            error_message=error_message,
                            received_at=utc_now(),
                        )
                    )

                completed = utc_now()
                state = session.scalar(
                    select(IntegrationSyncState).where(
                        IntegrationSyncState.organization_id == organization_id,
                        IntegrationSyncState.facility_id == facility_id,
                        IntegrationSyncState.provider == provider_id,
                        IntegrationSyncState.resource == resource,
                    )
                )
                state.cursor = result.next_cursor
                state.status = "succeeded" if errors == 0 else "failed"
                state.last_completed_at = completed
                if errors == 0:
                    state.last_success_at = completed
                state.last_error = "" if errors == 0 else f"{errors} record(s) failed normalization."
                state.records_seen += len(result.records)
                state.records_written += accepted + errors
                state.updated_by = actor
                attempt = session.scalar(select(IntegrationSyncAttempt).where(IntegrationSyncAttempt.run_id == run_id))
                attempt.status = "succeeded" if errors == 0 else "failed"
                attempt.cursor_after = result.next_cursor
                attempt.record_count = len(result.records)
                attempt.accepted_count = accepted
                attempt.duplicate_count = duplicates
                attempt.error_count = errors
                attempt.error_message = state.last_error
                attempt.completed_at = completed
            return {
                "resource": resource,
                "run_id": run_id,
                "status": "succeeded" if errors == 0 else "failed",
                "cursor_before": cursor_before,
                "cursor_after": result.next_cursor,
                "record_count": len(result.records),
                "accepted_count": accepted,
                "duplicate_count": duplicates,
                "error_count": errors,
                "transport": result.transport,
            }
        except Exception as exc:
            completed = utc_now()
            message = f"{type(exc).__name__}: {exc}"[:512]
            with self.sessions.begin() as session:
                state = session.scalar(
                    select(IntegrationSyncState).where(
                        IntegrationSyncState.organization_id == organization_id,
                        IntegrationSyncState.facility_id == facility_id,
                        IntegrationSyncState.provider == provider_id,
                        IntegrationSyncState.resource == resource,
                    )
                )
                if state:
                    state.status = "failed"
                    state.last_completed_at = completed
                    state.last_error = message
                    state.updated_by = actor
                attempt = session.scalar(select(IntegrationSyncAttempt).where(IntegrationSyncAttempt.run_id == run_id))
                if attempt:
                    attempt.status = "failed"
                    attempt.error_count = 1
                    attempt.error_message = message
                    attempt.completed_at = completed
            raise

    def _validate_scope(self, organization_id: str, facility_id: str) -> None:
        with self.sessions() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Sandbox integration facility is outside the active organization.")

    @staticmethod
    def _adapter(provider: str) -> SandboxAdapter:
        normalized = str(provider or "").strip().casefold()
        adapter = ADAPTERS.get(normalized)
        if adapter is None:
            raise ValueError("Sandbox provider must be metrc, dutchie, biotrack, or quickbooks.")
        return adapter

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    def _state_public(self, state: IntegrationSyncState) -> dict[str, Any]:
        return {
            "resource": state.resource,
            "status": state.status,
            "cursor": state.cursor,
            "last_started_at": self._iso(state.last_started_at),
            "last_completed_at": self._iso(state.last_completed_at),
            "last_success_at": self._iso(state.last_success_at),
            "last_error": state.last_error,
            "records_seen": state.records_seen,
            "records_written": state.records_written,
        }

    def _attempt_public(self, attempt: IntegrationSyncAttempt) -> dict[str, Any]:
        return {
            "run_id": attempt.run_id,
            "resource": attempt.resource,
            "status": attempt.status,
            "record_count": attempt.record_count,
            "accepted_count": attempt.accepted_count,
            "duplicate_count": attempt.duplicate_count,
            "error_count": attempt.error_count,
            "error_message": attempt.error_message,
            "started_at": self._iso(attempt.started_at),
            "completed_at": self._iso(attempt.completed_at),
        }
