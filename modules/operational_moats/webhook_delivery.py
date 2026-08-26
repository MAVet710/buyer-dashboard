"""Signed DoobieLogic webhook delivery with encrypted signing secrets."""

from __future__ import annotations

import base64
from datetime import timezone
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
import requests
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import sessionmaker

from modules.coman.models import utc_now
from .models import WebhookDelivery, WebhookSubscription
from .service import OperationalMoatService


class WebhookDeliveryError(RuntimeError):
    pass


def _cipher(encryption_key: str) -> Fernet:
    clean = str(encryption_key or "").strip()
    if not clean:
        raise WebhookDeliveryError("Webhook signing-secret encryption is not configured.")
    digest = hashlib.sha256(clean.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _hash(value: str) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


class WebhookDeliveryService:
    MAX_ATTEMPTS = 5

    def __init__(self, engine: Engine, encryption_key: str):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        self.cipher = _cipher(encryption_key)

    def create_subscription(
        self,
        *,
        organization_id: str,
        facility_id: str | None,
        name: str,
        target_url: str,
        event_types: list[str],
        actor: str,
    ) -> tuple[WebhookSubscription, str]:
        row, secret = OperationalMoatService(self.engine).create_webhook(
            organization_id=organization_id,
            facility_id=facility_id,
            name=name,
            target_url=target_url,
            event_types=event_types,
            actor=actor,
        )
        self._seal(row.id, organization_id, secret)
        return row, secret

    def _seal(self, subscription_id: str, organization_id: str, secret: str) -> None:
        encrypted = self.cipher.encrypt(secret.encode()).decode()
        hint = f"••••{secret[-4:]}"
        with self.sessions.begin() as session:
            result = session.execute(
                text("UPDATE webhook_subscriptions SET encrypted_secret=:encrypted, secret_hint=:hint WHERE id=:id AND organization_id=:org"),
                {"encrypted": encrypted, "hint": hint, "id": subscription_id, "org": organization_id},
            )
            if result.rowcount != 1:
                raise WebhookDeliveryError("Webhook subscription could not be sealed.")

    def rotate_secret(self, *, organization_id: str, subscription_id: str) -> str:
        secret = f"dlwh_{secrets.token_urlsafe(32)}"
        encrypted = self.cipher.encrypt(secret.encode()).decode()
        hint = f"••••{secret[-4:]}"
        with self.sessions.begin() as session:
            row = session.get(WebhookSubscription, subscription_id)
            if not row or row.organization_id != organization_id:
                raise WebhookDeliveryError("Webhook subscription was not found in this organization.")
            row.secret_hash = _hash(secret)
            session.execute(
                text("UPDATE webhook_subscriptions SET encrypted_secret=:encrypted, secret_hint=:hint WHERE id=:id"),
                {"encrypted": encrypted, "hint": hint, "id": subscription_id},
            )
        return secret

    def secret_hint(self, *, organization_id: str, subscription_id: str) -> str:
        with self.sessions() as session:
            value = session.execute(
                text("SELECT secret_hint FROM webhook_subscriptions WHERE id=:id AND organization_id=:org"),
                {"id": subscription_id, "org": organization_id},
            ).scalar_one_or_none()
        return str(value or "")

    def _secret(self, session, subscription: WebhookSubscription) -> str:
        encrypted = session.execute(
            text("SELECT encrypted_secret FROM webhook_subscriptions WHERE id=:id"),
            {"id": subscription.id},
        ).scalar_one_or_none()
        if not encrypted:
            raise WebhookDeliveryError("Webhook signing secret has not been sealed. Rotate the secret before delivery.")
        try:
            return self.cipher.decrypt(str(encrypted).encode()).decode()
        except InvalidToken as exc:
            raise WebhookDeliveryError("Webhook signing secret cannot be decrypted with the active key.") from exc

    def list_subscriptions(self, organization_id: str, facility_id: str | None = None) -> list[dict[str, Any]]:
        with self.sessions() as session:
            statement = select(WebhookSubscription).where(WebhookSubscription.organization_id == organization_id)
            rows = list(session.scalars(statement.order_by(WebhookSubscription.created_at.desc())))
            hints = {
                row.id: str(session.execute(text("SELECT secret_hint FROM webhook_subscriptions WHERE id=:id"), {"id": row.id}).scalar_one_or_none() or "")
                for row in rows
            }
        result = []
        for row in rows:
            if facility_id and row.facility_id and row.facility_id != facility_id:
                continue
            result.append({
                "id": row.id,
                "name": row.name,
                "facility_id": row.facility_id,
                "target_url": row.target_url,
                "event_types": json.loads(row.event_types_json or "[]"),
                "status": row.status,
                "secret_hint": hints.get(row.id, ""),
                "created_by": row.created_by,
                "created_at": row.created_at,
            })
        return result

    def set_status(self, *, organization_id: str, subscription_id: str, status: str) -> WebhookSubscription:
        target = str(status or "").casefold()
        if target not in {"active", "paused", "disabled"}:
            raise WebhookDeliveryError("Webhook status must be active, paused, or disabled.")
        with self.sessions.begin() as session:
            row = session.get(WebhookSubscription, subscription_id)
            if not row or row.organization_id != organization_id:
                raise WebhookDeliveryError("Webhook subscription was not found in this organization.")
            row.status = target
            session.flush()
            return row

    def send_delivery(self, *, organization_id: str, delivery_id: str, timeout_seconds: int = 15) -> dict[str, Any]:
        with self.sessions.begin() as session:
            delivery = session.get(WebhookDelivery, delivery_id)
            if not delivery or delivery.organization_id != organization_id:
                raise WebhookDeliveryError("Webhook delivery was not found in this organization.")
            subscription = session.get(WebhookSubscription, delivery.subscription_id)
            if not subscription or subscription.organization_id != organization_id:
                raise WebhookDeliveryError("Webhook subscription was not found.")
            if subscription.status != "active":
                raise WebhookDeliveryError("Webhook subscription is not active.")
            if delivery.status not in {"queued", "failed"}:
                raise WebhookDeliveryError(f"Webhook delivery cannot send from status {delivery.status}.")
            if delivery.attempt_count >= self.MAX_ATTEMPTS:
                delivery.status = "dead_letter"
                raise WebhookDeliveryError("Webhook delivery reached the retry limit.")
            secret = self._secret(session, subscription)
            body = str(delivery.payload_json or "{}")
            timestamp = str(int(time.time()))
            signature_payload = f"{timestamp}.{body}".encode()
            signature = hmac.new(secret.encode(), signature_payload, hashlib.sha256).hexdigest()
            delivery.status = "sending"
            delivery.attempt_count += 1
            delivery.last_attempt_at = utc_now()
            session.flush()
            target_url = subscription.target_url
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "DoobieLogic-Webhooks/1.0",
                "X-DoobieLogic-Event": delivery.event_type,
                "X-DoobieLogic-Delivery": delivery.id,
                "X-DoobieLogic-Timestamp": timestamp,
                "X-DoobieLogic-Signature": f"sha256={signature}",
            }

        try:
            response = requests.post(target_url, data=body.encode(), headers=headers, timeout=timeout_seconds)
            success = 200 <= response.status_code < 300
            retryable = response.status_code == 429 or response.status_code >= 500
            error = "" if success else f"Webhook target returned HTTP {response.status_code}."
        except requests.RequestException as exc:
            response = None
            success = False
            retryable = True
            error = f"Webhook request failed: {type(exc).__name__}."

        with self.sessions.begin() as session:
            delivery = session.get(WebhookDelivery, delivery_id)
            if not delivery or delivery.organization_id != organization_id:
                raise WebhookDeliveryError("Webhook delivery disappeared during delivery.")
            if success:
                delivery.status = "succeeded"
                delivery.last_error = ""
                delivery.completed_at = utc_now()
            else:
                delivery.last_error = error[:2000]
                delivery.status = "failed" if retryable and delivery.attempt_count < self.MAX_ATTEMPTS else "dead_letter"
                if delivery.status == "dead_letter":
                    delivery.completed_at = utc_now()
            return {
                "id": delivery.id,
                "status": delivery.status,
                "attempt_count": delivery.attempt_count,
                "http_status": response.status_code if response is not None else None,
                "retryable": bool(not success and delivery.status == "failed"),
                "last_error": delivery.last_error,
            }

    def deliver_batch(self, *, organization_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.sessions() as session:
            ids = list(session.scalars(
                select(WebhookDelivery.id)
                .where(WebhookDelivery.organization_id == organization_id, WebhookDelivery.status.in_(("queued", "failed")))
                .order_by(WebhookDelivery.created_at)
                .limit(max(1, min(int(limit), 100)))
            ))
        results = []
        for delivery_id in ids:
            try:
                results.append(self.send_delivery(organization_id=organization_id, delivery_id=delivery_id))
            except WebhookDeliveryError as exc:
                results.append({"id": delivery_id, "status": "error", "error": str(exc)})
        return results
