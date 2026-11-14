"""Regression tests for the path-traversal fix in LocalObjectStorage and
the filename-sanitization helper in services/datasets.

Every test here must remain passing after the fix and must have failed (or
exposed the vulnerability) with the original code.

Safety: no test touches the development database or the development storage
root.  All storage operations use isolated temporary directories created with
``tempfile.mkdtemp`` (avoids the pytest ``tmp_path`` permission issue on this
Windows machine).
"""
import io
import shutil
import tempfile
from pathlib import Path

import pytest

from app.storage.local import LocalObjectStorage, StoragePathError
from app.services.datasets import _sanitize_filename

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmpdir() -> Path:
    """Create a fresh temp directory that this process owns."""
    return Path(tempfile.mkdtemp(prefix="mm_sec_test_"))


def make_storage(root: Path) -> LocalObjectStorage:
    """Return a LocalObjectStorage rooted at *root*."""
    storage_root = root / "storage_root"
    storage_root.mkdir(parents=True, exist_ok=True)
    return LocalObjectStorage(base_path=storage_root)


CSV_DATA = b"a,b\n1,2\n3,4\n"


# ===========================================================================
# Unit tests: LocalObjectStorage._safe_path
# ===========================================================================


class TestSafePath:
    """_safe_path must reject any key that would escape the storage root."""

    # --- traversal variants ------------------------------------------------

    def test_simple_traversal_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("../outside.txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_nested_traversal_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("datasets/abc/../../../outside.txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_deep_nested_traversal_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("a/b/c/../../../../outside.txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_traversal_targeting_root(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("../../../../../../../etc/passwd")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # --- absolute paths ----------------------------------------------------

    def test_absolute_posix_path_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("/etc/passwd")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_absolute_windows_path_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("C:\\Windows\\System32\\evil.txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_windows_unc_path_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("\\\\server\\share\\file.txt")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # --- empty / blank keys ------------------------------------------------

    def test_empty_key_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_whitespace_only_key_rejected(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            with pytest.raises(StoragePathError):
                s._safe_path("   ")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    # --- valid keys (must NOT raise) ---------------------------------------

    def test_simple_key_accepted(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            result = s._safe_path("file.csv")
            assert result.parent == s.base_path
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_nested_key_accepted(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            result = s._safe_path("datasets/abc/v1/data.csv")
            assert str(result).startswith(str(s.base_path))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_key_with_uuid_accepted(self):
        d = _tmpdir()
        try:
            s = make_storage(d)
            result = s._safe_path("datasets/550e8400-e29b-41d4-a716-446655440000/v1/data.csv")
            assert str(result).startswith(str(s.base_path))
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# Integration tests: all public methods guard their keys
# ===========================================================================


TRAVERSAL_KEYS = [
    "../escape.txt",
    "a/../../escape.txt",
    "/absolute/path.txt",
]


@pytest.mark.parametrize("key", TRAVERSAL_KEYS)
def test_put_rejects_traversal(key):
    d = _tmpdir()
    try:
        s = make_storage(d)
        with pytest.raises(StoragePathError):
            s.put(key, io.BytesIO(b"evil"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("key", TRAVERSAL_KEYS)
def test_open_rejects_traversal(key):
    d = _tmpdir()
    try:
        s = make_storage(d)
        with pytest.raises(StoragePathError):
            s.open(key)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("key", TRAVERSAL_KEYS)
def test_delete_rejects_traversal(key):
    d = _tmpdir()
    try:
        s = make_storage(d)
        with pytest.raises(StoragePathError):
            s.delete(key)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("key", TRAVERSAL_KEYS)
def test_compute_sha256_rejects_traversal(key):
    d = _tmpdir()
    try:
        s = make_storage(d)
        with pytest.raises(StoragePathError):
            s.compute_sha256(key)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.mark.parametrize("key", TRAVERSAL_KEYS)
def test_get_file_size_rejects_traversal(key):
    d = _tmpdir()
    try:
        s = make_storage(d)
        with pytest.raises(StoragePathError):
            s.get_file_size(key)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# Integration tests: traversal cannot write outside the root
# ===========================================================================


def test_put_traversal_does_not_write_outside_root():
    d = _tmpdir()
    try:
        root = d / "storage"
        root.mkdir()
        outside_marker = d / "outside.txt"

        s = LocalObjectStorage(base_path=root)
        with pytest.raises(StoragePathError):
            s.put("../outside.txt", io.BytesIO(b"evil"))

        assert not outside_marker.exists(), (
            "Path traversal SUCCEEDED: file was written outside the storage root"
        )
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_put_deep_traversal_does_not_write_outside_root():
    """A key that traverses up through nested sub-dirs but stays inside the
    root must not write outside.  A key that genuinely escapes must be
    blocked by the guard.  This test verifies both properties.
    """
    d = _tmpdir()
    try:
        root = d / "storage"
        (root / "datasets" / "abc" / "v1").mkdir(parents=True)

        s = LocalObjectStorage(base_path=root)

        # --- Scenario A: key that resolves outside the root (genuine escape) ---
        # Four levels up from v1/ takes us above the storage root entirely.
        escape_key = "datasets/abc/v1/../../../../evil.txt"
        with pytest.raises(StoragePathError):
            s.put(escape_key, io.BytesIO(b"evil"))
        # The file must not exist anywhere outside the root
        assert not (d / "evil.txt").exists()

        # --- Scenario B: key that resolves inside the root (not a traversal) ---
        # Three levels up from v1/ lands at storage_root/evil.txt — still inside.
        inside_key = "datasets/abc/v1/../../../evil.txt"
        # This resolves to root/evil.txt, which is valid.  No StoragePathError expected.
        s.put(inside_key, io.BytesIO(b"safe content"))
        assert (root / "evil.txt").exists(), "File should be at root/evil.txt"
        s.delete("evil.txt")  # clean up using the normalised key
    finally:
        shutil.rmtree(d, ignore_errors=True)


# Normal round-trip must still work after the fix.
def test_normal_put_and_open_still_work():
    d = _tmpdir()
    try:
        s = make_storage(d)
        key = "datasets/abc/v1/data.csv"
        s.put(key, io.BytesIO(CSV_DATA))
        with s.open(key) as f:
            assert f.read() == CSV_DATA
        assert s.exists(key)
        assert s.get_file_size(key) == len(CSV_DATA)
        checksum = s.compute_sha256(key)
        assert len(checksum) == 64
        s.delete(key)
        assert not s.exists(key)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# Unit tests: _sanitize_filename
# ===========================================================================


class TestSanitizeFilename:
    """_sanitize_filename must strip directory components and unsafe chars."""

    # --- traversal in filename (the primary attack surface) ----------------

    def test_strips_relative_path_prefix(self):
        assert _sanitize_filename("../../../etc/passwd") == "passwd"

    def test_strips_absolute_path_prefix(self):
        result = _sanitize_filename("/etc/passwd")
        assert "/" not in result
        assert result != ""

    def test_strips_windows_path(self):
        result = _sanitize_filename("C:\\Windows\\System32\\cmd.exe")
        assert "\\" not in result
        assert ":" not in result

    def test_strips_mixed_slashes(self):
        # Path("foo/bar/../baz.csv").name is "baz.csv"
        result = _sanitize_filename("foo/bar/../baz.csv")
        assert result == "baz.csv"

    # --- unsafe character replacement -------------------------------------

    def test_semicolons_replaced(self):
        assert ";" not in _sanitize_filename("evil;rm -rf.csv")

    def test_spaces_replaced(self):
        assert " " not in _sanitize_filename("my file.csv")

    def test_null_bytes_replaced(self):
        assert "\x00" not in _sanitize_filename("evil\x00.csv")

    # --- fallback for empty result ----------------------------------------

    def test_empty_string_falls_back(self):
        assert _sanitize_filename("") == "upload.csv"

    def test_all_unsafe_chars_falls_back(self):
        result = _sanitize_filename("...")
        assert result != ""

    # --- normal filenames must pass through cleanly -----------------------

    def test_normal_csv_unchanged(self):
        assert _sanitize_filename("sales.csv") == "sales.csv"

    def test_name_with_hyphens_and_underscores(self):
        result = _sanitize_filename("my-dataset_v2.csv")
        assert result == "my-dataset_v2.csv"

    def test_long_filename_truncated(self):
        long_name = "a" * 200 + ".csv"
        result = _sanitize_filename(long_name)
        assert len(result) <= 100

    def test_uuid_style_name_accepted(self):
        name = "550e8400-e29b-41d4-a716-446655440000.csv"
        assert _sanitize_filename(name) == name


# ===========================================================================
# API-level test: malicious filename via upload endpoint
# ===========================================================================


def test_upload_with_traversal_filename_is_rejected_or_sanitized(client, alice):
    """Uploading a file whose filename contains '../' must not write outside
    the storage root.  The response must be 201 (sanitized) or 422
    (validation rejected), never 500 and never an escaped file.
    """
    csv = b"a,b\n1,2\n3,4\n"
    from app.core.config import PROJECT_ROOT

    outside_marker = PROJECT_ROOT / "evil_traversal_test.csv"
    try:
        r = client.post(
            "/api/v1/projects",
            json={"name": "Traversal test project"},
            headers=alice,
        )
        assert r.status_code == 201
        project_id = r.json()["id"]

        resp = client.post(
            f"/api/v1/projects/{project_id}/datasets",
            headers=alice,
            data={"name": "Traversal attempt"},
            files={"file": ("../../../evil_traversal_test.csv", io.BytesIO(csv), "text/csv")},
        )

        assert resp.status_code in {201, 422}, (
            f"Unexpected status {resp.status_code}: {resp.text}"
        )
        assert not outside_marker.exists(), (
            "Path traversal SUCCEEDED via the upload API: "
            f"file written to {outside_marker}"
        )
    finally:
        if outside_marker.exists():
            outside_marker.unlink()


def test_upload_with_absolute_filename_is_safe(client, alice):
    """A filename that looks like an absolute path must be sanitized."""
    csv = b"x,y\n1,2\n"
    r = client.post(
        "/api/v1/projects",
        json={"name": "Absolute filename project"},
        headers=alice,
    )
    assert r.status_code == 201
    project_id = r.json()["id"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        headers=alice,
        data={"name": "Absolute attempt"},
        files={"file": ("/etc/passwd", io.BytesIO(csv), "text/csv")},
    )

    # Must not be 500.
    assert resp.status_code in {201, 422}, (
        f"Unexpected status {resp.status_code}: {resp.text}"
    )
