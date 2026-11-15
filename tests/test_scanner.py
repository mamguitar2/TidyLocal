import threading
from pathlib import Path

import pytest

import scanner


def test_protected_system_and_project_paths_are_detected():
    from organizer import is_protected_path

    assert is_protected_path(Path('/Users/test/Desktop/Library/cache.db'))
    assert is_protected_path(Path('/Users/test/Desktop/repo/.git/hooks/applypatch-msg'))
    assert not is_protected_path(Path('/Users/test/Desktop/Notes/report.pdf'))


def test_non_actionable_index_and_numeric_artifact_names_are_filtered():
    from organizer import is_non_actionable_artifact

    assert is_non_actionable_artifact(Path('index.html'))
    assert is_non_actionable_artifact(Path('1234567890123456.tmp'))
    assert is_non_actionable_artifact(Path('aa997a2ca344c70e64fcc08758bfee260136e3'))
    assert is_non_actionable_artifact(Path('applypatch-msg.sample'))
    assert is_non_actionable_artifact(Path('repo/.git/hooks/pre-commit.sample'))
    assert not is_non_actionable_artifact(Path('2024-tax-return.pdf'))
    assert not is_non_actionable_artifact(Path('12345.pdf'))


def test_user_visible_filter_omits_binaries_and_code_but_keeps_documents():
    assert not scanner.is_user_visible_file(Path('library.dll'))
    assert not scanner.is_user_visible_file(Path('build.py'))
    assert scanner.is_user_visible_file(Path('lease.pdf'))
    assert scanner.is_user_visible_file(Path('notes.unknown'))


def test_categories():
    assert scanner.categorize(Path('x.pdf')) == 'documents'
    assert scanner.categorize(Path('x.mp4')) == 'videos'
    assert scanner.categorize(Path('x.unknown')) == 'other'
    assert scanner.categorize(Path('.DS_Store')) == 'system'
    assert scanner.describe_file_type(Path('.DS_Store')) == 'macOS Finder metadata'
    assert scanner.describe_file_type(Path('movie.mp4')) == 'Video'
    from organizer import suggest_file
    metadata = suggest_file(Path('.DS_Store'), location_root=Path('/tmp'))
    assert metadata['protected'] is True
    assert 'stays in place' in metadata['reason']


def test_duplicate_hashing_and_app_symlink_exclusion(tmp_path, monkeypatch):
    home = tmp_path / 'home'; home.mkdir()
    downloads = home / 'Downloads'; downloads.mkdir()
    desktop = home / 'Desktop'; desktop.mkdir()
    documents = home / 'Documents'; documents.mkdir()
    (downloads / 'one.txt').write_bytes(b'same')
    (desktop / 'two.txt').write_bytes(b'same')
    bundle = downloads / 'skip.app'; bundle.mkdir(); (bundle / 'payload').write_text('same')
    outside = tmp_path / 'outside'; outside.mkdir(); (outside / 'secret').write_text('same')
    (downloads / 'escape').symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(scanner, 'approved_roots', lambda _home=None: {n: (home / n).resolve() for n in scanner.LOCATION_NAMES})
    result = scanner.scan_locations(['Downloads', 'Desktop'], threading.Event(), lambda count: None)
    assert len(result['files']) == 2
    assert result['duplicates'][0]['estimated_savings'] == 4
    assert all('secret' not in f['path'] for f in result['files'])


