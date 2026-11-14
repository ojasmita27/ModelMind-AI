"""Local filesystem storage implementation for datasets."""
import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import PROJECT_ROOT, get_settings


class StoragePathError(ValueError):
    """Raised when a storage key attempts to escape the configured storage root."""


class LocalObjectStorage:
    """Local filesystem storage implementing the ObjectStorage protocol."""

    def __init__(self, base_path: Path | None = None) -> None:
        if base_path is None:
            settings = get_settings()
            base_path = getattr(settings, "PROJECT_ROOT", PROJECT_ROOT) / "data" / "uploads"
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path guard
    # ------------------------------------------------------------------

    def _safe_path(self, key: str) -> Path:
        """Resolve *key* relative to the storage root and verify containment.

        Raises ``StoragePathError`` if the resolved path escapes the root,
        or if *key* is an absolute path.  This prevents path-traversal attacks
        regardless of whether the key contains ``../``, URL-encoded sequences,
        or OS-specific separators.
        """
        if not key or not key.strip():
            raise StoragePathError("Storage key must not be empty.")

        # Reject absolute paths outright — they are never valid storage keys.
        # PurePosixPath / PureWindowsPath cover cross-platform absolute detection.
        from pathlib import PurePosixPath, PureWindowsPath
        if PurePosixPath(key).is_absolute() or PureWindowsPath(key).is_absolute():
            raise StoragePathError(f"Storage key must not be an absolute path: {key!r}")

        # Build the candidate path and resolve all '..' and symlinks.
        candidate = (self.base_path / key).resolve()

        # Containment check: the resolved path must start with the resolved root,
        # AND must not be the root itself (a key should never point to the root dir).
        import os
        common = os.path.commonpath([str(self.base_path), str(candidate)])
        if common != str(self.base_path) or candidate == self.base_path:
            raise StoragePathError(
                f"Storage key escapes the storage root. "
                f"Root: {self.base_path!r}, Key: {key!r}"
            )

        return candidate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, key: str, data: BinaryIO) -> str:
        """Store data and return a storage URI (local://...)."""
        target_path = self._safe_path(key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with target_path.open("wb") as f:
            shutil.copyfileobj(data, f)

        return f"local://{key}"

    def open(self, key: str) -> BinaryIO:
        """Open a file for reading."""
        target_path = self._safe_path(key)
        return target_path.open("rb")

    def exists(self, key: str) -> bool:
        """Check if a file exists."""
        target_path = self._safe_path(key)
        return target_path.exists()

    def delete(self, key: str) -> None:
        """Delete a file."""
        target_path = self._safe_path(key)
        if target_path.exists():
            target_path.unlink()

    def compute_sha256(self, key: str) -> str:
        """Compute SHA-256 checksum of a stored file."""
        target_path = self._safe_path(key)
        sha256_hash = hashlib.sha256()
        with target_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def get_file_size(self, key: str) -> int:
        """Get file size in bytes."""
        target_path = self._safe_path(key)
        return target_path.stat().st_size

    def list_keys(self, prefix: str) -> list[str]:
        """List storage keys under *prefix* (e.g. ``experiments/{id}/``).

        The prefix is resolved through the same containment guard, so a
        traversal attempt raises ``StoragePathError`` rather than listing
        files outside the storage root.
        """
        base = self._safe_path(prefix.rstrip("/") + "/__list__")
        root = base.parent
        if not root.exists():
            return []
        return [
            str(p.relative_to(self.base_path)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file()
        ]

    def delete_prefix(self, prefix: str) -> dict[str, int]:
        """Delete every object under *prefix*. Returns {"deleted": n, "failed": n}.

        Missing keys are ignored. Individual delete failures are counted,
        never raised, so callers can report partial cleanup honestly.
        """
        deleted = failed = 0
        for key in self.list_keys(prefix):
            try:
                self.delete(key)
                deleted += 1
            except Exception:
                failed += 1
        # Remove now-empty directories bottom-up (best effort).
        try:
            root = self._safe_path(prefix.rstrip("/") + "/__cleanup__").parent
            for directory in sorted((d for d in root.rglob("*") if d.is_dir()), key=lambda d: -len(d.parts)):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        except Exception:
            pass
        return {"deleted": deleted, "failed": failed}
