"""Read-only scanning primitives for explicitly approved locations."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from organizer import (
    describe_file_type,
    is_non_actionable_artifact,
    is_protected_path,
    is_system_metadata,
    organization_suggestions,
)

LOCATION_NAMES = ("Downloads", "Desktop", "Documents")
MAX_FOLDER_CHOICES = 1500
CATEGORIES = {
    "documents": {
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
        ".odt",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".csv",
    },
    "images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".tif", ".tiff", ".bmp", ".svg"},
    "videos": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"},
    "audio": {".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg"},
    "archives": {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"},
    "installers": {".dmg", ".pkg", ".mpkg", ".iso", ".app"},
    "code": {
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".java",
        ".c",
        ".cpp",
        ".go",
        ".rs",
        ".json",
        ".yaml",
        ".yml",
        ".sh",
    },
}
SYSTEM_BINARY_SUFFIXES = {
    ".dll",
    ".exe",
    ".so",
    ".dylib",
    ".sys",
    ".drv",
    ".ocx",
    ".pyd",
    ".pyc",
    ".class",
    ".o",
    ".a",
    ".lib",
    ".tmp",
    ".cache",
}


class FileIdentity(TypedDict):
    size: int
    mtime_ns: int
    device: int
    inode: int


class ScannedFile(TypedDict):
    name: str
    path: str
    location: str
    top_folder: str
    size: int
    modified: str
    last_opened: str | None
    category: str
    file_type: str
    identity: FileIdentity
    large: bool
    old_download: bool


class ScannedFolder(TypedDict):
    name: str
    path: str
    location: str
    relative: str
    identity: FileIdentity


class LocationSummary(TypedDict):
    count: int
    size: int
    available: bool


class ScanProblem(TypedDict):
    location: str
    message: str


class DuplicateGroup(TypedDict):
    files: list[ScannedFile]
    size: int
    estimated_savings: int


class ScanResult(TypedDict):
    files: list[ScannedFile]
    folders: list[ScannedFolder]
    folder_choices_truncated: bool
    locations: dict[str, LocationSummary]
    duplicates: list[DuplicateGroup]
    recommendations: list[dict[str, object]]
    problems: list[ScanProblem]
    apfs_note: str


def is_user_visible_file(path: Path) -> bool:
    """Keep user-facing files; drop code, system binaries, and opaque artifacts."""
    suffix = path.suffix.lower()
    return (
        categorize(path) != "code"
        and suffix not in SYSTEM_BINARY_SUFFIXES
        and not is_system_metadata(path)
        and not is_non_actionable_artifact(path)
    )


def approved_roots(home: Path | None = None) -> dict[str, Path]:
    home = (home or Path.home()).resolve()
    return {name: (home / name).resolve() for name in LOCATION_NAMES}


def categorize(path: Path) -> str:
    if is_system_metadata(path):
        return "system"
    suffix = path.suffix.lower()
    return next(
        (category for category, extensions in CATEGORIES.items() if suffix in extensions), "other"
    )


def _hash(path: Path, cancel: threading.Event | None = None) -> str | None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            if cancel is not None and cancel.is_set():
                return None
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _last_opened(path: Path) -> str | None:
    """Return macOS Spotlight's last-used date when available; never infer from mtime."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["mdls", "-raw", "-name", "kMDItemLastUsedDate", str(path)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        value = result.stdout.strip()
        if result.returncode != 0 or not value or value == "(null)":
            return None
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(timezone.utc)
            .isoformat()
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def scan_locations(
    selected: list[str], cancel: threading.Event, progress: Callable[[int], None]
) -> ScanResult:
    roots = approved_roots()
    files: list[ScannedFile] = []
    problems: list[ScanProblem] = []
    totals: dict[str, LocationSummary] = {}
    folders: list[ScannedFolder] = []
    folder_choices_truncated = False
    for name in selected:
        root = roots[name]
        totals[name] = {"count": 0, "size": 0, "available": root.is_dir()}
        if not root.is_dir():
            problems.append({"location": name, "message": "Location is unavailable."})
            continue
        for directory, dirs, names in os.walk(
            root,
            topdown=True,
            followlinks=False,
            onerror=lambda error: problems.append(
                {
                    "location": name,
                    "message": "Some paths could not be read (permission denied or unavailable).",
                }
            ),
        ):
            if cancel.is_set():
                break
            current = Path(directory)
            dirs[:] = [
                d
                for d in dirs
                if not (current / d).is_symlink()
                and not d.lower().endswith(".app")
                and not is_protected_path(current / d)
            ]
            for dirname in dirs:
                if len(folders) < MAX_FOLDER_CHOICES:
                    folder_path = current / dirname
                    try:
                        folder_info = folder_path.stat(follow_symlinks=False)
                        folder_record: ScannedFolder = {
                            "name": dirname,
                            "path": str(folder_path),
                            "location": name,
                            "relative": folder_path.relative_to(root).as_posix(),
                            "identity": {
                                "size": folder_info.st_size,
                                "mtime_ns": folder_info.st_mtime_ns,
                                "device": folder_info.st_dev,
                                "inode": folder_info.st_ino,
                            },
                        }
                        folders.append(folder_record)
                    except OSError:
                        problems.append(
                            {
                                "location": name,
                                "message": "Some folders could not be read (permission denied or unavailable).",
                            }
                        )
                else:
                    folder_choices_truncated = True
            for filename in names:
                path = current / filename
                try:
                    if (
                        path.is_symlink()
                        or is_protected_path(path)
                        or not is_user_visible_file(path)
                    ):
                        continue
                    info = path.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode) or not path.resolve().is_relative_to(root):
                        continue
                    relative_parts = path.relative_to(root).parts
                    top_folder = relative_parts[0] if len(relative_parts) > 1 else "(root files)"
                    row: ScannedFile = {
                        "name": filename,
                        "path": str(path),
                        "location": name,
                        "top_folder": top_folder,
                        "size": info.st_size,
                        "modified": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                        "last_opened": None,
                        "category": categorize(path),
                        "file_type": describe_file_type(path),
                        "identity": {
                            "size": info.st_size,
                            "mtime_ns": info.st_mtime_ns,
                            "device": info.st_dev,
                            "inode": info.st_ino,
                        },
                        "large": info.st_size >= 100 * 1024 * 1024,
                        "old_download": name == "Downloads"
                        and info.st_mtime < datetime.now().timestamp() - 180 * 86400,
                    }
                    files.append(row)
                    totals[name]["count"] += 1
                    totals[name]["size"] += info.st_size
                except (OSError, ValueError):
                    problems.append(
                        {
                            "location": name,
                            "message": "Some files could not be read (permission denied or unavailable).",
                        }
                    )
            progress(len(files))
    grouped: defaultdict[tuple[int, str], list[ScannedFile]] = defaultdict(list)
    by_size: defaultdict[int, list[ScannedFile]] = defaultdict(list)
    for item in files:
        by_size[item["size"]].append(item)
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        for item in candidates:
            if cancel.is_set():
                break
            try:
                digest = _hash(Path(item["path"]), cancel)
                if digest is not None:
                    grouped[(item["size"], digest)].append(item)
            except OSError:
                pass
    duplicates: list[DuplicateGroup] = [
        {"files": group, "size": size, "estimated_savings": size * (len(group) - 1)}
        for (size, _), group in grouped.items()
        if len(group) > 1
    ]
    # Spotlight queries are process launches; keep them to the 10 largest files
    # shown in the report rather than stalling a scan on every file.
    largest_paths = {
        item["path"] for item in sorted(files, key=lambda item: item["size"], reverse=True)[:10]
    }
    for item in files:
        if cancel.is_set():
            break
        if item["path"] in largest_paths:
            item["last_opened"] = _last_opened(Path(item["path"]))
    return {
        "files": files,
        "folders": folders,
        "folder_choices_truncated": folder_choices_truncated,
        "locations": totals,
        "duplicates": duplicates,
        "recommendations": organization_suggestions(files, roots, tuple(totals.keys())),
        "problems": problems,
        "apfs_note": "Estimated logical bytes if one copy were retained; APFS clones, compression, "
        "and hard links can make actual reclaimable space lower (or zero).",
    }
