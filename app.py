from __future__ import annotations

import os
import json
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from scanner import LOCATION_NAMES, scan_locations
from organizer import find_similar_folder
from operations import DestinationExists, OperationError, append_log, apply_move, exclusive_rename, identity, move_into_folder, move_to_category, open_file, reveal, roots_for, safe_folder_name, trash, validate_path
from applications import list_applications
from ollama_local import suggest as ollama_suggest
from undo import undo_latest

BASE_DIR = Path(__file__).parent
SAMPLE_FILES = [
    {"name": "Family Photos", "kind": "Folder", "size": "1.8 GB", "modified": "Today"},
    {"name": "tax_return_2024.pdf", "kind": "PDF document", "size": "2.4 MB", "modified": "Yesterday"},
    {"name": "Weekend playlist.m4a", "kind": "Audio", "size": "86 MB", "modified": "Mar 12"},
    {"name": "project-draft.zip", "kind": "Archive", "size": "340 MB", "modified": "Mar 08"},
    {"name": "meeting-notes.docx", "kind": "Word document", "size": "128 KB", "modified": "Mar 02"},
]


def disk_metrics(path: str = "/") -> dict[str, Any]:
    """Return actual filesystem capacity metrics without reading user files."""
    usage = shutil.disk_usage(path)
    return {"total": usage.total, "used": usage.used, "available": usage.free}


def create_demo_files() -> Path:
    """Create harmless demo placeholders in an OS-managed temporary directory."""
    folder = Path(tempfile.mkdtemp(prefix="tidylocal-demo-"))
    for item in SAMPLE_FILES:
        if item["kind"] != "Folder":
            (folder / item["name"]).write_text("TidyLocal demo placeholder — not a real personal file.\n", encoding="utf-8")
    (folder / "Family Photos").mkdir()
    return folder


app = FastAPI(title="TidyLocal", docs_url=None, redoc_url=None)
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_MAX_RETAINED_JOBS = 20
_MAX_RUNNING_JOBS = 2


class ScanRequest(BaseModel):
    locations: list[str]


class OllamaRequest(BaseModel):
    enabled: bool = False
    endpoint: str = "http://127.0.0.1:11434/api/generate"
    model: str = "llama3.2"
    metadata: list[dict[str, Any]] = Field(default_factory=list)


class ActionRequest(BaseModel):
    action: str
    job_id: str | None = None
    source: str | None = None
    sources: list[str] = Field(default_factory=list)
    destination: str | None = None
    name: str | None = None
    expected: dict[str, int] | None = None
    alternate_name: str | None = None
    plan: list[dict[str, str]] = Field(default_factory=list)
    category: str | None = None
    subcategory: str | None = None


