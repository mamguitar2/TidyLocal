# Contributing

Thanks for helping make TidyLocal safer and easier to use. Keep changes focused, preserve existing behavior unless an issue explicitly requests a behavior change, and prefer the smallest design that solves the actual problem. Avoid new abstractions, dependencies, or configuration knobs without a concrete use case.

## Set up the project

TidyLocal targets macOS and supports Python 3.10 or newer. From the repository root, create a virtual environment and install the committed development lock:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
```

Run the documented test target with `make test`. Before opening a pull request, run `make check` for lint, formatting, and type checking, then `make test-coverage` to see the coverage report. CI runs these checks as explicit commands so each result is visible in the job. If you need to override the interpreter, use `make test PYTHON=/path/to/python`.

`pyproject.toml` is the canonical dependency manifest: runtime libraries belong in `[project].dependencies`, while test and contributor tools belong in `[project.optional-dependencies].dev`. The committed `.lock` files pin transitive versions and contain markers for supported Python versions. When dependencies change, install uv (`brew install uv` on macOS) and regenerate both locks with the `uv pip compile --universal --python-version 3.10 ...` commands in the README. Review the full lock diff and test a fresh install on the lowest supported Python version; the lock must not select packages that dropped Python 3.10 support.

## Project map

`app.py` exposes the local FastAPI routes and coordinates scan-gated operations. `scanner.py` contains read-only traversal and duplicate detection. `organizer.py` creates conservative local suggestions, and `operations.py` / `undo.py` perform validated filesystem operations. `templates/` and `static/` contain the browser interface. Tests live under `tests/` and use pytest.

## Code style and test expectations

Follow the Ruff configuration in `pyproject.toml`; do not disable a rule just to make a check green. Keep types meaningful at operation and data boundaries. Add a focused regression test for a bug or safety change, not a placeholder assertion. Run the narrow test while iterating, then run the complete `make test` and `make check` before submitting. Coverage is reported in CI; it is a signal to test important behavior, not a reason to inflate counts with low-value tests.

All filesystem fixtures and destructive-operation mocks must use `tmp_path` or another isolated temporary directory. Never run tests or manual checks against a real Downloads, Desktop, Documents, or home directory. Mock Trash, `open`, Spotlight, and other platform-specific integrations. Do not use real user files as fixtures. Tests must not require a network service or make changes outside their temporary sandbox.

## Safety expectations

- Keep scanning, previews, and suggestion generation read-only.
- Validate paths against approved roots, reject symlinks and path escapes, and recheck saved file identity before each mutation.
- Use exclusive no-overwrite moves. Preserve the source on failure, and clean up only empty directories created by the failed operation.
- Keep failure messages visible and fail closed when a safe operating-system primitive is unavailable.
- Do not add permanent deletion, upload file contents, or let AI output authorize a filesystem action.
- Avoid committing secrets, personal paths, real filenames, private file contents, generated logs, or screenshots containing personal data.

## Pull requests

Open a pull request with a concise problem statement, implementation summary, commands run, and any compatibility or safety implications. Update the README when setup, user-visible behavior, privacy, or limitations change. Keep unrelated formatting and generated artifacts out of the change. Before submission, inspect `git diff --check`, review staged paths, and make sure no secret or machine-specific path is included.
