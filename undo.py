"""Safe, item-by-item undo for logged moves and empty folders created by TidyLocal."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from operations import (
    OperationError,
    append_log,
    apply_move,
    exclusive_rename,
    identity,
    validate_path,
)


def undo_latest(log_path, roots, repo=None):
    log_path = Path(log_path)
    if not log_path.exists():
        return {"results": [{"success": False, "message": "No activity to undo."}]}
    try:
        records = [
            record
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for record in [json.loads(line)]
            if isinstance(record, dict)
        ]
    except (OSError, json.JSONDecodeError):
        return {
            "results": [
                {
                    "success": False,
                    "message": "Activity history is unreadable; nothing was changed.",
                }
            ]
        }
    undone_ids = {
        row.get("undo_of") for row in records if row.get("action") == "undo" and row.get("success")
    }
    legacy_undone = {
        (row.get("source"), row.get("destination"))
        for row in records
        if row.get("action") == "undo" and row.get("success")
    }
    candidate = next(
        (
            row
            for row in reversed(records)
            if row.get("success")
            and row.get("action") in {"move", "create-folder"}
            and (
                (row.get("operation_id") and row["operation_id"] not in undone_ids)
                or (
                    not row.get("operation_id")
                    and row.get("action") == "move"
                    and (row.get("destination"), row.get("source")) not in legacy_undone
                )
            )
        ),
        None,
    )
    if candidate is None:
        return {
            "results": [
                {
                    "success": False,
                    "message": "No restorable move or empty created folder. Trash must be restored in Finder.",
                }
            ]
        }
    try:
        if candidate["action"] == "create-folder":
            folder = validate_path(candidate["destination"], roots, repo=repo)
            if folder in roots.values():
                raise OperationError("Approved root folders are never removed")
            expected = candidate.get("expected", {})
            actual = identity(folder)
            if not folder.is_dir() or any(
                actual.get(key) != expected.get(key) for key in ("device", "inode")
            ):
                raise OperationError("Created folder changed; undo skipped")
            if next(folder.iterdir(), None) is not None:
                raise OperationError("Created folder is not empty; undo skipped")
            folder.rmdir()
            try:
                append_log(
                    log_path,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "operation_id": uuid.uuid4().hex,
                        "action": "undo",
                        "undo_of": candidate.get("operation_id"),
                        "source": str(folder),
                        "destination": "",
                        "success": True,
                    },
                )
            except OSError as log_error:
                try:
                    folder.mkdir(exist_ok=False)
                except OSError as rollback_error:
                    raise OperationError(
                        f"Folder removed but undo logging and restoration failed: {rollback_error}"
                    ) from log_error
                raise OperationError(
                    f"Folder removal was restored because undo logging failed: {log_error}"
                ) from log_error
            message = f"Removed empty created folder {folder}"
        else:
            moved = validate_path(candidate["destination"], roots, repo=repo)
            if identity(moved) != candidate.get("expected"):
                raise OperationError("Moved file changed; undo skipped")
            destination = apply_move(
                str(moved), candidate["source"], candidate["expected"], roots, repo
            )
            try:
                append_log(
                    log_path,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "operation_id": uuid.uuid4().hex,
                        "action": "undo",
                        "undo_of": candidate.get("operation_id"),
                        "source": str(moved),
                        "destination": destination,
                        "success": True,
                    },
                )
            except OSError as log_error:
                try:
                    exclusive_rename(Path(destination), moved)
                except OSError as rollback_error:
                    raise OperationError(
                        f"File restored to {destination}, but undo logging and rollback failed: {rollback_error}"
                    ) from log_error
                raise OperationError(
                    f"Undo move was rolled back because logging failed: {log_error}"
                ) from log_error
            message = f"Restored to {destination}"
        return {"results": [{"success": True, "message": message}]}
    except (OperationError, OSError) as exc:
        return {"results": [{"success": False, "message": str(exc)}]}