def _check_local_request(request: Request) -> None:
    from urllib.parse import urlsplit

    host = request.headers.get("host", "").lower()
    try:
        host_parts = urlsplit(f"//{host}")
        port = host_parts.port
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid local Host")
    if host_parts.hostname not in {"127.0.0.1", "localhost", "::1"} or host_parts.username or host_parts.password:
        raise HTTPException(status_code=403, detail="Local requests only")
    origin = request.headers.get("origin")
    if not origin:
        # Modern browsers omit Origin on same-origin GETs; fetch metadata provides
        # an equivalent same-site signal. Reject requests lacking either proof.
        if request.headers.get("sec-fetch-site") == "same-origin":
            return
        raise HTTPException(status_code=403, detail="Origin header required")
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid Origin")
    if (parsed.scheme != "http" or parsed.hostname != host_parts.hostname or origin_port != port
            or parsed.netloc.lower() != host or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise HTTPException(status_code=403, detail="Origin must exactly match this local app")


def _start_job(selected: list[str]) -> str:
    job_id = uuid.uuid4().hex
    cancel = threading.Event()
    record: dict[str, Any] = {"id": job_id, "locations": list(selected), "status": "running", "progress": 0, "result": None, "cancel": cancel}
    with _jobs_lock:
        completed = [key for key, value in _jobs.items() if value["status"] != "running"]
        while len(_jobs) >= _MAX_RETAINED_JOBS and completed:
            del _jobs[completed.pop(0)]
        if len(_jobs) >= _MAX_RETAINED_JOBS or sum(value["status"] == "running" for value in _jobs.values()) >= _MAX_RUNNING_JOBS:
            raise HTTPException(status_code=429, detail="Scan capacity is full; wait for a scan to finish")
        _jobs[job_id] = record
    def progress(count: int) -> None:
        record["progress"] = count
    def run() -> None:
        try:
            result = scan_locations(selected, cancel, progress)
            record["result"] = result
            record["status"] = "cancelled" if cancel.is_set() else "complete"
        except Exception:
            record["status"] = "error"
            record["error"] = "Scan failed unexpectedly."
    threading.Thread(target=run, daemon=True).start()
    return job_id


@app.get("/api/activity")
def activity(request: Request):
    _check_local_request(request)
    if not LOG_PATH.exists(): return {"items": []}
    try:
        with LOG_PATH.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            offset = max(0, end - 256 * 1024)
            stream.seek(offset)
            if offset:
                stream.readline()  # Discard a possibly partial first JSONL record.
            tail = stream.read().decode("utf-8", errors="replace").splitlines()
        records = [json.loads(line) for line in tail if line.strip()]
        return {"items": records[-100:]}
    except (OSError, json.JSONDecodeError):
        return {"items": [], "warning": "Activity history could not be read."}


@app.get("/api/roots")
def approved_roots_api(request: Request) -> dict[str, list[str]]:
    _check_local_request(request)
    return {"locations": list(roots_for())}


@app.get("/api/applications")
def applications(request: Request):
    _check_local_request(request)
    return {"applications": list_applications()}


@app.post("/api/ollama")
def local_suggestions(body: OllamaRequest, request: Request):
    _check_local_request(request)
    try:
        allowed = [{key: row.get(key) for key in ("category", "size", "reason")} for row in body.metadata[:100]]
        return {"text": ollama_suggest(allowed, body.endpoint, body.model, body.enabled)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _ensure_plan_folder(destination: str, roots: dict[str, Path], repo: Path) -> tuple[Path, bool]:
    target = Path(destination)
    if not target.is_absolute() or ".." in target.parts or not safe_folder_name(target.name):
        raise OperationError("Plan destination must be a safe absolute file path")
    parent = target.parent
    downloads = roots["Downloads"]
    category = parent.name
    if category not in {"Installers", "Archives", "Documents"} or parent.parent != downloads:
        raise OperationError("Plan destinations must be directly under an approved Downloads category folder")
    if parent.exists():
        checked = validate_path(parent, roots, repo=repo)
        if not checked.is_dir(): raise OperationError("Plan destination parent is not a folder")
        return checked, False
    # The only missing path permitted is the single category folder under Downloads.
    validate_path(parent, roots, must_exist=False, repo=repo)
    parent.mkdir(exist_ok=False)
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": uuid.uuid4().hex,
              "action": "create-folder", "destination": str(parent), "expected": identity(parent), "success": True}
    try:
        append_log(LOG_PATH, record)
    except OSError as log_error:
        try:
            parent.rmdir()
        except OSError as rollback_error:
            raise OperationError(f"Plan folder was created but logging and cleanup failed: {rollback_error}") from log_error
        raise OperationError(f"Plan folder creation was rolled back because logging failed: {log_error}") from log_error
    return parent, True


@app.post("/api/actions")
def perform_action(body: ActionRequest, request: Request) -> dict[str, Any]:
    _check_local_request(request)
    roots = roots_for()
    repo = BASE_DIR.resolve()
    try:
        if body.action == "undo":
            return undo_latest(LOG_PATH, roots, repo)
        if body.action == "create-folder":
            if not body.destination or not safe_folder_name(body.name or ""):
                raise OperationError("Choose a single safe folder name")
            parent_path = roots.get(body.destination, body.destination)
            parent = validate_path(parent_path, roots, repo=repo)
            similar = find_similar_folder(parent, body.name)
            if similar:
                raise OperationError(f"A similar folder already exists: {similar}")
            target = parent / body.name
            target.mkdir(exist_ok=False)
            record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": uuid.uuid4().hex, "action": "create-folder", "destination": str(target), "expected": identity(target), "success": True}
            try:
                append_log(LOG_PATH, record)
            except OSError as log_error:
                try:
                    target.rmdir()
                except OSError as rollback_error:
                    raise OperationError(f"Folder was created but logging failed; cleanup also failed: {rollback_error}") from log_error
                raise OperationError(f"Folder creation was rolled back because logging failed: {log_error}") from log_error
            return {"results": [record]}
        if body.action == "organize":
            if not body.job_id or not body.source or not body.category:
                raise OperationError("Choose a scanned file and organizer destination")
            job = _jobs.get(body.job_id)
            if not job or job.get("status") != "complete":
                raise OperationError("A completed scan is required before organizing files")
            scanned = {item["path"]: item for item in job.get("result", {}).get("files", [])}
            row = scanned.get(body.source)
            if row is None:
                raise OperationError("Source was not part of the completed scan")
            search_locations = (job or {}).get("locations") or [row.get("location")]
            search_roots = {name: roots[name] for name in search_locations if name in roots}
            destination = move_to_category(
                body.source, body.category, body.subcategory or "", row.get("location"),
                row["identity"], roots, repo, search_roots,
            )
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation_id": uuid.uuid4().hex,
                "action": "move",
                "source": body.source,
                "destination": destination,
                "expected": identity(Path(destination)),
                "success": True,
            }
            try:
                append_log(LOG_PATH, record)
            except OSError as log_error:
                try:
                    exclusive_rename(Path(destination), Path(body.source))
                except OSError as rollback_error:
                    raise OperationError(f"File moved but logging and rollback failed: {rollback_error}") from log_error
                raise OperationError(f"Move rolled back because logging failed: {log_error}") from log_error
            return {"results": [record]}
        if body.action == "apply-plan":
            job = _jobs.get(body.job_id or "")
            if not job or job.get("status") != "complete":
                raise OperationError("A completed scan is required before applying a plan")
            scanned = {item["path"]: item for item in (job or {}).get("result", {}).get("files", [])}
            outcomes = []
            for proposal in body.plan:
                try:
                    source_path = proposal.get("source", "")
                    destination_path = proposal.get("destination", "")
                    row = scanned.get(source_path)
                    if row is None: raise OperationError("Source was not part of this scan")
                    if not destination_path: raise OperationError("Destination is required")
                    current = validate_path(row["path"], roots, repo=repo)
                    if identity(current) != row["identity"]: raise OperationError("Source changed since scan/review")
                    parent, _created = _ensure_plan_folder(destination_path, roots, repo)
                    target = parent / Path(destination_path).name
                    destination = apply_move(row["path"], str(target), row["identity"], roots, repo)
                    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": uuid.uuid4().hex, "action": "move", "source": row["path"], "destination": destination, "expected": identity(Path(destination)), "success": True}
                    try:
                        append_log(LOG_PATH, record)
                    except OSError as log_error:
                        try:
                            exclusive_rename(Path(destination), Path(row["path"]))
                        except OSError as rollback_error:
                            raise OperationError(f"File moved to {destination}, but logging and rollback failed: {rollback_error}") from log_error
                        raise OperationError(f"Move was rolled back because logging failed: {log_error}") from log_error
                    outcomes.append(record)
                except DestinationExists as exc:
                    outcomes.append({"source": proposal.get("source"), "success": False, "collision": True, "destination": str(exc).split(': ', 1)[-1], "message": str(exc)})
                except (OperationError, OSError) as exc: outcomes.append({"source": proposal.get("source"), "success": False, "message": str(exc)})
            return {"results": outcomes}
        selected_sources = body.sources or ([body.source] if body.source else [])
        if body.action not in {"move", "trash", "reveal", "open"} or not body.job_id or not selected_sources:
            raise OperationError("Unsupported or incomplete action")
        job = _jobs.get(body.job_id)
        if not job or job.get("status") != "complete":
            raise OperationError("A completed scan is required before this action")
        scan_result = job.get("result", {})
        scanned = {item["path"]: item for item in scan_result.get("files", [])}
        scanned_folders = {item["path"]: item for item in scan_result.get("folders", [])}
        results = []
        for raw_source in selected_sources:
            try:
                row = scanned.get(raw_source)
                source = validate_path(raw_source, roots, repo=repo)
                if body.action == "reveal":
                    scanned_item = scanned_folders.get(raw_source) if source.is_dir() else row
                    if scanned_item is None:
                        raise OperationError("Only scanned files or folders can be revealed")
                    if identity(source) != scanned_item.get("identity"):
                        raise OperationError("Source changed since scan/review")
                    result = reveal(source); results.append(result); continue
                if body.action == "open":
                    if not source.is_file(): raise OperationError("Only regular files can be opened")
                    if row is None: raise OperationError("Only scanned files can be opened")
                    if identity(source) != row.get("identity"):
                        raise OperationError("Source changed since scan/review")
                    result = open_file(source); results.append(result); continue
                if row is None: raise OperationError("Source was not part of this scan")
                expected = row.get("identity")
                if identity(source) != expected: raise OperationError("Source changed since scan/review")
                if body.action == "trash":
                    intent = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": uuid.uuid4().hex,
                              "action": "trash-intent", "source": str(source), "success": False,
                              "message": "Trash operation started; check Finder if no completion record follows."}
                    append_log(LOG_PATH, intent)
                    result = trash(source)
                    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": intent["operation_id"], "action": "trash", "source": str(source), "success": True, "message": result["message"]}
                else:
                    if not body.destination: raise OperationError("Destination folder is required")
                    destination = move_into_folder(source, body.destination, expected, roots, repo, body.alternate_name)
                    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "operation_id": uuid.uuid4().hex, "action": "move", "source": str(source), "destination": destination, "expected": identity(Path(destination)), "success": True}
                try:
                    append_log(LOG_PATH, record)
                except OSError as log_error:
                    if body.action == "move":
                        try:
                            exclusive_rename(Path(destination), source)
                        except OSError as rollback_error:
                            raise OperationError(f"File moved to {destination}, but logging and rollback failed: {rollback_error}") from log_error
                        raise OperationError(f"Move was rolled back because logging failed: {log_error}") from log_error
                    raise OperationError(f"Action completed but logging failed: {log_error}") from log_error
                results.append(record)
            except DestinationExists as exc:
                results.append({"source": raw_source, "success": False, "collision": True, "destination": str(exc).split(': ', 1)[-1], "message": str(exc)})
            except (OperationError, OSError) as exc:
                results.append({"source": raw_source, "success": False, "message": str(exc)})
        return {"results": results}
    except (OperationError, OSError) as exc:
        return {"results": [{"success": False, "message": str(exc)}]}


