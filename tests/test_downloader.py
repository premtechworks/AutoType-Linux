"""Unit tests for autotype.downloader using a local HTTP server."""
from __future__ import annotations

import hashlib
import http.server
import io
import os
from pathlib import Path
import shutil
import tarfile
import threading
from typing import ClassVar
from unittest.mock import patch

import pytest

from autotype.downloader import (
    ChecksumMismatchError,
    DownloadCancelledError,
    DownloaderError,
    InsufficientDiskSpaceError,
    UnverifiedModelError,
    compute_file_sha256,
    download_item,
    download_stream,
    ensure_binary_verified,
    remove_item,
    verify_binary_safety,
)
from autotype.manifest import ManifestItem


class MockDownloadServer(http.server.HTTPServer):
    """Local HTTP server that provides content and handles Range requests."""

    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.routes: dict[str, bytes] = {}
        self.force_200: bool = False
        self.requests_log: list[tuple[str, dict[str, str]]] = []


class MockHTTPHandler(http.server.BaseHTTPRequestHandler):
    server: MockDownloadServer

    def log_message(self, format, *args):
        # Suppress standard logging to keep test output clean
        pass

    def do_GET(self):
        req_headers = {k: v for k, v in self.headers.items()}
        self.server.requests_log.append((self.path, req_headers))

        data = self.server.routes.get(self.path)
        if data is None:
            self.send_response(404)
            self.end_headers()
            return

        total_len = len(data)
        range_hdr = self.headers.get("Range")

        if range_hdr and not self.server.force_200:
            if not range_hdr.startswith("bytes="):
                self.send_response(400)
                self.end_headers()
                return

            try:
                start_str = range_hdr[6:].rstrip("-")
                start = int(start_str)
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return

            if start >= total_len:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total_len}")
                self.end_headers()
                return

            chunk = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{total_len - 1}/{total_len}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(total_len))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(data)


