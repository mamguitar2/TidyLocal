# Contributing

Thanks for helping make TidyLocal safer and easier to use. Keep changes focused, preserve existing behavior unless the issue explicitly asks for a change, and avoid adding abstractions or dependencies without a concrete need.

## Set up and verify

Use Python 3.10 or newer. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m pytest --cov --cov-report=term-missing
```

The filesystem tests must use `tmp_path` or another temporary directory. Never run tests or manual checks against a real Downloads, Desktop, Documents, or home directory. Mock Trash and platform-specific operations; do not use real user files as fixtures.

## Safety expectations

- Keep scanning and previews read-only.
- Validate paths against approved roots and reject symlinks/path escapes.
- Use exclusive no-overwrite moves; preserve sources on failure and clean up only empty folders created by the failed operation.
- Recheck saved file identity before a mutation. Keep failures visible and fail closed when a safe OS primitive is unavailable.
- Do not add permanent deletion, upload file contents, or make AI output authorize a filesystem action.
- Avoid committing secrets, personal paths, real filenames, or file contents in fixtures, logs, and screenshots.

## Dependencies and pull requests

Runtime and development requirements are bounded version ranges, not a fully pinned lockfile. Keep runtime dependencies in `requirements.txt` and tooling/test-only dependencies in `requirements-dev.txt`; explain new dependencies and verify a fresh install where practical.

Open a pull request with a concise summary, the tests/checks you ran, and any compatibility or safety implications. Update user-facing documentation when setup, behavior, or limitations change. Do not include generated logs, virtual environments, or unrelated formatting changes.
