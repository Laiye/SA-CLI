# Repository Guidelines

## Project Structure & Module Organization

SA-CLI uses a `src/sa_cli/` package layout:

- `cli/`: entry point, argument parsing, command dispatch, and result conversion.
- `instruments/`: JSON-driven SCPI methods, device classes, and VISA sessions.
- `measurements/`: bandwidth, RBW switching, phase noise, sweep width, and scale algorithms; `common.py` holds synchronization and progress helpers.
- `data/`: bundled SCPI definitions and default calibration points.
- `config.py`, `validation.py`, `errors.py`, and `report.py`: configuration, validation, measurement errors, and exports.

Tests are organized into `tests/unit/` and `tests/integration/`. Reusable VISA fakes live in `tests/fakes.py`; fixtures live in `tests/conftest.py`. Root `main.py` only forwards the legacy entry point.

## Build, Test, and Development Commands

Use Python 3.8+ from the repository root:

- `python -m venv .venv`: create an isolated environment; activate it with `.\.venv\Scripts\Activate.ps1` on PowerShell.
- `python -m pip install -e ".[dev]"`: install the editable CLI and pytest dependencies.
- `sa-cli --help` or `python -m sa_cli --help`: inspect available commands.
- `sa-cli rbw --rbw-list 100 1000 --dry-run`: preview SCPI commands without connecting to instruments.
- `python -m pytest`: run the full test suite.
- `python -m pytest tests/integration/test_main.py -q`: run focused CLI tests.
- `python -m pip wheel . --no-deps -w dist`: build a wheel using the setuptools backend.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants. Preserve Python 3.8 compatibility and existing Chinese documentation and CLI help conventions. Keep measurement logic separate from CLI parsing and instrument transport. Define new SCPI actions in `src/sa_cli/data/`. Keep package imports explicit. Follow surrounding style; no formatter is configured. Keep requirements aligned with `pyproject.toml`.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Reuse fake resources and mock hardware interaction; unit tests require no physical instruments. Cover changed calculations, argument validation, SCPI sequences, and failure cleanup as applicable. Run the full suite before submitting. No numerical coverage threshold is configured.

## Commit & Pull Request Guidelines

Recent commits use `feat: ...` and `feat(cli): ...` with concise Chinese summaries. Follow that type-and-optional-scope pattern. PRs should describe behavior changes, relevant issues, and validation results. Update `README.md` for changed commands or defaults.

## Configuration & Instrument Safety

Use `SA_CLI_SG_ADDR`, `SA_CLI_SA_ADDR`, and `SA_CLI_DATA_DIR` for local configuration. Packaged defaults load through `importlib.resources`; wheel installations require no external data directory. Use `visa_session` for all measurement calls: it owns RF shutdown and resource cleanup. Inject waits through its `sleep` argument; never modify global sleep state. Preserve sweep synchronization.
