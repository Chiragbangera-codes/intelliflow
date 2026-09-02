"""
Server-Side Request Forgery (SSRF) Protection Utilities.

Provides strict URL validation and safe network dispatching to prevent outbound
requests to internal networks, private IP ranges, loopback addresses, cloud metadata
services, or container hostnames.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Forbidden hostnames and aliases
FORBIDDEN_HOSTNAMES: set[str] = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "host.docker.internal",
    "gateway.docker.internal",
    "metadata.google.internal",
    "metadata",
    "kubernetes",
    "postgres",
    "redis",
    "backend",
    "worker",
    "ollama",
    "frontend",
    "intelliflow_postgres",
    "intelliflow_redis",
    "intelliflow_backend",
    "intelliflow_worker",
    "intelliflow_ollama",
    "intelliflow_frontend",
}

# Forbidden CIDR ranges
FORBIDDEN_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),  # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # Documentation
    ipaddress.ip_network("192.168.0.0/16"),  # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # Documentation
    ipaddress.ip_network("203.0.113.0/24"),  # Documentation
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 ranges
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),  # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("fc00::/7"),  # Unique Local
    ipaddress.ip_network("fe80::/10"),  # Link-Local
    ipaddress.ip_network("ff00::/8"),  # Multicast
]

ALLOWED_SCHEMES: set[str] = {"http", "https"}
ALLOWED_PORTS: set[int] = {80, 443, 8080, 8443}


class SSRFValidationError(ValueError):
    """Raised when a URL violates SSRF safety constraints."""


def is_ip_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to any forbidden / private network."""
    # Check built-in properties
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # Check against explicit forbidden CIDR networks
    for net in FORBIDDEN_IP_NETWORKS:
        if ip in net:
            return True

    # If IPv6 is IPv4-mapped, check the mapped IPv4
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_ip_forbidden(ip.ipv4_mapped)

    return False


def validate_webhook_url(url: str, allow_test_local: bool = False) -> str:
    """
    Validate a webhook URL against SSRF rules.

    Args:
        url: The candidate webhook URL string.
        allow_test_local: Flag for unit tests ONLY. Must be False in production.

    Returns:
        The validated clean URL string.

    Raises:
        SSRFValidationError: If the URL fails any security check.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("Webhook URL must be a non-empty string.")

    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFValidationError(f"Invalid URL structure: {exc}") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFValidationError(
            f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("Webhook URL must include a valid hostname.")

    hostname_lower = hostname.lower()

    # Disallow user credentials in URL (e.g. http://user:pass@example.com)
    if parsed.username or parsed.password:
        raise SSRFValidationError("Embedding user credentials in webhook URLs is forbidden.")

    # Check port
    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        raise SSRFValidationError(
            f"Port {port} is not allowed. Allowed ports: {sorted(ALLOWED_PORTS)}"
        )

    # Check forbidden hostnames
    if not allow_test_local and hostname_lower in FORBIDDEN_HOSTNAMES:
        raise SSRFValidationError(f"Target host '{hostname}' is an internal/forbidden destination.")

    # Resolve IP addresses for DNS-level validation
    try:
        # Check if the hostname is already a direct IP address literal
        # Handle decimal / hex / standard representations
        try:
            ip_obj = ipaddress.ip_address(hostname_lower.strip("[]"))
            if not allow_test_local and is_ip_forbidden(ip_obj):
                raise SSRFValidationError(
                    f"Target IP address '{ip_obj}' is in a private or restricted range."
                )
            return url
        except ValueError:
            # Not a direct IP literal, proceed to resolve via DNS
            pass

        # Resolve hostname to all associated IPs
        addr_infos = socket.getaddrinfo(
            hostname,
            port or (443 if parsed.scheme == "https" else 80),
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )

        resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for _family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            try:
                resolved_ips.append(ipaddress.ip_address(ip_str))
            except ValueError:
                continue

        if not resolved_ips:
            raise SSRFValidationError(f"Could not resolve hostname '{hostname}' to an IP address.")

        if not allow_test_local:
            for ip in resolved_ips:
                if is_ip_forbidden(ip):
                    raise SSRFValidationError(
                        f"Hostname '{hostname}' resolved to restricted IP address '{ip}'."
                    )

    except socket.gaierror as exc:
        raise SSRFValidationError(f"DNS resolution failed for host '{hostname}': {exc}") from exc
    except SSRFValidationError:
        raise
    except Exception as exc:
        raise SSRFValidationError(f"SSRF validation failed: {exc}") from exc

    return url


async def safe_http_post(
    url: str,
    headers: dict[str, str],
    content: bytes,
    timeout_seconds: float = 10.0,
    max_redirects: int = 3,
    allow_test_local: bool = False,
) -> tuple[int, str, dict[str, str]]:
    """
    Execute an asynchronous HTTP POST request with strict SSRF validation across redirects.

    Returns:
        tuple of (status_code, response_body_text, response_headers_dict)
    """
    current_url = validate_webhook_url(url, allow_test_local=allow_test_local)
    redirect_count = 0

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_seconds),
        verify=True,
    ) as client:
        while True:
            response = await client.post(
                current_url,
                headers=headers,
                content=content,
            )

            # Check for redirects
            if response.is_redirect and redirect_count < max_redirects:
                redirect_url = response.headers.get("Location")
                if not redirect_url:
                    break
                # Validate the redirect destination against SSRF
                current_url = validate_webhook_url(redirect_url, allow_test_local=allow_test_local)
                redirect_count += 1
                continue

            resp_headers = {k: v for k, v in response.headers.items()}
            return response.status_code, response.text, resp_headers
