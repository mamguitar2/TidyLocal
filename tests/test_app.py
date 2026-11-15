from pathlib import Path

import app


def test_disk_metrics_uses_system_usage(monkeypatch):
    class Usage:
        total = 1000
        used = 600
        free = 400

    monkeypatch.setattr("shutil.disk_usage", lambda path: Usage())
    assert app.disk_metrics("/") == {"total": 1000, "used": 600, "available": 400}


def test_demo_files_are_confined_to_temporary_directory(monkeypatch, tmp_path):
    demo_root = tmp_path / "tidylocal-demo-test"
    def make_demo_root(prefix):
        demo_root.mkdir()
        return str(demo_root)
    monkeypatch.setattr(app.tempfile, "mkdtemp", make_demo_root)
    result = app.create_demo_files()
    assert result == demo_root
    assert (demo_root / "tax_return_2024.pdf").read_text().startswith("TidyLocal demo placeholder")
    assert (demo_root / "Family Photos").is_dir()
    assert not (tmp_path / "tax_return_2024.pdf").exists()
    assert len(list(demo_root.iterdir())) == len(app.SAMPLE_FILES)
