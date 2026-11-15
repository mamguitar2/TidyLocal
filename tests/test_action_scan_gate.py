from starlette.requests import Request

import app
import operations


def make_request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/actions",
            "headers": [(b"host", b"127.0.0.1:8000"), (b"origin", b"http://127.0.0.1:8000")],
            "query_string": b"",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def setup_job(monkeypatch, tmp_path, files=None, folders=None):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir(exist_ok=True)
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    job_id = "scan-gate-test"
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {"status": "complete", "result": {"files": files or [], "folders": folders or []}},
    )
    return job_id


def test_open_rejects_unscanned_file(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    source = roots["Downloads"] / "unscanned.txt"
    source.write_text("content")
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    monkeypatch.setitem(
        app._jobs, "scan-gate-test", {"status": "complete", "result": {"files": [], "folders": []}}
    )
    monkeypatch.setattr(
        app, "open_file", lambda path: (_ for _ in ()).throw(AssertionError("must not open"))
    )

    result = app.perform_action(
        app.ActionRequest(action="open", job_id="scan-gate-test", source=str(source)),
        make_request(),
    )

    assert not result["results"][0].get("success", False)
    assert "scanned" in result["results"][0]["message"]


def test_open_rejects_stale_scanned_identity(monkeypatch, tmp_path):
    source = tmp_path / "Downloads" / "changed.txt"
    source.parent.mkdir(parents=True)
    source.write_text("current contents")
    job_id = setup_job(monkeypatch, tmp_path)
    stale_identity = {"size": 1, "mtime_ns": 0, "device": -1, "inode": -1}
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {
            "status": "complete",
            "result": {"files": [{"path": str(source), "identity": stale_identity}], "folders": []},
        },
    )
    monkeypatch.setattr(
        app, "open_file", lambda path: (_ for _ in ()).throw(AssertionError("must not open"))
    )

    result = app.perform_action(
        app.ActionRequest(action="open", job_id=job_id, source=str(source)), make_request()
    )

    assert not result["results"][0].get("success", False)
    assert "changed" in result["results"][0]["message"]


def test_reveal_rejects_unscanned_directory(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    folder = roots["Downloads"] / "private"
    folder.mkdir()
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    monkeypatch.setitem(
        app._jobs, "scan-gate-test", {"status": "complete", "result": {"files": [], "folders": []}}
    )
    monkeypatch.setattr(
        app, "reveal", lambda path: (_ for _ in ()).throw(AssertionError("must not reveal"))
    )

    result = app.perform_action(
        app.ActionRequest(action="reveal", job_id="scan-gate-test", source=str(folder)),
        make_request(),
    )

    assert not result["results"][0].get("success", False)
    assert "scanned" in result["results"][0]["message"]


def test_reveal_rejects_stale_scanned_directory_identity(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    folder = roots["Downloads"] / "reviewed"
    folder.mkdir()
    job_id = "scan-gate-test"
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    stale_identity = {"size": 1, "mtime_ns": 0, "device": -1, "inode": -1}
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {
            "status": "complete",
            "result": {"files": [], "folders": [{"path": str(folder), "identity": stale_identity}]},
        },
    )
    monkeypatch.setattr(
        app, "reveal", lambda path: (_ for _ in ()).throw(AssertionError("must not reveal"))
    )

    result = app.perform_action(
        app.ActionRequest(action="reveal", job_id=job_id, source=str(folder)), make_request()
    )

    assert not result["results"][0].get("success", False)
    assert "changed" in result["results"][0]["message"]


def test_reveal_accepts_scanned_directory_with_matching_identity(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    folder = roots["Downloads"] / "reviewed"
    folder.mkdir()
    job_id = "scan-gate-test"
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {
            "status": "complete",
            "result": {
                "files": [],
                "folders": [{"path": str(folder), "identity": operations.identity(folder)}],
            },
        },
    )
    monkeypatch.setattr(app, "reveal", lambda path: {"success": True, "message": "revealed"})

    result = app.perform_action(
        app.ActionRequest(action="reveal", job_id=job_id, source=str(folder)), make_request()
    )

    assert result["results"][0]["success"]


def test_cancelled_scan_cannot_authorize_file_action(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    source = roots["Downloads"] / "partial.txt"
    source.write_text("content")
    job_id = "cancelled-scan-test"
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {
            "status": "cancelled",
            "result": {
                "files": [{"path": str(source), "identity": operations.identity(source)}],
                "folders": [],
            },
        },
    )
    monkeypatch.setattr(
        app, "open_file", lambda path: (_ for _ in ()).throw(AssertionError("must not open"))
    )

    result = app.perform_action(
        app.ActionRequest(action="open", job_id=job_id, source=str(source)), make_request()
    )

    assert not result["results"][0].get("success", False)
    assert "completed scan" in result["results"][0]["message"]


def test_cancelled_scan_cannot_authorize_organize_action(monkeypatch, tmp_path):
    roots = {name: tmp_path / name for name in ("Downloads", "Desktop", "Documents")}
    for root in roots.values():
        root.mkdir()
    source = roots["Downloads"] / "partial.txt"
    source.write_text("content")
    job_id = "cancelled-organize-test"
    monkeypatch.setattr(app, "roots_for", lambda: roots)
    monkeypatch.setattr(app, "_check_local_request", lambda request: None)
    monkeypatch.setitem(
        app._jobs,
        job_id,
        {
            "status": "cancelled",
            "locations": ["Downloads"],
            "result": {
                "files": [
                    {
                        "path": str(source),
                        "location": "Downloads",
                        "identity": operations.identity(source),
                    }
                ],
                "folders": [],
            },
        },
    )
    monkeypatch.setattr(
        app,
        "move_to_category",
        lambda *args: (_ for _ in ()).throw(AssertionError("must not organize")),
    )

    result = app.perform_action(
        app.ActionRequest(action="organize", job_id=job_id, source=str(source), category="Taxes"),
        make_request(),
    )

    assert not result["results"][0].get("success", False)
    assert "completed scan" in result["results"][0]["message"]
