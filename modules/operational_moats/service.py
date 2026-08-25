"""Services for SOP controls, LabelGuard, cultivation harvests, machine telemetry and partner/API access."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import secrets
from typing import Any, Iterable

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import FacilityMachine, TradePartner, utc_now
from modules.coman.repository import ComanRepository
from modules.commercial_finance.models import CustomerPriceRule

from .models import (
    CultivationHarvest,
    LabelReview,
    LabelTemplate,
    MachineTelemetryEvent,
    PartnerPortalAccess,
    SOPAcknowledgement,
    SOPDeviation,
    SOPDocument,
    ServiceAccount,
    WebhookDelivery,
    WebhookSubscription,
)


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def evaluate_label_rules(label: dict[str, Any], rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate reviewed/configured rules deterministically without hard-coding changing law."""
    findings: list[dict[str, Any]] = []
    normalized = {str(key): value for key, value in (label or {}).items()}
    raw_text = str(normalized.get("raw_text") or "").casefold()
    for index, rule in enumerate(rules or (), start=1):
        kind = str(rule.get("kind") or "required_field").strip().casefold()
        field = str(rule.get("field") or "").strip()
        key = str(rule.get("key") or f"rule-{index}")
        severity = str(rule.get("severity") or "fail").strip().casefold()
        if severity not in {"warning", "fail"}:
            severity = "fail"
        passed = True
        observed: Any = None
        expected: Any = rule.get("value")
        if kind == "required_field":
            observed = normalized.get(field)
            passed = observed is not None and str(observed).strip() != ""
            expected = "present"
        elif kind == "contains":
            needle = str(rule.get("value") or "").casefold()
            observed = str(normalized.get(field) or raw_text)
            passed = bool(needle) and needle in observed.casefold()
        elif kind == "equals":
            observed = normalized.get(field)
            passed = str(observed or "").strip().casefold() == str(expected or "").strip().casefold()
        elif kind == "numeric_min":
            observed = normalized.get(field)
            try:
                passed = float(observed) >= float(expected)
            except (TypeError, ValueError):
                passed = False
        elif kind == "numeric_max":
            observed = normalized.get(field)
            try:
                passed = float(observed) <= float(expected)
            except (TypeError, ValueError):
                passed = False
        else:
            findings.append({"key": key, "status": "warning", "message": f"Unsupported configured rule type: {kind}", "field": field, "source": str(rule.get("source") or "")})
            continue
        findings.append({
            "key": key,
            "status": "pass" if passed else severity,
            "message": str(rule.get("message") or (f"{field or key} passed." if passed else f"{field or key} needs review.")),
            "field": field,
            "observed": observed,
            "expected": expected,
            "source": str(rule.get("source") or ""),
        })
    return findings