LOG_PATH = Path.home() / ".tidylocal" / "activity.jsonl"

@app.post("/api/scan")
def start_scan(body: ScanRequest, request: Request) -> dict[str, str]:
    _check_local_request(request)
    if not body.locations or len(set(body.locations)) != len(body.locations) or any(item not in LOCATION_NAMES for item in body.locations):
        raise HTTPException(status_code=400, detail="Choose one or more approved locations")
    return {"job_id": _start_job(body.locations)}


@app.get("/api/scan/{job_id}")
def scan_status(job_id: str, request: Request) -> dict[str, Any]:
    _check_local_request(request)
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown scan")
    return {key: value for key, value in job.items() if key != "cancel"}


@app.post("/api/scan/{job_id}/cancel")
def cancel_scan(job_id: str, request: Request) -> dict[str, str]:
    _check_local_request(request)
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown scan")
    job["cancel"].set()
    return {"status": "cancelling"}
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/api/disk")
def get_disk_metrics(request: Request) -> dict[str, Any]:
    _check_local_request(request)
    return disk_metrics()


@app.get("/api/samples")
def get_samples(request: Request) -> dict[str, Any]:
    _check_local_request(request)
    return {"files": SAMPLE_FILES, "label": "Generated sample data — not a scan of your files"}


@app.post("/api/demo")
def start_demo(request: Request) -> dict[str, str]:
    _check_local_request(request)
    folder = create_demo_files()
    return {"status": "created", "location": str(folder), "message": "Demo placeholders created in a temporary folder."}


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse((BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8"))


def main() -> None:
    import threading
    import webbrowser
    import uvicorn

    host, port = "127.0.0.1", int(os.environ.get("TIDYLOCAL_PORT", "8000"))
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_config=None)


if __name__ == "__main__":
    main()
