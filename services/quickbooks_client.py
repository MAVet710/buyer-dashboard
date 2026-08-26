"""QuickBooks Online OAuth, company-health, and bounded accounting helpers.

This module never persists OAuth material. Callers supply encrypted credentials,
refresh them through Intuit, and persist any rotated refresh token back through
the integration credential service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests


TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SANDBOX_API = "https://sandbox-quickbooks.api.intuit.com"
PRODUCTION_API = "https://quickbooks.api.intuit.com"
ALLOWED_ACCOUNTING_ENTITIES = {"customer", "vendor", "invoice", "payment", "purchaseorder", "bill"}


class QuickBooksError(RuntimeError):
    def __init__(self, message: str, *, http_status: int | None = None, retryable: bool = False, payload: Any = None):
        super().__init__(message)
        self.http_status = http_status
        self.retryable = retryable
        self.payload = payload


@dataclass(frozen=True)
class QuickBooksToken:
    access_token: str
    refresh_token: str
    expires_in: int


def _api_base(environment: str, override: str = "") -> str:
    if override:
        clean = str(override).strip().rstrip("/")
        parsed = urlparse(clean)
        if parsed.scheme != "https" or not parsed.netloc:
            raise QuickBooksError("QuickBooks API base URL must use HTTPS.")
        return clean
    return PRODUCTION_API if str(environment).casefold() == "production" else SANDBOX_API


def refresh_quickbooks_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    token_url: str = TOKEN_URL,
    timeout: int = 20,
) -> QuickBooksToken:
    if not all(str(value or "").strip() for value in (client_id, client_secret, refresh_token)):
        raise QuickBooksError("QuickBooks client ID, client secret, and refresh token are required.")
    parsed = urlparse(str(token_url))
    if parsed.scheme != "https" or not parsed.netloc:
        raise QuickBooksError("QuickBooks OAuth token URL must use HTTPS.")
    try:
        response = requests.post(
            token_url,
            auth=(str(client_id).strip(), str(client_secret)),
            data={"grant_type": "refresh_token", "refresh_token": str(refresh_token)},
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise QuickBooksError(f"QuickBooks token refresh failed: {exc}", retryable=True) from exc
    if response.status_code in {400, 401, 403}:
        raise QuickBooksError("QuickBooks rejected the saved OAuth credentials or refresh token.", http_status=response.status_code)
    if response.status_code == 429:
        raise QuickBooksError("QuickBooks rate limited the token refresh.", http_status=429, retryable=True)
    if not response.ok:
        raise QuickBooksError(f"QuickBooks token refresh failed with HTTP {response.status_code}.", http_status=response.status_code, retryable=response.status_code >= 500)
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksError("QuickBooks returned a non-JSON OAuth response.", http_status=response.status_code) from exc
    access = str(payload.get("access_token") or "").strip()
    rotated_refresh = str(payload.get("refresh_token") or refresh_token).strip()
    if not access:
        raise QuickBooksError("QuickBooks token refresh did not return an access token.")
    return QuickBooksToken(access_token=access, refresh_token=rotated_refresh, expires_in=int(payload.get("expires_in") or 0))


def quickbooks_api_request(
    *,
    access_token: str,
    realm_id: str,
    environment: str,
    entity: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
    api_base_url: str = "",
    timeout: int = 30,
) -> dict[str, Any]:
    """Call only the accounting entities DoobieLogic explicitly supports."""
    realm = str(realm_id or "").strip()
    entity_name = str(entity or "").strip().casefold()
    if not realm:
        raise QuickBooksError("QuickBooks company realm ID is required.")
    if entity_name not in ALLOWED_ACCOUNTING_ENTITIES:
        raise QuickBooksError(f"QuickBooks entity '{entity_name}' is not enabled for native sync.")
    url = f"{_api_base(environment, api_base_url)}/v3/company/{realm}/{entity_name}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json", "Content-Type": "application/json"}
    try:
        response = requests.request(method.upper(), url, json=payload or {}, headers=headers, params={"minorversion": "75"}, timeout=timeout)
    except requests.RequestException as exc:
        raise QuickBooksError(f"QuickBooks {entity_name} request failed: {exc}", retryable=True) from exc
    parsed: Any = None
    if response.content:
        try:
            parsed = response.json()
        except ValueError:
            parsed = {"message": response.text[:1000]}
    if response.status_code == 429:
        raise QuickBooksError("QuickBooks rate limited the accounting request.", http_status=429, retryable=True, payload=parsed)
    if response.status_code in {401, 403}:
        raise QuickBooksError("QuickBooks rejected the OAuth token for this company.", http_status=response.status_code, payload=parsed)
    if response.status_code >= 500:
        raise QuickBooksError(f"QuickBooks returned HTTP {response.status_code}.", http_status=response.status_code, retryable=True, payload=parsed)
    if not response.ok:
        raise QuickBooksError(f"QuickBooks rejected the {entity_name} request with HTTP {response.status_code}.", http_status=response.status_code, payload=parsed)
    if not isinstance(parsed, dict):
        raise QuickBooksError("QuickBooks returned an unexpected accounting response.", http_status=response.status_code)
    return parsed


def fetch_quickbooks_company_info(
    *,
    access_token: str,
    realm_id: str,
    environment: str,
    api_base_url: str = "",
    timeout: int = 20,
) -> dict[str, Any]:
    realm = str(realm_id or "").strip()
    if not realm:
        raise QuickBooksError("QuickBooks company realm ID is required.")
    url = f"{_api_base(environment, api_base_url)}/v3/company/{realm}/companyinfo/{realm}"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, params={"minorversion": "75"}, timeout=timeout)
    except requests.RequestException as exc:
        raise QuickBooksError(f"QuickBooks company check failed: {exc}", retryable=True) from exc
    if response.status_code in {401, 403}:
        raise QuickBooksError("QuickBooks access token is not authorized for the configured company.", http_status=response.status_code)
    if response.status_code == 429:
        raise QuickBooksError("QuickBooks rate limited the company check.", http_status=429, retryable=True)
    if not response.ok:
        raise QuickBooksError(f"QuickBooks company check failed with HTTP {response.status_code}.", http_status=response.status_code, retryable=response.status_code >= 500)
    try:
        payload = response.json()
    except ValueError as exc:
        raise QuickBooksError("QuickBooks returned a non-JSON company response.", http_status=response.status_code) from exc
    info = payload.get("QueryResponse") if isinstance(payload, dict) else None
    if not isinstance(info, dict) or not info.get("CompanyInfo"):
        raise QuickBooksError("QuickBooks did not return company information for the configured realm.")
    company = info["CompanyInfo"][0] if isinstance(info["CompanyInfo"], list) else info["CompanyInfo"]
    return {"company_name": company.get("CompanyName") or company.get("LegalName") or "", "realm_id": realm}


def test_quickbooks_connection(
    *, client_id: str, client_secret: str, refresh_token: str, realm_id: str, environment: str, api_base_url: str = "", token_url: str = TOKEN_URL
) -> dict[str, Any]:
    try:
        token = refresh_quickbooks_token(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token, token_url=token_url)
        company = fetch_quickbooks_company_info(access_token=token.access_token, realm_id=realm_id, environment=environment, api_base_url=api_base_url)
        return {"ok": True, "message": f"QuickBooks connected to {company['company_name'] or 'the configured company'}.", "company": company, "refresh_token": token.refresh_token}
    except QuickBooksError as exc:
        return {"ok": False, "message": str(exc), "refresh_token": refresh_token}
