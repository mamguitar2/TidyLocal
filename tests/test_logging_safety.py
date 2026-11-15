import json
import os
import threading

import operations
import scanner


def test_activity_log_permissions_are_private(tmp_path):
    log = tmp_path / "private" / "activity.jsonl"
    operations.append_log(log, {"action": "fixture"})
    assert log.parent.stat().st_mode & 0o777 == 0o700
    assert log.stat().st_mode & 0o777 == 0o600
    assert json.loads(log.read_text().strip())["action"] == "fixture"


def test_hash_observes_cancellation(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"fixture")
    cancel = threading.Event()
    cancel.set()
    assert scanner._hash(path, cancel) is None


def test_undo_move_rolls_back_when_history_append_fails(tmp_path, monkeypatch):
    import uuid
    import undo

    home = tmp_path / "home"
    root = home / "Downloads"
    moved_dir = root / "Sorted"
    moved_dir.mkdir(parents=True)
    original = root / "item.txt"
    moved = moved_dir / original.name
    original.write_text("payload")
    expected = operations.identity(original)
    operations.exclusive_rename(original, moved)
    log = tmp_path / "activity.jsonl"
    operations.append_log(log, {"operation_id": uuid.uuid4().hex, "action": "move", "success": True,
                                "source": str(original), "destination": str(moved), "expected": expected})
    monkeypatch.setattr(undo, "append_log", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))

    result = undo.undo_latest(log, operations.roots_for(home))
    assert not result["results"][0]["success"]
    assert moved.read_text() == "payload"
    assert not original.exists()
