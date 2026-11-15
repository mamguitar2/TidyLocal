import pytest
from pathlib import Path
import operations
from applications import list_applications


def setup_files(tmp_path):
    home = tmp_path.resolve() / 'home'
    root = home / 'Downloads'; root.mkdir(parents=True)
    source = root / 'one.txt'; source.write_text('safe')
    dest = root / 'Organized'; dest.mkdir()
    return home, root, source, dest


def test_path_validation_rejects_outside_symlinks_and_app(tmp_path):
    home, root, source, dest = setup_files(tmp_path)
    roots = operations.roots_for(home)
    assert operations.validate_path(str(source), roots) == source
    outside = tmp_path / 'secret'; outside.write_text('x')
    link = root / 'linked'; link.symlink_to(outside)
    with pytest.raises(operations.OperationError): operations.validate_path(str(link), roots)
    with pytest.raises(operations.OperationError): operations.validate_path(str(outside), roots)
    alias = root / 'alias'; alias.symlink_to(dest, target_is_directory=True)
    with pytest.raises(operations.OperationError, match='Symlink'):
        operations.validate_path(str(alias / 'child.txt'), roots, must_exist=False)
    assert operations.safe_folder_name('Review')
    assert not operations.safe_folder_name('../Review')
    assert not operations.safe_folder_name('bad\\\\name')
    with pytest.raises(operations.OperationError, match='protected'):
        operations.validate_path(str(source), roots, repo=home)


def test_exclusive_move_collision_never_overwrites(tmp_path, monkeypatch):
    home, root, source, dest = setup_files(tmp_path)
    target = dest / source.name; target.write_text('keep')
    roots = operations.roots_for(home)
    with pytest.raises(operations.OperationError, match='exists'):
        operations.apply_move(str(source), str(target), operations.identity(source), roots)
    assert source.read_text() == 'safe' and target.read_text() == 'keep'


def test_move_uses_saved_identity_and_undo_validation(tmp_path):
    home, root, source, dest = setup_files(tmp_path)
    roots = operations.roots_for(home); expected = operations.identity(source)
    target = operations.apply_move(str(source), str(dest / 'one.txt'), expected, roots)
    assert Path(target).read_text() == 'safe' and not source.exists()
    with pytest.raises(operations.OperationError): operations.apply_move(target, str(source), {**operations.identity(Path(target)), 'size': 99}, roots)


def test_trash_delegates_to_send2trash_mock(tmp_path, monkeypatch):
    import sys, types
    called=[]
    monkeypatch.setitem(sys.modules, 'send2trash', types.SimpleNamespace(send2trash=lambda path: called.append(path)))
    path=tmp_path/'fixture.txt'; path.write_text('fixture only')
    result=operations.trash(path)
    assert called == [str(path)]
    assert 'restore it manually in Finder' in result['message']




def test_two_moves_undo_once_each_then_exhausted(tmp_path):
    import json
    import uuid
    from undo import undo_latest
    home, root, first, dest = setup_files(tmp_path)
    second = root / 'two.txt'; second.write_text('second')
    roots = operations.roots_for(home)
    log = tmp_path / 'activity.jsonl'
    for source in (first, second):
        moved = dest / source.name
        operations.exclusive_rename(source, moved)
        operations.append_log(log, {'operation_id': uuid.uuid4().hex, 'action': 'move', 'success': True,
            'source': str(source), 'destination': str(moved), 'expected': operations.identity(moved)})
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(records) == 2
    first_undo = undo_latest(log, roots, tmp_path / 'repo')
    second_undo = undo_latest(log, roots, tmp_path / 'repo')
    third_undo = undo_latest(log, roots, tmp_path / 'repo')
    assert first_undo['results'][0]['success'] and second_undo['results'][0]['success']
    assert not third_undo['results'][0]['success']
    assert first.read_text() == 'safe' and second.read_text() == 'second'
    assert not (dest / first.name).exists() and not (dest / second.name).exists()
    log_records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([record for record in log_records if record['action'] == 'undo']) == 2


def test_undo_fails_closed_on_malformed_jsonl(tmp_path):
    from undo import undo_latest
    home, root, source, dest = setup_files(tmp_path)
    log = tmp_path / 'activity.jsonl'
    log.write_text('{bad json}' + chr(10))
    result = undo_latest(log, operations.roots_for(home))
    assert not result['results'][0]['success']
    assert source.read_text() == 'safe'


def test_created_folder_undo_only_when_empty(tmp_path):
    import uuid
    from undo import undo_latest
    home, root, source, dest = setup_files(tmp_path)
    created = root / 'NewFolder'; created.mkdir()
    log = tmp_path / 'activity.jsonl'
    operations.append_log(log, {'operation_id': uuid.uuid4().hex, 'action': 'create-folder', 'success': True,
        'destination': str(created), 'expected': operations.identity(created)})
    (created / 'keep.txt').write_text('keep')
    blocked = undo_latest(log, operations.roots_for(home))
    assert not blocked['results'][0]['success'] and created.is_dir()
    (created / 'keep.txt').unlink()
    allowed = undo_latest(log, operations.roots_for(home))
    assert allowed['results'][0]['success'] and not created.exists()


def test_undo_never_removes_approved_root_folder(tmp_path):
    import uuid
    from undo import undo_latest
    home, root, source, dest = setup_files(tmp_path)
    log = tmp_path / 'activity.jsonl'
    operations.append_log(log, {'operation_id': uuid.uuid4().hex, 'action': 'create-folder', 'success': True,
        'destination': str(root), 'expected': operations.identity(root)})
    result = undo_latest(log, operations.roots_for(home))
    assert not result['results'][0]['success'] and root.is_dir()


def test_app_listing_disabled_off_mac():
    assert list_applications(platform_name='Linux') == []


def test_app_metadata_unknown_never_uses_mtime(tmp_path, monkeypatch):
    import applications
    bundle = tmp_path / 'Applications' / 'Sample.app'
    bundle.mkdir(parents=True); (bundle / 'binary').write_bytes(b'abc')
    monkeypatch.setattr(applications.subprocess, 'run', lambda *args, **kwargs: type('Result', (), {'stdout':'(null)'})())
    rows = applications.list_applications(home=tmp_path, platform_name='Darwin', system_root=tmp_path / 'SystemApplications')
    row = next(item for item in rows if item['name'] == 'Sample')
    assert row['size'] == 3
    assert row['last_used'] == 'Unknown'


def test_ollama_requires_opt_in_and_loopback():
    from ollama_local import suggest
    with pytest.raises(ValueError, match='disabled'): suggest([], enabled=False)
    with pytest.raises(ValueError, match='loopback'): suggest([], endpoint='http://example.com', enabled=True)
