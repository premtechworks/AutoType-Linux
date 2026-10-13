"""Model manifest dataclasses and helpers."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Literal

from autotype.paths import get_bin_dir, get_manifest_path, get_models_dir

log = logging.getLogger("autotype.manifest")


@dataclass(frozen=True)
class ManifestItem:
    id: str
    display_name: str
    type: Literal["stt-stream", "stt-batch", "binary"]
    size_bytes: int
    url: str
    sha256: str
    license: str
    version: str
    platform: str
    filename: str
    verified: bool = True
    installable: bool = True
    recommended: bool = False
    source: str = ""
    description: str = ""
    archive_member: str | None = None
    binary_size_bytes: int | None = None
    binary_sha256: str | None = None
    unverified_reason: str | None = None

    @property
    def target_dir(self) -> Path:
        if self.type == "binary":
            return get_bin_dir()
        return get_models_dir()

    @property
    def target_path(self) -> Path:
        return self.target_dir / self.filename


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size string."""
    if size_bytes <= 0:
        return "0 B"
    num = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if num < 1024.0 or unit == "GB":
            if unit in ("B", "KB"):
                return f"{num:.0f} {unit}"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"


def load_manifest(manifest_path: Path | None = None) -> list[ManifestItem]:
    """Parse and return items from manifest.json."""
    path = manifest_path or get_manifest_path()
    if not path.is_file():
        log.warning("Manifest file not found: %s", path)
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to read manifest %s: %s", path, exc)
        return []

    raw_items = data.get("models") or data.get("items") or []
    items: list[ManifestItem] = []
    for raw in raw_items:
        try:
            item = ManifestItem(
                id=str(raw["id"]),
                display_name=str(raw.get("display_name") or raw.get("name") or raw["id"]),
                type=raw.get("type", "stt-stream"),
                size_bytes=int(raw.get("size_bytes") or raw.get("size") or 0),
                url=str(raw.get("url", "")),
                sha256=str(raw.get("sha256", "")),
                license=str(raw.get("license", "")),
                version=str(raw.get("version", "")),
                platform=str(raw.get("platform", "linux-x86_64")),
                filename=str(raw.get("filename") or Path(raw.get("url", raw["id"])).name),
                verified=bool(raw.get("verified", True)),
                installable=bool(raw.get("installable", True)),
                recommended=bool(raw.get("recommended", False)),
                source=str(raw.get("source", "")),
                description=str(raw.get("description", "")),
                archive_member=raw.get("archive_member"),
                binary_size_bytes=raw.get("binary_size_bytes"),
                binary_sha256=raw.get("binary_sha256"),
                unverified_reason=raw.get("unverified_reason"),
            )
            items.append(item)
        except Exception as exc:
            log.warning("Skipping invalid manifest item: %s (%s)", raw, exc)
    return items


def get_item(item_id: str, manifest_path: Path | None = None) -> ManifestItem | None:
    """Return ManifestItem with the given ID, or None."""
    for item in load_manifest(manifest_path):
        if item.id == item_id:
            return item
    return None


def get_recommended_items(manifest_path: Path | None = None) -> list[ManifestItem]:
    """Return list of recommended installable items."""
    return [i for i in load_manifest(manifest_path) if i.recommended and i.installable]


def is_item_installed(item: ManifestItem) -> bool:
    """Check whether a manifest item is installed on disk and ready for use."""
    target = item.target_path
    if not target.is_file():
        return False
    if item.type == "binary":
        return os.access(target, os.X_OK)
    return target.stat().st_size > 0