def test_scanner_hides_unmovable_system_metadata(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    for name in scanner.LOCATION_NAMES:
        (home / name).mkdir(parents=True)
    desktop = home / 'Desktop'
    (desktop / 'notes.txt').write_text('keep', encoding='utf-8')
    (desktop / '.DS_Store').write_bytes(b'metadata')
    (desktop / '._notes.txt').write_bytes(b'resource fork')
    monkeypatch.setattr(scanner, 'approved_roots', lambda _home=None: {name: (home / name).resolve() for name in scanner.LOCATION_NAMES})

    result = scanner.scan_locations(['Desktop'], threading.Event(), lambda count: None)

    assert [item['name'] for item in result['files']] == ['notes.txt']


def test_scan_reports_top_level_folder_names(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    for name in scanner.LOCATION_NAMES:
        (home / name).mkdir(parents=True)
    wedding = home / 'Desktop' / 'Wedding'
    wedding.mkdir()
    (wedding / 'guest-list.txt').write_text('guest data', encoding='utf-8')
    monkeypatch.setattr(scanner, 'approved_roots', lambda _home=None: {name: home / name for name in scanner.LOCATION_NAMES})
    result = scanner.scan_locations(['Desktop'], threading.Event(), lambda count: None)
    assert result['files'][0]['top_folder'] == 'Wedding'
    assert any(folder['relative'] == 'Wedding' for folder in result['folders'])
    assert result['recommendations'] == []  # Already in its matching Wedding folder.


def test_photos_remain_in_scan_and_are_available_in_organizer_recommendations(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    for name in scanner.LOCATION_NAMES:
        (home / name).mkdir(parents=True)
    photo = home / 'Desktop' / 'family.jpg'
    photo.write_bytes(b'photo')
    monkeypatch.setattr(scanner, 'approved_roots', lambda _home=None: {name: (home / name).resolve() for name in scanner.LOCATION_NAMES})

    result = scanner.scan_locations(['Desktop'], threading.Event(), lambda count: None)

    assert result['files'][0]['category'] == 'images'
    assert len(result['recommendations']) == 1
    assert result['recommendations'][0]['file_category'] == 'images'


def test_chatgpt_atlas_installer_gets_reversible_trash_recommendation(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    for name in scanner.LOCATION_NAMES:
        (home / name).mkdir(parents=True)
    installer = home / 'Downloads' / 'ChatGPT Atlas.dmg'
    installer.write_bytes(b'installer')
    monkeypatch.setattr(scanner, 'approved_roots', lambda _home=None: {name: (home / name).resolve() for name in scanner.LOCATION_NAMES})

    result = scanner.scan_locations(['Downloads'], threading.Event(), lambda count: None)
    suggestion = result['recommendations'][0]

    assert suggestion['file_category'] == 'installers'
    assert suggestion['recommended_action'] == 'trash'
    assert 'will not uninstall' in suggestion['reason']


def test_resume_inside_existing_career_folder_is_not_suggested_for_move(tmp_path):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Desktop'
    career = root / 'Career'
    career.mkdir(parents=True)
    resume = career / 'resume.pdf'
    resume.write_bytes(b'resume')

    suggestion = suggest_file(resume, location_root=root)

    assert suggestion['category'] == 'Career'
    assert suggestion['needs_review'] is False
    assert suggestion['already_organized'] is True


@pytest.mark.parametrize(('folder_name','file_name','contents','expected'), [
    ('Wedding Plans', 'invoice.txt', 'tax return invoice', 'Personal/Wedding'),
    ('My Music', 'track.mp3', None, 'Personal/Music'),
])
def test_existing_wedding_and_music_folders_are_treated_as_already_sorted(tmp_path, folder_name, file_name, contents, expected):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Desktop'
    folder = root / folder_name
    folder.mkdir(parents=True)
    source = folder / file_name
    if contents is None:
        source.write_bytes(b'audio')
    else:
        source.write_text(contents, encoding='utf-8')

    suggestion = suggest_file(source, location_root=root)

    assert f"{suggestion['category']}/{suggestion['subcategory']}" == expected
    assert suggestion['needs_review'] is False
    assert suggestion['already_organized'] is True


def test_files_inside_similar_tax_folder_are_already_organized(tmp_path):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Desktop'
    tax_folder = root / 'Tax Documents'
    tax_year = tax_folder / '2024'
    tax_year.mkdir(parents=True)
    source = tax_year / 'scan_001.pdf'
    source.write_bytes(b'pdf data')

    suggestion = suggest_file(source, location_root=root)

    assert suggestion['category'] == 'Taxes'
    assert suggestion['needs_review'] is False
    assert suggestion['already_organized'] is True
    assert suggestion['destination'] == str(tax_folder)
    assert 'Tax Documents' in suggestion['reason']


def test_photo_inside_tax_folder_is_not_auto_classified_as_taxes(tmp_path):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Desktop'
    tax_folder = root / 'Taxes'
    tax_folder.mkdir(parents=True)
    photo = tax_folder / 'family-photo.jpg'
    photo.write_bytes(b'image data')

    suggestion = suggest_file(photo, location_root=root)

    assert suggestion['category'] == ''
    assert suggestion['needs_review'] is True


def test_organizer_suggests_tax_from_filename_and_local_text(tmp_path):
    from organizer import suggest_file
    home = tmp_path / 'home'; root = home / 'Downloads'; root.mkdir(parents=True)
    source = root / '2024_tax_return.txt'
    source.write_text('Federal return and IRS filing notes', encoding='utf-8')
    suggestion = suggest_file(source, location_root=root)
    assert suggestion['category'] == 'Taxes'
    assert suggestion['destination'] == str(root / 'Taxes')
    assert suggestion['confidence'] >= 0.7
    assert 'Filename' in suggestion['reason']
    assert suggestion['content_checked'] is True


def test_bad_caddy_name_overrides_audio_file_type(tmp_path):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Downloads'
    root.mkdir(parents=True)
    audio = root / 'Bad_Caddy_Audio_Recording.mp3'
    audio.write_bytes(b'audio data')
    suggestion = suggest_file(audio, location_root=root)
    assert (suggestion['category'], suggestion['subcategory']) == ('Personal', 'Bad Caddy Apparel Co')
    assert suggestion['needs_review'] is False


def test_personal_subcategory_and_uncertain_review(tmp_path):
    from organizer import suggest_file
    root = tmp_path / 'home' / 'Documents'; root.mkdir(parents=True)
    poa = root / 'durable_poa.txt'; poa.write_text('Power of attorney document', encoding='utf-8')
    unknown = root / 'notes.txt'; unknown.write_text('Some random content', encoding='utf-8')
    poa_suggestion = suggest_file(poa, location_root=root)
    unknown_suggestion = suggest_file(unknown, location_root=root)
    assert (poa_suggestion['category'], poa_suggestion['subcategory']) == ('Personal', 'Power of Attorney')
    assert poa_suggestion['needs_review'] is False
    assert unknown_suggestion['needs_review'] is True
    assert unknown_suggestion['category'] == ''
    assert unknown_suggestion['destination'] == ''


def test_api_selection_whitelist_and_origin(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    monkeypatch.setattr(app, 'scan_locations', lambda selected, cancel, progress: {'files': [], 'locations': {}, 'duplicates': [], 'problems': []})
    client = TestClient(app.app)
    headers = {'host': '127.0.0.1:8123', 'origin': 'http://127.0.0.1:8123'}
    assert client.post('/api/scan', json={'locations':['/tmp']}, headers=headers).status_code == 400
    assert client.post('/api/scan', json={'locations':['Downloads']}, headers={**headers,'origin':'https://evil.test'}).status_code == 403
    assert client.post('/api/scan', json={'locations':['Downloads']}, headers={'host':headers['host']}).status_code == 403
    response = client.post('/api/scan', json={'locations':['Downloads']}, headers=headers)
    assert response.status_code == 200
    status = client.get('/api/scan/' + response.json()['job_id'], headers=headers)
    assert status.status_code == 200


def test_cancellation(monkeypatch):
    import app
    import time
    entered, finished = threading.Event(), threading.Event()

    def controlled_scan(selected, cancel, progress):
        entered.set()
        assert cancel.wait(timeout=2)
        finished.set()
        return {'files': [], 'locations': {}, 'duplicates': [], 'problems': []}

    monkeypatch.setattr(app, 'scan_locations', controlled_scan)
    job_id = app._start_job(['Downloads'])
    assert entered.wait(timeout=1)
    with app._jobs_lock:
        record = app._jobs[job_id]
    record['cancel'].set()
    assert finished.wait(timeout=1)
    for _ in range(100):
        if record['status'] != 'running':
            break
        time.sleep(.01)
    assert record['status'] == 'cancelled'


def test_demo_requires_matching_origin(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    client = TestClient(app.app)
    assert client.post('/api/demo').status_code == 403
    monkeypatch.setattr(app, 'create_demo_files', lambda: Path('/tmp/demo-test'))
    headers = {'host': 'localhost:9234', 'origin': 'http://localhost:9234'}
    assert client.post('/api/demo', headers=headers).status_code == 200
