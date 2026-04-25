"""Dependency resolution cache for Layer 3 container wheel tests.

Caches RPM package lookups (dnf provides / apt-file) across runs so that
repeated ee-preflight invocations skip expensive container queries for
packages that have already been resolved.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

CACHE_VERSION = "1"
DEFAULT_TTL_DAYS = 30
DEFAULT_CACHE_FILE = ".ee-preflight-cache.json"


@dataclass
class CacheEntry:
    """A single cached RPM resolution result keyed by image + package + file."""

    base_image: str
    python_package: str
    missing_file: str
    resolved_rpm: str | None
    platform: str
    timestamp: str
    python_version: str

    def is_expired(self, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        """Check if cache entry is older than TTL."""
        try:
            entry_time = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # Invalid timestamp format, consider expired
            return True
        now = datetime.now(UTC)
        return (now - entry_time) > timedelta(days=ttl_days)

    def to_dict(self) -> dict[str, str | None]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "base_image": self.base_image,
            "python_package": self.python_package,
            "missing_file": self.missing_file,
            "resolved_rpm": self.resolved_rpm,
            "platform": self.platform,
            "timestamp": self.timestamp,
            "python_version": self.python_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Deserialize from a dictionary (as stored in the cache JSON)."""
        return cls(
            base_image=data["base_image"],
            python_package=data["python_package"],
            missing_file=data["missing_file"],
            resolved_rpm=data.get("resolved_rpm"),
            platform=data["platform"],
            timestamp=data["timestamp"],
            python_version=data["python_version"],
        )


class DependencyCache:
    """On-disk JSON cache for RPM/DEB resolution results from Layer 3."""

    def __init__(self, cache_path: Path | None = None, ttl_days: int = DEFAULT_TTL_DAYS) -> None:
        self.cache_path = cache_path or Path.cwd() / DEFAULT_CACHE_FILE
        self.ttl_days = ttl_days
        self._entries: list[CacheEntry] = []
        self._loaded = False

    def _load(self) -> None:
        """Load cache from disk if it exists."""
        if self._loaded:
            return

        self._loaded = True
        if not self.cache_path.exists():
            return

        try:
            data = json.loads(self.cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        if data.get("cache_version") != CACHE_VERSION:
            return

        for entry_data in data.get("entries", []):
            try:
                entry = CacheEntry.from_dict(entry_data)
            except (KeyError, TypeError):
                continue
            if not entry.is_expired(self.ttl_days):
                self._entries.append(entry)

    def get(
        self,
        base_image: str,
        python_package: str,
        missing_file: str,
        platform: str,
        python_version: str = "",
    ) -> str | None:
        """
        Retrieve cached RPM for the given key.
        Returns None if not found or expired.
        """
        self._load()

        for entry in self._entries:
            if (
                entry.base_image == base_image
                and entry.python_package == python_package
                and entry.missing_file == missing_file
                and entry.platform == platform
                and entry.python_version == python_version
            ):
                return entry.resolved_rpm

        return None

    def set(
        self,
        base_image: str,
        python_package: str,
        missing_file: str,
        resolved_rpm: str | None,
        platform: str,
        python_version: str,
    ) -> None:
        """Add or update a cache entry."""
        self._load()

        # Remove existing entry for this key if present
        self._entries = [
            e
            for e in self._entries
            if not (
                e.base_image == base_image
                and e.python_package == python_package
                and e.missing_file == missing_file
                and e.platform == platform
                and e.python_version == python_version
            )
        ]

        # Add new entry
        entry = CacheEntry(
            base_image=base_image,
            python_package=python_package,
            missing_file=missing_file,
            resolved_rpm=resolved_rpm,
            platform=platform,
            timestamp=datetime.now(UTC).isoformat(),
            python_version=python_version,
        )
        self._entries.append(entry)

        # Save to disk
        self._save()

    def _save(self) -> None:
        """Write cache to disk."""
        data = {
            "cache_version": CACHE_VERSION,
            "entries": [e.to_dict() for e in self._entries],
        }

        # Ensure parent directory exists
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically using temp file + rename
        temp_path = self.cache_path.with_suffix(f".{os.getpid()}.tmp")
        temp_path.write_text(json.dumps(data, indent=2))
        temp_path.replace(self.cache_path)

    def clear(self) -> None:
        """Clear all cache entries and delete cache file."""
        self._entries = []
        self._loaded = True
        if self.cache_path.exists():
            self.cache_path.unlink()
