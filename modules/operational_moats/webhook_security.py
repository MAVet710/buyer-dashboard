"""Network-boundary validation for outbound webhook destinations.

Webhook destinations are administrator-controlled, but the delivery worker still
runs with the API's network identity. Treat every configured target as untrusted
and refuse URLs that could turn webhook delivery into an SSRF primitive.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeWebhookTarget(ValueError):
    pass


def _public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.is_global)


def validate_webhook_target(target_url: str, *, resolve_dns: bool = True) -> str:
    """Return a normalized public HTTPS webhook URL or raise.

    DNS is resolved immediately before delivery so normal private, loopback,
    link-local, multicast, reserved and unspecified destinations fail closed.
    Redirects are disabled by the delivery worker separately so a public host
    cannot bounce a validated request into a private network.
    """

    clean = str(target_url or "").strip()
    try:
        parsed = urlsplit(clean)
    except ValueError as exc:
        raise UnsafeWebhookTarget("Webhook target is not a valid URL.") from exc

    if parsed.scheme.casefold() != "https":
        raise UnsafeWebhookTarget("Webhook targets must use HTTPS.")
    if not parsed.hostname:
        raise UnsafeWebhookTarget("Webhook target must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeWebhookTarget("Webhook targets cannot contain URL credentials.")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeWebhookTarget("Webhook target contains an invalid port.") from exc

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeWebhookTarget("Webhook target must use a public Internet host.")

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeWebhookTarget("Webhook target must use a public Internet address.")

    if resolve_dns and literal is None:
        try:
            answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise UnsafeWebhookTarget("Webhook target hostname could not be resolved.") from exc
        addresses = {str(answer[4][0]) for answer in answers if answer and answer[4]}
        if not addresses:
            raise UnsafeWebhookTarget("Webhook target hostname did not resolve to an address.")
        if any(not _public_address(address) for address in addresses):
            raise UnsafeWebhookTarget("Webhook target resolves to a non-public address.")

    return clean
