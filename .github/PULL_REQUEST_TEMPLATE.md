## Summary

- What changed and why?

## Verification

- [ ] `.venv/bin/python -m pytest --cov --cov-report=term-missing`
- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `mypy`

## Safety and compatibility

- [ ] File-operation tests use temporary directories only; I did not test against personal files.
- [ ] No unintended deletion, overwrite, or path escape is possible.
- [ ] Documentation and dependency changes are included where needed.
- [ ] No secrets, personal paths, or private file data are included.
