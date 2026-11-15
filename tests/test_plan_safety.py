import json
import uuid
from pathlib import Path

import app
import operations
from undo import undo_latest


def test_move_contract_uses_existing_folder_and_explicit_alternate(tmp_path):
    home = tmp_path.resolve() / "home"
    downloads = home / "Downloads"
    source_dir = downloads / "Incoming"
    destination = downloads / "Sorted"
    source_dir.mkdir(parents=True)
    destination.mkdir()
    source = source_dir / "report.txt"
    source.write_text("source fixture")
    occupied = destination / source.name
    occupied.write_text("keep fixture")
    roots = operations.roots_for(home)

    try:
        operations.move_into_folder(source, destination, operations.identity(source), roots)
    except operations.DestinationExists:
        pass
    else:
        raise AssertionError("Existing destination must be a collision, not overwritten")
    assert source.read_text() == "source fixture"
    assert occupied.read_text() == "keep fixture"

    moved = operations.move_into_folder(
        source,
        destination,
        operations.identity(source),
        roots,
        alternate_name="report-reviewed.txt",
    )
    assert moved == str(destination / "report-reviewed.txt")
    assert Path(moved).read_text() == "source fixture"
    assert occupied.read_text() == "keep fixture"


def test_plan_creates_only_approved_category_and_folder_undo(tmp_path, monkeypatch):
    home = tmp_path.resolve() / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "installer.dmg"
    source.write_text("fixture payload")
    roots = operations.roots_for(home)
    log = tmp_path / "activity.jsonl"
    monkeypatch.setattr(app, "LOG_PATH", log)
    repo = tmp_path / "project"

    target_path = downloads / "Installers" / source.name
    folder, created = app._ensure_plan_folder(str(target_path), roots, repo)
    assert created and folder == downloads / "Installers"
    assert folder.is_dir()
    with __import__("pytest").raises(operations.OperationError):
        app._ensure_plan_folder(str(tmp_path / "outside" / "x.txt"), roots, repo)

    moved = operations.apply_move(
        source, folder / source.name, operations.identity(source), roots, repo
    )
    operations.append_log(
        log,
        {
            "timestamp": "fixture",
            "operation_id": uuid.uuid4().hex,
            "action": "move",
            "source": str(source),
            "destination": moved,
            "expected": operations.identity(Path(moved)),
            "success": True,
        },
    )
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [row["action"] for row in rows] == ["create-folder", "move"]
    assert all(row["operation_id"] for row in rows)

    assert undo_latest(log, roots, repo)["results"][0]["success"]
    assert source.read_text() == "fixture payload" and folder.is_dir()
    assert undo_latest(log, roots, repo)["results"][0]["success"]
    assert not folder.exists()
    assert not undo_latest(log, roots, repo)["results"][0]["success"]


def test_folder_contract_rejects_nonexistent_destination(tmp_path):
    home = tmp_path.resolve() / "home"
    root = home / "Downloads"
    root.mkdir(parents=True)
    source = root / "a.txt"
    source.write_text("fixture")
    with __import__("pytest").raises(operations.OperationError, match="existing approved folder"):
        operations.move_into_folder(
            source, root / "missing", operations.identity(source), operations.roots_for(home)
        )
    assert source.read_text() == "fixture"
