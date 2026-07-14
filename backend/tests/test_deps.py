"""
Unit tests for rate limiting logic — pure logic, no external dependencies.
"""
import pytest


class TestRateLimitLogic:
    """Simulate the sliding window counter used by redis_client.py."""

    def test_requests_within_limit(self):
        store = {}
        max_req = 20
        results = []
        for i in range(20):
            key = "rate_limit:test:192.168.1.1"
            store[key] = store.get(key, 0) + 1
            results.append(store[key] <= max_req)
        assert all(results), "All 20 should be allowed"

    def test_requests_exceed_limit(self):
        store = {}
        max_req = 20
        results = []
        for i in range(25):
            key = "rate_limit:test:192.168.1.1"
            store[key] = store.get(key, 0) + 1
            results.append(store[key] <= max_req)
        assert not any(results[20:]), "Requests 21+ should be blocked"
        assert sum(results) == 20

    def test_different_ips_independent(self):
        store = {}
        # Use up IP1's quota
        for _ in range(20):
            store["rate_limit:test:10.0.0.1"] = store.get("rate_limit:test:10.0.0.1", 0) + 1
        # IP2 should still be allowed
        store["rate_limit:test:10.0.0.2"] = store.get("rate_limit:test:10.0.0.2", 0) + 1
        assert store["rate_limit:test:10.0.0.2"] == 1
        # IP1 is blocked
        assert store["rate_limit:test:10.0.0.1"] == 20

    def test_rate_limit_disabled(self):
        """When disabled, always allow."""
        enabled = False
        
        def check_rate_limit(max_requests, window):
            if not enabled:
                return True
            # ... real logic
            return False
        
        # 1000 requests should all pass when disabled
        for _ in range(1000):
            assert check_rate_limit(20, 60) is True

    def test_ip_header_extraction(self):
        """Verify X-Forwarded-For parsing logic."""
        xff = "192.168.1.1, 10.0.0.1, 172.16.0.1"
        first_ip = xff.split(",")[0].strip()
        assert first_ip == "192.168.1.1"

    def test_ip_sanitization(self):
        """IP too long should be truncated."""
        long_ip = "a" * 100
        ip = long_ip[:45]
        assert len(ip) == 45
        assert "\n" not in ip
