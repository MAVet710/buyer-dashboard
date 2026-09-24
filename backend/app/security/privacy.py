"""No bodies, tokens, cookies, raw usernames, raw IPs or query strings."""
from hashlib import sha256
import hmac
from ipaddress import ip_address, ip_network


def pseudonym(secret: str, namespace: str, value: str) -> str:
    if not value:
        return ""
    return hmac.new(secret.encode(), (namespace + ":" + value[:1024]).encode(), sha256).hexdigest()


def source_identity(request, settings) -> str:
    peer = request.client.host if request.client else ""
    try:
        address = ip_address(peer)
    except ValueError:
        return ""
    networks = []
    for entry in settings.security_trusted_proxy_cidrs.split(","):
        if entry.strip():
            try:
                networks.append(ip_network(entry.strip(), strict=False))
            except ValueError:
                return ""
    # Existing Caddy overwrites this header. Only explicitly trusted ingress
    # peers may supply it; X-Forwarded-For is never used here.
    if any(address in network for network in networks):
        raw = request.headers.get("x-advisory-client-ip", "")
        try:
            forwarded = ip_address(raw)
            if "%" in raw or forwarded.is_loopback or forwarded.is_unspecified:
                return ""
            return str(forwarded)
        except ValueError:
            return ""
    # A local proxy is not a client: do not group all customers as one attacker.
    return "" if address.is_loopback or address.is_unspecified else str(address)