@pytest.fixture
def http_server():
    server = MockDownloadServer(("127.0.0.1", 0), MockHTTPHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def test_dirs(tmp_path, monkeypatch):
    data_dir = tmp_path / "autotype_data"
    models_dir = data_dir / "models"
    bin_dir = data_dir / "bin"
    staging_dir = data_dir / ".tmp"

    data_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    staging_dir.mkdir(parents=True)

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("autotype.paths.get_xdg_data_dir", lambda: data_dir)
    monkeypatch.setattr("autotype.paths.get_models_dir", lambda: models_dir)
    monkeypatch.setattr("autotype.paths.get_bin_dir", lambda: bin_dir)
    monkeypatch.setattr("autotype.paths.get_staging_dir", lambda: staging_dir)
    monkeypatch.setattr("autotype.downloader.get_staging_dir", lambda: staging_dir)

    return {
        "data": data_dir,
        "models": models_dir,
        "bin": bin_dir,
        "staging": staging_dir,
    }


def test_download_model_success(http_server, test_dirs):
    content = b"GGUF_TEST_MODEL_DATA_STREAMING_12345"
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/model.gguf"
    http_server.routes["/model.gguf"] = content

    item = ManifestItem(
        id="test-model",
        display_name="Test Model",
        type="stt-stream",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="test-model.gguf",
    )

    progress_events = []

    def on_progress(dl, total):
        progress_events.append((dl, total))

    installed_path = download_item(item, progress_callback=on_progress)

    assert installed_path == test_dirs["models"] / "test-model.gguf"
    assert installed_path.is_file()
    assert installed_path.read_bytes() == content
    assert len(progress_events) >= 1
    assert progress_events[-1] == (len(content), len(content))


def test_download_binary_executable_bit(http_server, test_dirs):
    content = b"\x7fELF_DUMMY_BINARY_PAYLOAD_EXEC"
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/sample-cli"
    http_server.routes["/sample-cli"] = content

    item = ManifestItem(
        id="sample-cli",
        display_name="Sample CLI",
        type="binary",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="sample-cli",
    )

    installed_path = download_item(item)

    assert installed_path == test_dirs["bin"] / "sample-cli"
    assert installed_path.is_file()
    assert os.access(installed_path, os.X_OK)
    assert verify_binary_safety(installed_path, expected_sha256=sha) is True


def test_download_resume_with_range_206(http_server, test_dirs):
    content = b"PART_1_INITIAL_BYTES" + b"_PART_2_RESUMED_BYTES"
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/resumable.gguf"
    http_server.routes["/resumable.gguf"] = content

    item = ManifestItem(
        id="resumable-model",
        display_name="Resumable Model",
        type="stt-stream",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="resumable.gguf",
    )

    # Pre-populate partial file in staging directory
    staging_file = test_dirs["staging"] / "resumable.gguf.tmp"
    staging_file.write_bytes(b"PART_1_INITIAL_BYTES")

    progress_events = []
    installed_path = download_item(item, progress_callback=lambda dl, t: progress_events.append((dl, t)))

    assert installed_path.is_file()
    assert installed_path.read_bytes() == content
    assert progress_events[0][0] == len(b"PART_1_INITIAL_BYTES")
    assert progress_events[-1][0] == len(content)


def test_download_resume_server_ignores_range_200(http_server, test_dirs):
    content = b"FULL_CONTENT_OVERWRITING_STAGING"
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/ignore-range.bin"
    http_server.routes["/ignore-range.bin"] = content
    http_server.force_200 = True  # Server ignores Range and returns 200 OK

    item = ManifestItem(
        id="ignore-range",
        display_name="Ignore Range Model",
        type="stt-batch",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="ignore-range.bin",
    )

    # Staging has corrupted/partial content
    staging_file = test_dirs["staging"] / "ignore-range.bin.tmp"
    staging_file.write_bytes(b"OLD_GARBAGE_BYTES")

    installed_path = download_item(item)
    assert installed_path.is_file()
    assert installed_path.read_bytes() == content


def test_download_checksum_mismatch(http_server, test_dirs):
    content = b"ACTUAL_DATA_ON_SERVER"
    bad_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/mismatch.bin"
    http_server.routes["/mismatch.bin"] = content

    item = ManifestItem(
        id="bad-checksum",
        display_name="Bad Checksum",
        type="stt-stream",
        size_bytes=len(content),
        url=url,
        sha256=bad_sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="mismatch.bin",
    )

    with pytest.raises(ChecksumMismatchError):
        download_item(item)

    target_path = test_dirs["models"] / "mismatch.bin"
    assert not target_path.exists()
    # Staging temp file should have been cleaned up on mismatch
    assert not (test_dirs["staging"] / "mismatch.bin.tmp").exists()


def test_download_cancellation(http_server, test_dirs):
    # Large data so streaming can be cancelled
    content = b"X" * (512 * 1024)
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/cancel.bin"
    http_server.routes["/cancel.bin"] = content

    item = ManifestItem(
        id="cancel-test",
        display_name="Cancel Test",
        type="stt-stream",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="cancel.bin",
    )

    cancel_event = threading.Event()

    def progress_canceller(dl, total):
        if dl > 65536:
            cancel_event.set()

    with pytest.raises(DownloadCancelledError):
        download_item(item, progress_callback=progress_canceller, cancel_event=cancel_event)

    # Staging file must be preserved for future resume
    staging_file = test_dirs["staging"] / "cancel.bin.tmp"
    assert staging_file.is_file()
    assert staging_file.stat().st_size > 0
    # Final target must not exist yet
    assert not (test_dirs["models"] / "cancel.bin").exists()


def test_download_insufficient_disk_space(http_server, test_dirs):
    content = b"DISK_SPACE_CHECK"
    sha = hashlib.sha256(content).hexdigest()
    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/space.bin"
    http_server.routes["/space.bin"] = content

    item = ManifestItem(
        id="space-test",
        display_name="Space Test",
        type="stt-stream",
        size_bytes=len(content),
        url=url,
        sha256=sha,
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="space.bin",
    )

    # Mock shutil.disk_usage to report only 1 KiB free
    fake_usage = shutil._ntuple_diskusage(total=10**9, used=10**9 - 1024, free=1024)
    with patch("shutil.disk_usage", return_value=fake_usage):
        with pytest.raises(InsufficientDiskSpaceError):
            download_item(item)

    # No network requests made
    assert len(http_server.requests_log) == 0


def test_download_archive_extraction(http_server, test_dirs):
    # Build in-memory tar.gz containing binary
    binary_content = b"\x7fELF_PARAKEET_CLI_EXECUTABLE"
    binary_sha = hashlib.sha256(binary_content).hexdigest()

    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
        ti = tarfile.TarInfo("parakeet-v0.5.0-bin-linux-cpu-x64/parakeet-cli")
        ti.size = len(binary_content)
        ti.mode = 0o755
        tar.addfile(ti, io.BytesIO(binary_content))

    tar_bytes = tar_buf.getvalue()
    tar_sha = hashlib.sha256(tar_bytes).hexdigest()

    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/parakeet-release.tar.gz"
    http_server.routes["/parakeet-release.tar.gz"] = tar_bytes

    item = ManifestItem(
        id="parakeet-cli",
        display_name="Parakeet CLI",
        type="binary",
        size_bytes=len(tar_bytes),
        url=url,
        sha256=tar_sha,
        archive_member="parakeet-v0.5.0-bin-linux-cpu-x64/parakeet-cli",
        binary_size_bytes=len(binary_content),
        binary_sha256=binary_sha,
        license="MIT",
        version="0.5.0",
        platform="linux-x86_64",
        filename="parakeet-cli",
    )

    installed_path = download_item(item)

    assert installed_path == test_dirs["bin"] / "parakeet-cli"
    assert installed_path.is_file()
    assert installed_path.read_bytes() == binary_content
    assert os.access(installed_path, os.X_OK)
    assert verify_binary_safety(installed_path, expected_sha256=binary_sha) is True


def test_archive_zip_slip_rejection(http_server, test_dirs):
    binary_content = b"MALICIOUS_FILE"
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
        # Create a member with traversal "../etc/evil"
        ti = tarfile.TarInfo("../evil-file")
        ti.size = len(binary_content)
        tar.addfile(ti, io.BytesIO(binary_content))

    tar_bytes = tar_buf.getvalue()
    tar_sha = hashlib.sha256(tar_bytes).hexdigest()

    port = http_server.server_port
    url = f"http://127.0.0.1:{port}/evil.tar.gz"
    http_server.routes["/evil.tar.gz"] = tar_bytes

    item = ManifestItem(
        id="evil-cli",
        display_name="Evil CLI",
        type="binary",
        size_bytes=len(tar_bytes),
        url=url,
        sha256=tar_sha,
        archive_member="../evil-file",
        binary_sha256=hashlib.sha256(binary_content).hexdigest(),
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="evil-cli",
    )

    with pytest.raises(DownloaderError) as exc_info:
        download_item(item)
    assert "directory traversal" in str(exc_info.value).lower()


def test_unverified_model_rejection():
    item = ManifestItem(
        id="unverified-tool",
        display_name="Unverified Tool",
        type="binary",
        size_bytes=0,
        url="",
        sha256="",
        license="MIT",
        version="0.1.0",
        platform="linux-x86_64",
        filename="unverified-tool",
        verified=False,
        installable=False,
        unverified_reason="No official binary release",
    )

    with pytest.raises(UnverifiedModelError) as exc_info:
        download_item(item)
    assert "No official binary release" in str(exc_info.value)


def test_binary_safety_gate(tmp_path):
    safe_bin = tmp_path / "safe-binary"
    content = b"SAFE_BINARY_BYTES"
    safe_bin.write_bytes(content)
    os.chmod(safe_bin, 0o755)
    valid_sha = hashlib.sha256(content).hexdigest()

    # Valid binary
    assert verify_binary_safety(safe_bin, expected_sha256=valid_sha) is True
    assert ensure_binary_verified(safe_bin, expected_sha256=valid_sha) == safe_bin

    # Non-executable binary
    os.chmod(safe_bin, 0o644)
    assert verify_binary_safety(safe_bin, expected_sha256=valid_sha) is False
    with pytest.raises(UnverifiedModelError):
        ensure_binary_verified(safe_bin, expected_sha256=valid_sha)

    # Wrong checksum
    os.chmod(safe_bin, 0o755)
    assert verify_binary_safety(safe_bin, expected_sha256="bad" * 16) is False
    with pytest.raises(UnverifiedModelError):
        ensure_binary_verified(safe_bin, expected_sha256="bad" * 16)


def test_remove_item(test_dirs):
    model_file = test_dirs["models"] / "to-remove.gguf"
    model_file.write_bytes(b"DATA")

    item = ManifestItem(
        id="to-remove",
        display_name="To Remove",
        type="stt-stream",
        size_bytes=4,
        url="",
        sha256="",
        license="MIT",
        version="1.0",
        platform="linux-x86_64",
        filename="to-remove.gguf",
    )

    assert model_file.is_file()
    assert remove_item(item) is True
    assert not model_file.exists()
    assert remove_item(item) is False