class OperationalMoatService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def create_sop(self, *, organization_id: str, facility_id: str | None, code: str, title: str, body_text: str, actor: str, source_reference: str = "", required_roles: list[str] | None = None, control_rules: list[dict[str, Any]] | None = None, activate: bool = False) -> SOPDocument:
        clean_code = str(code or "").strip().upper()
        if not clean_code or not str(title or "").strip():
            raise ValueError("SOP code and title are required.")
        with self._sessions.begin() as session:
            latest = int(session.scalar(select(func.coalesce(func.max(SOPDocument.version), 0)).where(SOPDocument.organization_id == organization_id, SOPDocument.code == clean_code)) or 0)
            if activate:
                for row in session.scalars(select(SOPDocument).where(SOPDocument.organization_id == organization_id, SOPDocument.code == clean_code, SOPDocument.status == "active")):
                    row.status = "retired"
            row = SOPDocument(organization_id=organization_id, facility_id=facility_id, code=clean_code, title=str(title).strip(), version=latest + 1, status="active" if activate else "draft", body_text=str(body_text or ""), source_reference=str(source_reference or ""), effective_date=utc_now().date() if activate else None, required_roles_json=_json(required_roles or []), control_rules_json=_json(control_rules or []), created_by=actor, approved_by=actor if activate else "", approved_at=utc_now() if activate else None)
            session.add(row); session.flush(); return row

    def activate_sop(self, organization_id: str, sop_id: str, actor: str) -> SOPDocument:
        with self._sessions.begin() as session:
            row = session.get(SOPDocument, sop_id)
            if not row or row.organization_id != organization_id:
                raise ValueError("SOP was not found.")
            for old in session.scalars(select(SOPDocument).where(SOPDocument.organization_id == organization_id, SOPDocument.code == row.code, SOPDocument.status == "active", SOPDocument.id != row.id)):
                old.status = "retired"
            row.status = "active"; row.effective_date = utc_now().date(); row.approved_by = actor; row.approved_at = utc_now(); return row

    def list_sops(self, organization_id: str, facility_id: str | None = None) -> list[SOPDocument]:
        with self._sessions() as session:
            stmt = select(SOPDocument).where(SOPDocument.organization_id == organization_id)
            if facility_id:
                stmt = stmt.where((SOPDocument.facility_id.is_(None)) | (SOPDocument.facility_id == facility_id))
            return list(session.scalars(stmt.order_by(SOPDocument.code, SOPDocument.version.desc())))

    def acknowledge_sop(self, organization_id: str, facility_id: str, sop_id: str, user_id: str) -> SOPAcknowledgement:
        with self._sessions.begin() as session:
            sop = session.get(SOPDocument, sop_id)
            if not sop or sop.organization_id != organization_id or sop.status != "active":
                raise ValueError("An active SOP is required.")
            existing = session.scalar(select(SOPAcknowledgement).where(SOPAcknowledgement.sop_document_id == sop_id, SOPAcknowledgement.user_id == user_id))
            if existing:
                return existing
            row = SOPAcknowledgement(organization_id=organization_id, facility_id=facility_id, sop_document_id=sop_id, user_id=user_id)
            session.add(row); session.flush(); return row

    def record_deviation(self, *, organization_id: str, facility_id: str, sop_id: str, entity_type: str, entity_id: str, rule_key: str, severity: str, evidence: dict[str, Any], explanation: str, actor: str = "system") -> SOPDeviation:
        severity = str(severity or "medium").casefold()
        if severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("Unsupported deviation severity.")
        with self._sessions.begin() as session:
            sop = session.get(SOPDocument, sop_id)
            if not sop or sop.organization_id != organization_id:
                raise ValueError("SOP was not found.")
            existing = session.scalar(select(SOPDeviation).where(SOPDeviation.organization_id == organization_id, SOPDeviation.facility_id == facility_id, SOPDeviation.sop_document_id == sop_id, SOPDeviation.entity_type == entity_type, SOPDeviation.entity_id == entity_id, SOPDeviation.rule_key == rule_key, SOPDeviation.status.in_(("open", "investigating"))))
            if existing:
                existing.evidence_json = _json(evidence); existing.explanation = explanation; existing.severity = severity; return existing
            row = SOPDeviation(organization_id=organization_id, facility_id=facility_id, sop_document_id=sop_id, entity_type=entity_type, entity_id=entity_id, rule_key=rule_key, severity=severity, evidence_json=_json(evidence), explanation=explanation, detected_by=actor)
            session.add(row); session.flush(); return row

    def list_deviations(self, organization_id: str, facility_id: str, open_only: bool = True) -> list[SOPDeviation]:
        with self._sessions() as session:
            stmt = select(SOPDeviation).where(SOPDeviation.organization_id == organization_id, SOPDeviation.facility_id == facility_id)
            if open_only:
                stmt = stmt.where(SOPDeviation.status.in_(("open", "investigating")))
            return list(session.scalars(stmt.order_by(SOPDeviation.detected_at.desc())))

    def create_label_template(self, *, organization_id: str, facility_id: str | None, name: str, jurisdiction: str, license_scope: str, layout: dict[str, Any], rules: list[dict[str, Any]], actor: str, activate: bool = False) -> LabelTemplate:
        if not str(name or "").strip():
            raise ValueError("Template name is required.")
        with self._sessions.begin() as session:
            clean_name = str(name).strip()
            latest = int(session.scalar(select(func.coalesce(func.max(LabelTemplate.version), 0)).where(LabelTemplate.organization_id == organization_id, LabelTemplate.name == clean_name)) or 0)
            if activate:
                for old in session.scalars(select(LabelTemplate).where(LabelTemplate.organization_id == organization_id, LabelTemplate.name == clean_name, LabelTemplate.status == "active")):
                    old.status = "retired"
            row = LabelTemplate(organization_id=organization_id, facility_id=facility_id, name=clean_name, version=latest + 1, jurisdiction=str(jurisdiction or "").strip(), license_scope=str(license_scope or "").strip(), status="active" if activate else "draft", layout_json=_json(layout or {}), rules_json=_json(rules or []), created_by=actor, approved_by=actor if activate else "", approved_at=utc_now() if activate else None)
            session.add(row); session.flush(); return row

    def list_label_templates(self, organization_id: str, facility_id: str | None = None) -> list[LabelTemplate]:
        with self._sessions() as session:
            stmt = select(LabelTemplate).where(LabelTemplate.organization_id == organization_id)
            if facility_id:
                stmt = stmt.where((LabelTemplate.facility_id.is_(None)) | (LabelTemplate.facility_id == facility_id))
            return list(session.scalars(stmt.order_by(LabelTemplate.name, LabelTemplate.version.desc())))

    def review_label(self, *, organization_id: str, facility_id: str, label: dict[str, Any], actor: str, template_id: str | None = None, product_id: str | None = None, package_id: str = "", ad_hoc_rules: list[dict[str, Any]] | None = None, rule_set_reference: str = "") -> tuple[LabelReview, list[dict[str, Any]]]:
        rules = list(ad_hoc_rules or [])
        with self._sessions.begin() as session:
            if template_id:
                template = session.get(LabelTemplate, template_id)
                if not template or template.organization_id != organization_id:
                    raise ValueError("Label template was not found.")
                rules.extend(_load(template.rules_json, []))
                if not rule_set_reference:
                    rule_set_reference = f"{template.name} v{template.version}"
            findings = evaluate_label_rules(label, rules)
            failures = sum(item["status"] == "fail" for item in findings); warnings = sum(item["status"] == "warning" for item in findings)
            status = "fail" if failures else ("warning" if warnings else "pass")
            row = LabelReview(organization_id=organization_id, facility_id=facility_id, template_id=template_id, product_id=product_id, package_id=str(package_id or ""), status=status, input_json=_json(label), findings_json=_json(findings), rule_set_reference=str(rule_set_reference or ""), reviewed_by=actor)
            session.add(row); session.flush(); return row, findings

    def list_label_reviews(self, organization_id: str, facility_id: str, limit: int = 100) -> list[LabelReview]:
        with self._sessions() as session:
            return list(session.scalars(select(LabelReview).where(LabelReview.organization_id == organization_id, LabelReview.facility_id == facility_id).order_by(LabelReview.reviewed_at.desc()).limit(max(1, min(limit, 500)))))

    def record_telemetry(self, *, organization_id: str, facility_id: str, machine_id: str, event_type: str, actor: str, metric_key: str = "", numeric_value: float | None = None, unit: str = "", state: str = "", source: str = "manual", external_event_id: str = "", payload: dict[str, Any] | None = None, recorded_at: datetime | None = None) -> MachineTelemetryEvent:
        event_type = str(event_type or "").casefold()
        if event_type not in {"heartbeat", "running", "idle", "downtime", "fault", "measurement", "cycle"}:
            raise ValueError("Unsupported telemetry event type.")
        with self._sessions.begin() as session:
            machine = session.get(FacilityMachine, machine_id)
            if not machine or machine.organization_id != organization_id or machine.facility_id != facility_id:
                raise ValueError("Machine was not found in the active facility.")
            if external_event_id:
                existing = session.scalar(select(MachineTelemetryEvent).where(MachineTelemetryEvent.organization_id == organization_id, MachineTelemetryEvent.machine_id == machine_id, MachineTelemetryEvent.external_event_id == external_event_id))
                if existing:
                    return existing
            row = MachineTelemetryEvent(organization_id=organization_id, facility_id=facility_id, machine_id=machine_id, event_type=event_type, metric_key=str(metric_key or ""), numeric_value=numeric_value, unit=str(unit or ""), state=str(state or ""), source=str(source or actor or "manual"), external_event_id=str(external_event_id or ""), payload_json=_json(payload or {}), recorded_at=recorded_at or utc_now())
            session.add(row); session.flush(); return row

    def telemetry_summary(self, organization_id: str, facility_id: str, hours: int = 24) -> dict[str, Any]:
        cutoff = utc_now() - timedelta(hours=max(1, min(int(hours), 24 * 30)))
        with self._sessions() as session:
            rows = list(session.scalars(select(MachineTelemetryEvent).where(MachineTelemetryEvent.organization_id == organization_id, MachineTelemetryEvent.facility_id == facility_id, MachineTelemetryEvent.recorded_at >= cutoff).order_by(MachineTelemetryEvent.recorded_at.desc())))
            machines = {row.id: row for row in session.scalars(select(FacilityMachine).where(FacilityMachine.organization_id == organization_id, FacilityMachine.facility_id == facility_id))}
        grouped: dict[str, list[MachineTelemetryEvent]] = defaultdict(list)
        for row in rows:
            grouped[row.machine_id].append(row)
        result = []
        for machine_id, machine in machines.items():
            events = grouped.get(machine_id, []); latest = events[0] if events else None
            result.append({"machine_id": machine_id, "name": machine.display_name, "asset_code": machine.asset_code, "last_state": (latest.state or latest.event_type) if latest else "no telemetry", "last_seen": latest.recorded_at if latest else None, "faults": sum(event.event_type == "fault" for event in events), "downtime_events": sum(event.event_type == "downtime" for event in events), "cycles": sum(event.event_type == "cycle" for event in events), "measurements": sum(event.event_type == "measurement" for event in events)})
        return {"hours": hours, "machines": result, "event_count": len(rows)}

    def create_harvest(self, *, organization_id: str, facility_id: str, harvest_code: str, strain: str, actor: str, room: str = "", plant_count: int = 0, wet_weight_g: float = 0, dry_weight_g: float = 0, waste_weight_g: float = 0, labor_hours: float = 0, status: str = "planned", notes: str = "", harvested_at: datetime | None = None) -> CultivationHarvest:
        status = str(status or "planned").casefold()
        if status not in {"planned", "active", "drying", "completed", "cancelled"}:
            raise ValueError("Unsupported harvest status.")
        if any(float(value) < 0 for value in (plant_count, wet_weight_g, dry_weight_g, waste_weight_g, labor_hours)):
            raise ValueError("Harvest quantities cannot be negative.")
        row = CultivationHarvest(organization_id=organization_id, facility_id=facility_id, harvest_code=str(harvest_code or "").strip().upper(), strain=str(strain or "").strip(), room=str(room or "").strip(), plant_count=int(plant_count), wet_weight_g=float(wet_weight_g), dry_weight_g=float(dry_weight_g), waste_weight_g=float(waste_weight_g), labor_hours=float(labor_hours), status=status, harvested_at=harvested_at, completed_at=utc_now() if status == "completed" else None, notes=str(notes or ""), created_by=actor)
        if not row.harvest_code or not row.strain:
            raise ValueError("Harvest code and strain are required.")
        with self._sessions.begin() as session:
            session.add(row); session.flush(); return row

    def list_harvests(self, organization_id: str, facility_id: str) -> list[CultivationHarvest]:
        with self._sessions() as session:
            return list(session.scalars(select(CultivationHarvest).where(CultivationHarvest.organization_id == organization_id, CultivationHarvest.facility_id == facility_id).order_by(CultivationHarvest.created_at.desc())))

    def harvest_summary(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        rows = self.list_harvests(organization_id, facility_id); completed = [row for row in rows if row.status == "completed"]
        wet = sum(float(row.wet_weight_g) for row in completed); dry = sum(float(row.dry_weight_g) for row in completed)
        by_strain: dict[str, dict[str, float]] = defaultdict(lambda: {"harvests": 0, "wet_g": 0.0, "dry_g": 0.0, "plants": 0.0})
        for row in completed:
            bucket = by_strain[row.strain]; bucket["harvests"] += 1; bucket["wet_g"] += float(row.wet_weight_g); bucket["dry_g"] += float(row.dry_weight_g); bucket["plants"] += int(row.plant_count)
        strain_rows = []
        for strain, values in by_strain.items():
            plants = values["plants"]
            strain_rows.append({"strain": strain, **values, "dry_g_per_plant": values["dry_g"] / plants if plants else 0.0, "dry_to_wet_pct": (values["dry_g"] / values["wet_g"] * 100.0) if values["wet_g"] else 0.0})
        return {"total_harvests": len(rows), "active_harvests": sum(row.status in {"active", "drying"} for row in rows), "completed_harvests": len(completed), "completed_wet_g": wet, "completed_dry_g": dry, "dry_to_wet_pct": (dry / wet * 100.0) if wet else 0.0, "by_strain": sorted(strain_rows, key=lambda item: item["dry_g"], reverse=True)}

    def issue_partner_portal_access(self, *, organization_id: str, facility_id: str, partner_id: str, actor: str, label: str = "Retailer Portal", expires_days: int = 90) -> tuple[PartnerPortalAccess, str]:
        with self._sessions.begin() as session:
            partner = session.get(TradePartner, partner_id)
            if not partner or partner.organization_id != organization_id or partner.partner_type not in {"customer", "both"}:
                raise ValueError("A customer trade partner is required.")
            token = _new_token("dlp")
            row = PartnerPortalAccess(organization_id=organization_id, facility_id=facility_id, partner_id=partner_id, token_hash=_hash_token(token), label=str(label or "Retailer Portal"), created_by=actor, expires_at=utc_now() + timedelta(days=max(1, min(int(expires_days), 365))))
            session.add(row); session.flush(); return row, token

    def resolve_partner_portal(self, token: str) -> PartnerPortalAccess:
        digest = _hash_token(token)
        with self._sessions.begin() as session:
            row = session.scalar(select(PartnerPortalAccess).where(PartnerPortalAccess.token_hash == digest))
            if not row or row.revoked_at is not None or (row.expires_at and row.expires_at < utc_now()):
                raise ValueError("Partner portal access is invalid or expired.")
            row.last_used_at = utc_now(); session.flush(); return row

    def partner_catalog(self, access: PartnerPortalAccess) -> dict[str, Any]:
        repo = ComanRepository(self.engine); products = repo.list_products(access.organization_id); lots = repo.list_inventory_lots(access.organization_id, access.facility_id)
        balances: dict[str, float] = {}
        for lot in lots:
            if lot.status in {"available", "released"}:
                balances[lot.product_id] = balances.get(lot.product_id, 0.0) + max(0.0, repo.inventory_balance(access.organization_id, lot.id))
        with self._sessions() as session:
            partner = session.get(TradePartner, access.partner_id)
            rules = {row.product_id: row for row in session.scalars(select(CustomerPriceRule).where(CustomerPriceRule.organization_id == access.organization_id, CustomerPriceRule.partner_id == access.partner_id, CustomerPriceRule.active.is_(True)))}
        catalog = []
        for product in products:
            available = balances.get(product.id, 0.0)
            if available <= 0:
                continue
            base = float(product.retail_price or 0.0); rule = rules.get(product.id)
            if rule and float(rule.price_usd or 0) > 0:
                price = float(rule.price_usd)
            elif rule:
                price = max(0.0, base * (1 - float(rule.discount_pct or 0) / 100.0))
            else:
                price = base
            catalog.append({"product_id": product.id, "sku": product.sku, "name": product.name, "unit": product.base_unit, "available": available, "price_usd": price})
        return {"partner": {"id": partner.id, "name": partner.name, "payment_terms": partner.payment_terms} if partner else {}, "facility_id": access.facility_id, "catalog": catalog}

    def issue_service_account(self, *, organization_id: str, facility_id: str | None, name: str, scopes: list[str], actor: str) -> tuple[ServiceAccount, str]:
        token = _new_token("dla")
        with self._sessions.begin() as session:
            row = ServiceAccount(organization_id=organization_id, facility_id=facility_id, name=str(name or "").strip(), token_hash=_hash_token(token), scopes_json=_json(sorted(set(str(scope) for scope in scopes if str(scope).strip()))), created_by=actor)
            if not row.name:
                raise ValueError("Service-account name is required.")
            session.add(row); session.flush(); return row, token

    def create_webhook(self, *, organization_id: str, facility_id: str | None, name: str, target_url: str, event_types: list[str], actor: str) -> tuple[WebhookSubscription, str]:
        target_url = str(target_url or "").strip()
        if not target_url.startswith("https://"):
            raise ValueError("Webhook targets must use HTTPS.")
        secret = _new_token("dlwh")
        with self._sessions.begin() as session:
            row = WebhookSubscription(organization_id=organization_id, facility_id=facility_id, name=str(name or "").strip(), target_url=target_url, event_types_json=_json(sorted(set(event_types))), secret_hash=_hash_token(secret), created_by=actor)
            if not row.name or not event_types:
                raise ValueError("Webhook name and at least one event type are required.")
            session.add(row); session.flush(); return row, secret

    def queue_webhook_event(self, *, organization_id: str, facility_id: str | None, event_type: str, event_id: str, payload: dict[str, Any]) -> int:
        with self._sessions.begin() as session:
            subscriptions = list(session.scalars(select(WebhookSubscription).where(WebhookSubscription.organization_id == organization_id, WebhookSubscription.status == "active")))
            count = 0
            for subscription in subscriptions:
                if subscription.facility_id and subscription.facility_id != facility_id:
                    continue
                if event_type not in _load(subscription.event_types_json, []):
                    continue
                session.add(WebhookDelivery(organization_id=organization_id, facility_id=facility_id, subscription_id=subscription.id, event_type=event_type, event_id=event_id, payload_json=_json(payload))); count += 1
            return count
