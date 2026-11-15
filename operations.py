"""Guarded filesystem actions. Every path is revalidated immediately before use."""
from __future__ import annotations
import ctypes
import json
import os
import platform
import subprocess
from pathlib import Path

from organizer import find_similar_folder, is_protected_path, is_system_metadata, resolve_destination_folder


class OperationError(ValueError):
    pass


class DestinationExists(OperationError):
    pass


def roots_for(home=None):
    home = Path(home or Path.home()).resolve()
    return {name: (home / name).resolve() for name in ("Downloads", "Desktop", "Documents")}


def validate_path(raw, roots, *, must_exist=True, repo=None):
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise OperationError("Path must be absolute")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise OperationError("Symlink paths are not allowed")
    resolved = path.resolve(strict=must_exist)
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots.values()):
        raise OperationError("Path must be inside an approved location")
    if repo and (resolved == repo or resolved.is_relative_to(repo)):
        raise OperationError("Application files are protected")
    if is_protected_path(resolved):
        raise OperationError("Protected system or project path")
    if must_exist and not (resolved.is_file() or resolved.is_dir()):
        raise OperationError("Path is not a regular file or directory")
    if must_exist and resolved.is_file() and resolved.name.endswith(".app"):
        raise OperationError("Application bundles are protected")
    return resolved


def safe_folder_name(name):
    return bool(name) and name not in {".", ".."} and Path(name).name == name and "/" not in name and chr(92) not in name and not any(ord(character) < 32 for character in name)


def identity(path):
    info = path.stat(follow_symlinks=False)
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "device": info.st_dev, "inode": info.st_ino}


def exclusive_rename(source, destination):
    """Use OS exclusive rename primitives; never fall back to an overwriting rename."""
    if platform.system() == "Darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = getattr(libc, "renamex_np", None)
        if function is None:
            raise OperationError("Safe exclusive moves unavailable on this macOS")
        result = function(os.fsencode(source), os.fsencode(destination), 0x00000004)
        if result != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(destination))
        return
    if platform.system() == "Linux":
        libc = ctypes.CDLL(None, use_errno=True)
        function = getattr(libc, "renameat2", None)
        if function is None:
            raise OperationError("Safe exclusive moves unavailable on this system")
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        if result != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(destination))
        return
    raise OperationError("Safe exclusive moves are unavailable on this platform")


def apply_move(source, destination, expected, roots, repo=None):
    source = validate_path(source, roots, repo=repo)
    if not source.is_file():
        raise OperationError("Only regular files can be moved")
    if identity(source) != expected:
        raise OperationError("Source changed since it was reviewed")
    destination = Path(destination)
    if destination.name in {".", ".."} or not destination.name:
        raise OperationError("Destination must include a safe file name")
    parent = validate_path(destination.parent, roots, must_exist=True, repo=repo)
    target = parent / destination.name
    if target.exists() or target.is_symlink():
        raise DestinationExists(f"Destination exists: {target}")
    exclusive_rename(source, target)
    return str(target)


def move_into_folder(source, folder, expected, roots, repo=None, alternate_name=None):
    folder = Path(folder)
    if not folder.is_dir():
        raise OperationError("Destination must be an existing approved folder")
    folder = validate_path(folder, roots, repo=repo)
    name = alternate_name if alternate_name is not None else Path(source).name
    if not safe_folder_name(name):
        raise OperationError("Choose a single safe destination filename")
    return apply_move(source, str(folder / name), expected, roots, repo)


def move_to_category(source, category, subcategory, location, expected, roots, repo=None, search_roots=None):
    """Move a scanned file to a whitelisted category under its approved source root."""
    categories = {"Taxes", "Finances", "Career", "Personal"}
    personal_subfolders = {"Music", "Bad Caddy Apparel Co", "Rent", "Power of Attorney", "Wedding"}
    if category not in categories or (subcategory and (category != "Personal" or subcategory not in personal_subfolders)):
        raise OperationError("Choose one of the approved organizer destinations")
    root = roots.get(location)
    if root is None:
        raise OperationError("Source location is not approved")
    source = validate_path(source, roots, repo=repo)
    if not source.is_file():
        raise OperationError("Only regular files can be organized")
    if is_system_metadata(source):
        raise OperationError("System metadata files are protected and stay in place")
    if identity(source) != expected:
        raise OperationError("Source changed since it was reviewed")
    validate_path(root, roots, repo=repo)

    def ensure_directory(parent: Path, name: str) -> Path:
        existing = find_similar_folder(parent, name)
        folder = existing or (parent / name)
        validate_path(folder.parent, roots, repo=repo)
        if not folder.exists() and not folder.is_symlink():
            folder.mkdir()
        validated = validate_path(folder, roots, repo=repo)
        if not validated.is_dir():
            raise OperationError("Organizer destination is not a folder")
        return validated

    candidate_roots = [root]
    for other_root in (search_roots or {}).values():
        if other_root != root and other_root not in candidate_roots:
            candidate_roots.append(other_root)
    destination_dir = None
    for candidate_root in candidate_roots:
        existing = resolve_destination_folder(candidate_root, category, subcategory)
        if existing.is_dir():
            destination_dir = validate_path(existing, roots, repo=repo)
            break
    if destination_dir is None:
        direct_personal_folder = find_similar_folder(root, subcategory) if subcategory else None
        if direct_personal_folder:
            destination_dir = validate_path(direct_personal_folder, roots, repo=repo)
        else:
            category_folder = ensure_directory(root, category)
            destination_dir = ensure_directory(category_folder, subcategory) if subcategory else category_folder
    destination = destination_dir / source.name
    if destination == source:
        raise OperationError("File is already in that folder")
    return apply_move(source, str(destination), expected, roots, repo)


def open_file(path):
    """Open a scanned regular file with its macOS default application."""
    if platform.system() != "Darwin":
        return {"success": False, "message": "Opening files this way is available only on macOS."}
    try:
        subprocess.run(["/usr/bin/open", str(path)], check=True, shell=False, timeout=10, capture_output=True)
        return {"success": True, "message": "Opened with the default application."}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"success": False, "message": f"Could not open file: {exc}"}


def reveal(path):
    if platform.system() != "Darwin":
        return {"success": False, "message": "Finder reveal is available only on macOS."}
    try:
        subprocess.run(["/usr/bin/open", "-R", str(path)], check=True, shell=False, timeout=10, capture_output=True)
        return {"success": True, "message": "Revealed in Finder."}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"success": False, "message": f"Finder reveal failed: {exc}"}


def trash(path):
    try:
        from send2trash import send2trash
    except ImportError as exc:
        raise OperationError("Move to Trash unavailable: send2trash is not installed") from exc
    send2trash(str(path))
    return {"success": True, "message": "Moved to macOS Trash; restore it manually in Finder."}


def append_log(path, record):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise PermissionError("Activity log directory must be a real directory")
    parent_mode = path.parent.stat().st_mode & 0o777
    os.chmod(path.parent, parent_mode & 0o700)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        file_mode = os.fstat(fd).st_mode & 0o777
        os.fchmod(fd, file_mode & 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", closefd=False) as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
