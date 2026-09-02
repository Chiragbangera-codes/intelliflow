"""
Comprehensive unit and security tests for SSRF (Server-Side Request Forgery) protection.
"""

import ipaddress

import pytest

from app.utils.ssrf import SSRFValidationError, is_ip_forbidden, validate_webhook_url


class TestSSRFProtection:
    """Test SSRF validation logic and IP filtering."""

    @pytest.mark.parametrize(
        "forbidden_url",
        [
            "http://localhost:8000/webhook",
            "http://127.0.0.1:8000/api",
            "http://127.0.0.2/test",
            "http://0.0.0.0:8000",
            "http://[::1]:8000",
            "http://10.0.0.1/webhook",
            "http://10.255.255.254/hook",
            "http://172.16.0.1/hook",
            "http://172.31.255.255/hook",
            "http://192.168.1.1/hook",
            "http://169.254.169.254/latest/meta-data/",  # AWS metadata
            "http://169.254.169.254/computeMetadata/v1/",  # GCP metadata
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://postgres:5432",
            "http://redis:6379",
            "http://backend:8000",
            "http://worker:8000",
            "http://intelliflow_backend:8000",
            "ftp://example.com/file",
            "file:///etc/passwd",
            "gopher://127.0.0.1:6379",
            "http://user:pass@example.com/hook",
            "http://example.com:22/ssh",
            "http://example.com:3306/db",
        ],
    )
    def test_forbidden_destinations_rejected(self, forbidden_url: str) -> None:
        with pytest.raises(SSRFValidationError):
            validate_webhook_url(forbidden_url, allow_test_local=False)

    @pytest.mark.parametrize(
        "valid_ip",
        [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34",  # example.com
            "140.82.121.3",  # github.com
        ],
    )
    def test_public_ips_allowed(self, valid_ip: str) -> None:
        ip_obj = ipaddress.ip_address(valid_ip)
        assert is_ip_forbidden(ip_obj) is False

    @pytest.mark.parametrize(
        "private_ip",
        [
            "127.0.0.1",
            "10.0.0.5",
            "172.16.1.1",
            "192.168.0.1",
            "169.254.169.254",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fc00::1",
            "255.255.255.255",
        ],
    )
    def test_private_ips_blocked(self, private_ip: str) -> None:
        ip_obj = ipaddress.ip_address(private_ip)
        assert is_ip_forbidden(ip_obj) is True

    def test_valid_public_webhook_url(self) -> None:
        url = "https://httpbin.org/post"
        validated = validate_webhook_url(url, allow_test_local=False)
        assert validated == url

    def test_allow_test_local_flag(self) -> None:
        # With allow_test_local=True, localhost should pass on standard allowed ports for mocked unit testing
        url = "http://127.0.0.1:8080/webhook"
        validated = validate_webhook_url(url, allow_test_local=True)
        assert validated == url
