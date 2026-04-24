from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ee_preflight.cache import CACHE_VERSION, CacheEntry, DependencyCache


class TestCacheEntry:
    def test_cache_entry_to_dict(self):
        entry = CacheEntry(
            base_image="registry.redhat.io/ansible-automation-platform-26/ee-minimal-rhel9:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            timestamp="2026-04-23T10:15:30Z",
            python_version="3.12",
        )
        result = entry.to_dict()

        assert result == {
            "base_image": "registry.redhat.io/ansible-automation-platform-26/ee-minimal-rhel9:latest",
            "python_package": "gssapi",
            "missing_file": "krb5-config",
            "resolved_rpm": "krb5-devel",
            "platform": "rpm",
            "timestamp": "2026-04-23T10:15:30Z",
            "python_version": "3.12",
        }

    def test_cache_entry_from_dict(self):
        data = {
            "base_image": "quay.io/ansible/ee-minimal:latest",
            "python_package": "lxml",
            "missing_file": "libxml2.h",
            "resolved_rpm": "libxml2-devel",
            "platform": "rpm",
            "timestamp": "2026-04-23T10:15:30Z",
            "python_version": "3.11",
        }
        entry = CacheEntry.from_dict(data)

        assert entry.base_image == "quay.io/ansible/ee-minimal:latest"
        assert entry.python_package == "lxml"
        assert entry.missing_file == "libxml2.h"
        assert entry.resolved_rpm == "libxml2-devel"
        assert entry.platform == "rpm"
        assert entry.timestamp == "2026-04-23T10:15:30Z"
        assert entry.python_version == "3.11"

    def test_cache_entry_is_expired_false(self):
        # Recent timestamp (1 day ago)
        now = datetime.now(UTC)
        recent = now - timedelta(days=1)
        entry = CacheEntry(
            base_image="test:latest",
            python_package="pkg",
            missing_file="file.h",
            resolved_rpm="rpm",
            platform="rpm",
            timestamp=recent.isoformat(),
            python_version="3.11",
        )

        assert entry.is_expired(ttl_days=30) is False

    def test_cache_entry_is_expired_true(self):
        # Old timestamp (40 days ago)
        now = datetime.now(UTC)
        old = now - timedelta(days=40)
        entry = CacheEntry(
            base_image="test:latest",
            python_package="pkg",
            missing_file="file.h",
            resolved_rpm="rpm",
            platform="rpm",
            timestamp=old.isoformat(),
            python_version="3.11",
        )

        assert entry.is_expired(ttl_days=30) is True

    def test_cache_entry_is_expired_custom_ttl(self):
        # 5 days old, TTL = 3 days
        now = datetime.now(UTC)
        old = now - timedelta(days=5)
        entry = CacheEntry(
            base_image="test:latest",
            python_package="pkg",
            missing_file="file.h",
            resolved_rpm="rpm",
            platform="rpm",
            timestamp=old.isoformat(),
            python_version="3.11",
        )

        assert entry.is_expired(ttl_days=3) is True
        assert entry.is_expired(ttl_days=10) is False

    def test_cache_entry_is_expired_invalid_timestamp(self):
        entry = CacheEntry(
            base_image="test:latest",
            python_package="pkg",
            missing_file="file.h",
            resolved_rpm="rpm",
            platform="rpm",
            timestamp="invalid-timestamp",
            python_version="3.11",
        )

        # Invalid timestamps should be considered expired
        assert entry.is_expired(ttl_days=30) is True


