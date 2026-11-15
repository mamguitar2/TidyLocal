from pathlib import Path

import pytest

import operations
from operations import DestinationExists, identity, move_to_category, roots_for
from undo import undo_latest


def test_organizer_creates_category_and_personal_subfolder(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "playlist.m3u"
    source.write_text("track list", encoding="utf-8")
    roots = roots_for(home)

    destination = move_to_category(
        source,
        "Personal",
        "Music",
        "Downloads",
        identity(source),
        roots,
    )

    assert Path(destination) == downloads / "Personal" / "Music" / source.name
    assert Path(destination).read_text(encoding="utf-8") == "track list"
    assert not source.exists()


def test_organizer_reuses_existing_similar_wedding_folder(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    wedding = downloads / "Wedding"
    wedding.mkdir(parents=True)
    source = downloads / "wedding_plan.pdf"
    source.write_bytes(b"plan")

    destination = move_to_category(
        source,
        "Personal",
        "Wedding",
        "Downloads",
        identity(source),
        roots_for(home),
    )

    assert Path(destination) == wedding / source.name
    assert not (downloads / "Personal").exists()


def test_organizer_never_overwrites_and_rejects_unapproved_category(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "tax.pdf"
    source.write_bytes(b"new")
    target_folder = downloads / "Taxes"
    target_folder.mkdir()
    target = target_folder / source.name
    target.write_bytes(b"existing")
    roots = roots_for(home)

    with pytest.raises(DestinationExists):
        move_to_category(source, "Taxes", "", "Downloads", identity(source), roots)
    with pytest.raises(ValueError):
        move_to_category(source, "Other", "", "Downloads", identity(source), roots)
    assert source.read_bytes() == b"new"
    assert target.read_bytes() == b"existing"


def test_failed_move_preserves_source_and_removes_new_empty_folders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "playlist.m3u"
    source.write_bytes(b"do not lose me")

    def fail_exclusive_rename(source_path, destination_path):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(operations, "exclusive_rename", fail_exclusive_rename)

    with pytest.raises(OSError, match="simulated filesystem failure"):
        move_to_category(
            source,
            "Personal",
            "Music",
            "Downloads",
            identity(source),
            roots_for(home),
        )

    assert source.read_bytes() == b"do not lose me"
    assert not (downloads / "Personal").exists()


def test_category_search_cannot_escape_approved_roots(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "resume.pdf"
    source.write_bytes(b"keep original")
    external = tmp_path / "unapproved"
    (external / "Career").mkdir(parents=True)

    with pytest.raises(operations.OperationError, match="approved location"):
        move_to_category(
            source,
            "Career",
            "",
            "Downloads",
            identity(source),
            roots_for(home),
            search_roots={"External": external},
        )

    assert source.read_bytes() == b"keep original"
    assert (external / "Career").is_dir()
    assert list((external / "Career").iterdir()) == []


def test_organizer_move_is_restorable_with_existing_undo(tmp_path):
    home = tmp_path / "home"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    source = downloads / "resume.pdf"
    source.write_bytes(b"resume")
    roots = roots_for(home)
    destination = Path(move_to_category(source, "Career", "", "Downloads", identity(source), roots))
    log = tmp_path / "activity.jsonl"
    from operations import append_log

    append_log(
        log,
        {
            "timestamp": "now",
            "operation_id": "test-move",
            "action": "move",
            "source": str(source),
            "destination": str(destination),
            "expected": identity(destination),
            "success": True,
        },
    )

    result = undo_latest(log, roots)

    assert result["results"][0]["success"] is True
    assert source.read_bytes() == b"resume"
    assert not destination.exists()
