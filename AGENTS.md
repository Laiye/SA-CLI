# Repository Guidelines

## Project Structure & Module Organization

SA-CLI controls spectrum analyzers and signal generators through PyVISA. Source modules live at the repository root:

- `main.py`: argument parsing, command dispatch, and result export orchestration.
- `instruments.py`: JSON-driven SCPI methods and VISA session lifecycle.
- `measurements.py`: calibration algorithms and instrument synchronization.
- `config.py`: instrument addresses and data-directory resolution.
- `report.py`: JSON and CSV exports.

`spectrum_analyzer.json` and `signal_generator.json` define instrument actions; `cal_points.json` supplies default calibration points. Tests live in `tests/`, with shared fake VISA resources in `tests/conftest.py`. Packaging and pytest settings are in `pyproject.toml`.

## Build, Test, and Development Commands

Run commands from the repository root with Python 3.8+:

- `python -m venv .venv`: create an isolated environment; activate it with `.\.venv\Scripts\Activate.ps1` on PowerShell.
- `python -m pip install -e ".[dev]"`: install the editable CLI and pytest dependencies.
- `sa-cli --help` or `python main.py --help`: inspect available commands.
- `sa-cli rbw --rbw-list 100 1000 --dry-run`: preview SCPI commands without connecting to instruments.
- `python -m pytest`: run the full test suite.
- `python -m pytest tests/test_main.py -q`: run focused CLI tests.
- `python -m pip wheel . --no-deps -w dist`: build a wheel using the setuptools backend.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, `PascalCase` classes, and uppercase constants. Preserve Python 3.8 compatibility and existing Chinese documentation and CLI help conventions. Keep measurement logic separate from CLI parsing and instrument transport. Define new SCPI actions in the corresponding JSON file. No formatter or linter is configured; follow surrounding code. Keep requirements files aligned with `pyproject.toml`, the dependency source of truth.

## Testing Guidelines

Use pytest with `test_*.py` files and `test_*` functions. Reuse fake resources and mock hardware interaction; unit tests require no physical instruments. Cover changed calculations, argument validation, SCPI sequences, and failure cleanup as applicable. Run the full suite before submitting. No numerical coverage threshold is configured.

## Commit & Pull Request Guidelines

Recent commits use `feat: ...` and `feat(cli): ...` with concise Chinese summaries. Follow that type-and-optional-scope pattern. PRs should describe behavior changes, relevant issues, test commands and results, and representative CLI output when useful. Update `README.md` for changed commands or defaults.

## Configuration & Instrument Safety

Use `SA_CLI_SG_ADDR`, `SA_CLI_SA_ADDR`, and `SA_CLI_DATA_DIR` for local configuration. Non-editable installations need access to the JSON data files through the data directory. Preserve `visa_session` cleanup, including RF shutdown on failure, and existing sweep synchronization.