class TestDependencyCache:
    def test_cache_get_miss(self, tmp_path: Path):
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result is None

    def test_cache_set_and_get(self, tmp_path: Path):
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result == "krb5-devel"

    def test_cache_set_none_rpm(self, tmp_path: Path):
        """Test caching failed lookups (None resolved_rpm)."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache.set(
            base_image="test:latest",
            python_package="unknown",
            missing_file="missing.h",
            resolved_rpm=None,
            platform="rpm",
            python_version="3.11",
        )

        result = cache.get(
            base_image="test:latest",
            python_package="unknown",
            missing_file="missing.h",
            platform="rpm",
        )

        assert result is None

    def test_cache_persistence(self, tmp_path: Path):
        """Test that cache is written to disk and can be loaded."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache1 = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache1.set(
            base_image="test:latest",
            python_package="lxml",
            missing_file="libxml2.h",
            resolved_rpm="libxml2-devel",
            platform="rpm",
            python_version="3.11",
        )

        # Create new cache instance and verify it loads from disk
        cache2 = DependencyCache(cache_path=cache_file, ttl_days=30)
        result = cache2.get(
            base_image="test:latest",
            python_package="lxml",
            missing_file="libxml2.h",
            platform="rpm",
        )

        assert result == "libxml2-devel"

    def test_cache_file_structure(self, tmp_path: Path):
        """Test that cache file has correct JSON structure."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        data = json.loads(cache_file.read_text())

        assert data["cache_version"] == CACHE_VERSION
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["base_image"] == "test:latest"
        assert data["entries"][0]["python_package"] == "gssapi"
        assert data["entries"][0]["missing_file"] == "krb5-config"
        assert data["entries"][0]["resolved_rpm"] == "krb5-devel"
        assert data["entries"][0]["platform"] == "rpm"
        assert data["entries"][0]["python_version"] == "3.11"
        assert "timestamp" in data["entries"][0]

    def test_cache_update_existing_entry(self, tmp_path: Path):
        """Test that setting the same key updates the entry."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        # Set initial value
        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        # Update with new value
        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-libs",
            platform="rpm",
            python_version="3.12",
        )

        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result == "krb5-libs"

        # Verify only one entry exists
        data = json.loads(cache_file.read_text())
        assert len(data["entries"]) == 1

    def test_cache_multiple_entries(self, tmp_path: Path):
        """Test cache with multiple entries."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        cache.set(
            base_image="test:latest",
            python_package="lxml",
            missing_file="libxml2.h",
            resolved_rpm="libxml2-devel",
            platform="rpm",
            python_version="3.11",
        )

        cache.set(
            base_image="ubuntu:latest",
            python_package="lxml",
            missing_file="libxml2.h",
            resolved_rpm="libxml2-dev",
            platform="dpkg",
            python_version="3.10",
        )

        # Verify all entries are distinct and retrievable
        assert (
            cache.get("test:latest", "gssapi", "krb5-config", "rpm") == "krb5-devel"
        )
        assert (
            cache.get("test:latest", "lxml", "libxml2.h", "rpm") == "libxml2-devel"
        )
        assert (
            cache.get("ubuntu:latest", "lxml", "libxml2.h", "dpkg") == "libxml2-dev"
        )

        # Verify no cross-contamination
        assert cache.get("test:latest", "lxml", "libxml2.h", "dpkg") is None

    def test_cache_clear(self, tmp_path: Path):
        """Test clearing the cache."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)

        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        assert cache_file.exists()

        cache.clear()

        assert not cache_file.exists()
        assert (
            cache.get("test:latest", "gssapi", "krb5-config", "rpm") is None
        )

    def test_cache_ignores_expired_entries(self, tmp_path: Path):
        """Test that expired entries are not loaded."""
        cache_file = tmp_path / ".ee-preflight-cache.json"

        # Create cache with old timestamp
        old_timestamp = (datetime.now(UTC) - timedelta(days=40)).isoformat()
        data = {
            "cache_version": CACHE_VERSION,
            "entries": [
                {
                    "base_image": "test:latest",
                    "python_package": "gssapi",
                    "missing_file": "krb5-config",
                    "resolved_rpm": "krb5-devel",
                    "platform": "rpm",
                    "timestamp": old_timestamp,
                    "python_version": "3.11",
                }
            ],
        }
        cache_file.write_text(json.dumps(data))

        # Load cache and verify expired entry is ignored
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)
        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result is None

    def test_cache_version_mismatch(self, tmp_path: Path):
        """Test that cache with wrong version is ignored."""
        cache_file = tmp_path / ".ee-preflight-cache.json"

        # Write cache with wrong version
        data = {
            "cache_version": "999",
            "entries": [
                {
                    "base_image": "test:latest",
                    "python_package": "gssapi",
                    "missing_file": "krb5-config",
                    "resolved_rpm": "krb5-devel",
                    "platform": "rpm",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "python_version": "3.11",
                }
            ],
        }
        cache_file.write_text(json.dumps(data))

        # Load cache and verify it's empty
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)
        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result is None

    def test_cache_corrupted_file(self, tmp_path: Path):
        """Test that corrupted cache file is handled gracefully."""
        cache_file = tmp_path / ".ee-preflight-cache.json"
        cache_file.write_text("{ invalid json")

        # Should not crash, just start fresh
        cache = DependencyCache(cache_path=cache_file, ttl_days=30)
        result = cache.get(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            platform="rpm",
        )

        assert result is None

    def test_cache_default_path(self, tmp_path: Path, monkeypatch):
        """Test that cache uses default path when none specified."""
        monkeypatch.chdir(tmp_path)

        cache = DependencyCache()
        cache.set(
            base_image="test:latest",
            python_package="gssapi",
            missing_file="krb5-config",
            resolved_rpm="krb5-devel",
            platform="rpm",
            python_version="3.11",
        )

        assert (tmp_path / ".ee-preflight-cache.json").exists()
