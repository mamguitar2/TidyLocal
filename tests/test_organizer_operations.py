from pathlib import Path

import pytest

from operations import DestinationExists, identity, move_to_category, roots_for
from undo import undo_latest


def test_organizer_creates_category_and_personal_subfolder(tmp_path):
    home = tmp_path / 'home'
    downloads = home / 'Downloads'
    downloads.mkdir(parents=True)
    source = downloads / 'playlist.m3u'
    source.write_text('track list', encoding='utf-8')
    roots = roots_for(home)

    destination = move_to_category(
        source, 'Personal', 'Music', 'Downloads', identity(source), roots,
    )

    assert Path(destination) == downloads / 'Personal' / 'Music' / source.name
    assert Path(destination).read_text(encoding='utf-8') == 'track list'
    assert not source.exists()


def test_organizer_reuses_existing_similar_wedding_folder(tmp_path):
    home = tmp_path / 'home'
    downloads = home / 'Downloads'
    wedding = downloads / 'Wedding'
    wedding.mkdir(parents=True)
    source = downloads / 'wedding_plan.pdf'
    source.write_bytes(b'plan')

    destination = move_to_category(
        source, 'Personal', 'Wedding', 'Downloads', identity(source), roots_for(home),
    )

    assert Path(destination) == wedding / source.name
    assert not (downloads / 'Personal').exists()


def test_organizer_never_overwrites_and_rejects_unapproved_category(tmp_path):
    home = tmp_path / 'home'
    downloads = home / 'Downloads'
    downloads.mkdir(parents=True)
    source = downloads / 'tax.pdf'
    source.write_bytes(b'new')
    target_folder = downloads / 'Taxes'
    target_folder.mkdir()
    target = target_folder / source.name
    target.write_bytes(b'existing')
    roots = roots_for(home)

    with pytest.raises(DestinationExists):
        move_to_category(source, 'Taxes', '', 'Downloads', identity(source), roots)
    with pytest.raises(ValueError):
        move_to_category(source, 'Other', '', 'Downloads', identity(source), roots)
    assert source.read_bytes() == b'new'
    assert target.read_bytes() == b'existing'


def test_organizer_move_is_restorable_with_existing_undo(tmp_path):
    home = tmp_path / 'home'
    downloads = home / 'Downloads'
    downloads.mkdir(parents=True)
    source = downloads / 'resume.pdf'
    source.write_bytes(b'resume')
    roots = roots_for(home)
    destination = Path(move_to_category(source, 'Career', '', 'Downloads', identity(source), roots))
    log = tmp_path / 'activity.jsonl'
    from operations import append_log
    append_log(log, {
        'timestamp': 'now', 'operation_id': 'test-move', 'action': 'move',
        'source': str(source), 'destination': str(destination),
        'expected': identity(destination), 'success': True,
    })

    result = undo_latest(log, roots)

    assert result['results'][0]['success'] is True
    assert source.read_bytes() == b'resume'
    assert not destination.exists()
