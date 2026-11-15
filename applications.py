"""Optional, metadata-only macOS application inventory."""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path


def _bundle_size(root, max_files=200000, max_seconds=3):
    total = seen = 0
    started = time.monotonic()
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not (Path(current) / name).is_symlink()]
        for name in files:
            path = Path(current) / name
            try:
                if not path.is_symlink():
                    total += path.stat(follow_symlinks=False).st_size
            except OSError:
                pass
            seen += 1
            if seen >= max_files or time.monotonic() - started > max_seconds:
                return None
    return total


def list_applications(home=None, platform_name=None, timeout=2, system_root=Path("/Applications")):
    import platform

    if (platform_name or platform.system()) != "Darwin":
        return []
    roots = [Path(system_root), Path(home or Path.home()) / "Applications"]
    apps: list[dict[str, str | int | None]] = []
    started = time.monotonic()
    for root in roots:
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for bundle in entries:
            if len(apps) >= 200 or time.monotonic() - started > 60:
                return apps
            if bundle.suffix != ".app" or bundle.is_symlink() or not bundle.is_dir():
                continue
            try:
                output = subprocess.run(
                    ["/usr/bin/mdls", "-name", "kMDItemLastUsedDate", "-raw", str(bundle)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                ).stdout.strip()
                last_used = (
                    output
                    if output not in {"(null)", "", "null"} and _valid_date(output)
                    else "Unknown"
                )
                size = _bundle_size(bundle)
                apps.append(
                    {"name": bundle.stem, "path": str(bundle), "size": size, "last_used": last_used}
                )
            except (OSError, subprocess.TimeoutExpired):
                apps.append(
                    {"name": bundle.stem, "path": str(bundle), "size": None, "last_used": "Unknown"}
                )
    return apps


def _valid_date(value):
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False
