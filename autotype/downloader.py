"""Resilient model and binary downloader for AutoType."""
from __future__ import annotations

from collections.abc import Callable
import hashlib
import logging
import os
from pathlib import Path
import shutil
import tarfile
import threading
import urllib.error
import urllib.request

from autotype.manifest import ManifestItem
from autotype.paths import get_staging_dir

log = logging.getLogger("autotype.downloader")

# 64 KiB chunk size for streaming downloads
CHUNK_SIZE = 64 * 1024
# 10 MB minimum disk safety margin
DISK_SAFETY_MARGIN_BYTES = 10 * 1024 * 1024


class DownloaderError(Exception):
    """Base exception for downloader failures."""


class InsufficientDiskSpaceError(DownloaderError):
    """Raised when free disk space is less than required."""


class ChecksumMismatchError(DownloaderError):
    """Raised when SHA-256 verification fails."""


class DownloadCancelledError(DownloaderError):
    """Raised when a download is cancelled by user via cancel_event."""


class UnverifiedModelError(DownloaderError):
    """Raised when attempting to download or execute an unverified model or binary."""


def compute_file_sha256(path: Path) -> str:
    """Calculate SHA-256 hex digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def _check_disk_space(target_dir: Path, required_bytes: int) -> None:
    """Verify target filesystem has sufficient space for download + safety margin."""
    target_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target_dir)
    needed = required_bytes + DISK_SAFETY_MARGIN_BYTES
    if usage.free < needed:
        raise InsufficientDiskSpaceError(
            f"Insufficient disk space on {target_dir}: {usage.free} bytes free, "
            f"{needed} bytes required ({required_bytes} file + {DISK_SAFETY_MARGIN_BYTES} margin)"
        )


def _safe_extract_member(tar_path: Path, member_name: str, dest_path: Path) -> None:
    """Safely extract a specific member from a tarball avoiding zip-slip traversal."""
    with tarfile.open(tar_path, "r:*") as tar:
        target_member = None
        for member in tar.getmembers():
            if member.name == member_name:
                target_member = member
                break

        if target_member is None:
            raise DownloaderError(
                f"Archive member '{member_name}' not found in '{tar_path.name}'"
            )

        clean_name = os.path.normpath(target_member.name)
        if clean_name.startswith(("/", "\\")) or ".." in clean_name.split(os.sep):
            raise DownloaderError(
                f"Security error: Archive member '{member_name}' attempts directory traversal"
            )

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_file = tar.extractfile(target_member)
        if extracted_file is None:
            raise DownloaderError(
                f"Archive member '{member_name}' is not a regular extractable file"
            )

        with open(dest_path, "wb") as out_f:
            shutil.copyfileobj(extracted_file, out_f)


def download_stream(
    url: str,
    dest_path: Path,
    expected_size: int,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float = 30.0,
) -> None:
    """Stream download a URL to dest_path with HTTP Range resume support."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    offset = dest_path.stat().st_size if dest_path.is_file() else 0
    if offset > 0 and expected_size > 0 and offset >= expected_size:
        # File is already fully or over-downloaded in staging
        offset = 0
        dest_path.unlink(missing_ok=True)

    headers = {
        "User-Agent": "AutoType-Downloader/1.0 (Linux x86_64)",
    }
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"

    req = urllib.request.Request(url, headers=headers)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        if err.code == 416:  # Range Not Satisfiable
            # Offset was invalid, restart from beginning
            offset = 0
            dest_path.unlink(missing_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": headers["User-Agent"]})
            resp = urllib.request.urlopen(req, timeout=timeout)
        else:
            raise DownloaderError(f"HTTP error {err.code} while fetching {url}: {err.reason}") from err
    except Exception as exc:
        raise DownloaderError(f"Network error while connecting to {url}: {exc}") from exc

    with resp:
        status = getattr(resp, "status", 200)
        is_partial = (status == 206)

        if is_partial and offset > 0:
            file_mode = "ab"
            downloaded = offset
        else:
            file_mode = "wb"
            downloaded = 0
            offset = 0

        total = expected_size
        if total <= 0:
            # Fall back to content-length header if expected_size was unspecified
            cl = resp.headers.get("Content-Length")
            total = (int(cl) + offset) if cl else 0

        if progress_callback:
            progress_callback(downloaded, total)

        with open(dest_path, file_mode) as out_f:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    out_f.flush()
                    raise DownloadCancelledError("Download cancelled by user")

                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break

                out_f.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    progress_callback(downloaded, total)


def download_item(
    item: ManifestItem,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Download, verify, and atomically place a manifest item.

    Returns the destination path of the installed file.
    """
    if not item.installable or not item.verified:
        reason = item.unverified_reason or "item is unverified or marked non-installable"
        raise UnverifiedModelError(f"Cannot download '{item.id}': {reason}")

    staging_dir = get_staging_dir()

    # 1. Pre-download disk space check
    required_space = item.size_bytes + (item.binary_size_bytes or 0)
    _check_disk_space(staging_dir, required_space)

    is_archive = bool(item.archive_member)
    staging_file_name = f"{item.id}.archive.tmp" if is_archive else f"{item.filename}.tmp"
    staging_path = staging_dir / staging_file_name

    # 2. Chunked streaming download with resume
    log.info("Starting download of '%s' from %s", item.id, item.url)
    download_stream(
        url=item.url,
        dest_path=staging_path,
        expected_size=item.size_bytes,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )

    # 3. Checksum verification of the downloaded file
    actual_sha256 = compute_file_sha256(staging_path)
    if actual_sha256.lower() != item.sha256.lower():
        staging_path.unlink(missing_ok=True)
        raise ChecksumMismatchError(
            f"Checksum mismatch for '{item.id}': expected {item.sha256}, got {actual_sha256}"
        )

    # 4. Handle archive extraction if item is packaged in an archive
    if is_archive:
        extracted_staging_path = staging_dir / f"{item.filename}.extracted.tmp"
        try:
            assert item.archive_member is not None
            _safe_extract_member(staging_path, item.archive_member, extracted_staging_path)

            if item.binary_sha256:
                bin_sha = compute_file_sha256(extracted_staging_path)
                if bin_sha.lower() != item.binary_sha256.lower():
                    extracted_staging_path.unlink(missing_ok=True)
                    raise ChecksumMismatchError(
                        f"Extracted binary checksum mismatch for '{item.id}': "
                        f"expected {item.binary_sha256}, got {bin_sha}"
                    )

            file_to_place = extracted_staging_path
        finally:
            staging_path.unlink(missing_ok=True)
    else:
        file_to_place = staging_path

    # 5. Atomic placement into target directory
    target_path = item.target_path
    item.target_dir.mkdir(parents=True, exist_ok=True)
    os.replace(file_to_place, target_path)

    # 6. Apply executable permissions for binary items
    if item.type == "binary":
        os.chmod(target_path, 0o755)

    log.info("Successfully installed '%s' to %s", item.id, target_path)
    return target_path


def verify_binary_safety(binary_path: Path, expected_sha256: str | None = None) -> bool:
    """Verify that a binary file exists, is executable, and matches expected SHA-256."""
    if not binary_path.is_file():
        return False
    if not os.access(binary_path, os.X_OK):
        return False

    if not expected_sha256:
        from autotype.manifest import load_manifest

        for item in load_manifest():
            if item.type == "binary" and item.filename == binary_path.name:
                expected_sha256 = item.binary_sha256 or item.sha256
                break

    if not expected_sha256:
        log.warning("Binary safety verification failed: no checksum known for %s", binary_path)
        return False

    actual_sha256 = compute_file_sha256(binary_path)
    return actual_sha256.lower() == expected_sha256.lower()


def ensure_binary_verified(binary_path: Path, expected_sha256: str | None = None) -> Path:
    """Return binary_path if safely verified; otherwise raise UnverifiedModelError."""
    if not verify_binary_safety(binary_path, expected_sha256):
        raise UnverifiedModelError(
            f"Binary at '{binary_path}' failed security verification "
            f"(checksum mismatch, missing file, or not executable)."
        )
    return binary_path


def remove_item(item: ManifestItem) -> bool:
    """Remove an installed model or binary from disk."""
    target = item.target_path
    if target.is_file():
        target.unlink()
        log.info("Removed installed item '%s' from %s", item.id, target)
        return True
    return False


def remove_item_by_id(item_id: str) -> bool:
    """Remove an installed model or binary by ID."""
    from autotype.manifest import get_item

    item = get_item(item_id)
    if not item:
        raise DownloaderError(f"Unknown item ID: '{item_id}'")
    return remove_item(item)
