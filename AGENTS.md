# Repository Guidelines

## Project Structure & Module Organization

Production code lives in `src/sa_cli/`:

- `cli/main.py`, `parser.py`, and `commands.py`: entry point, arguments, command registration, and result conversion.
- `instruments/base.py`, `devices.py`, and `session.py`: SCPI actions, device types, and VISA lifecycle.
- `measurements/`: separate bandwidth, RBW-switching, phase-noise, sweep-width, and scale algorithms; `common.py` handles synchronization and progress.
- `data/`: two SCPI JSON definitions and `cal_points.json`.
- `config.py`, `validation.py`, `errors.py`, and `report.py`: configuration, validation, exceptions, and exports.

Keep root `main.py` as a compatibility wrapper. Use package imports such as `from sa_cli.instruments import visa_session`; do not restore top-level implementation modules.

## Build, Test, and Development Commands

Run from the repository root:

- `python -m venv .venv`, then `.\.venv\Scripts\Activate.ps1`: create and activate the PowerShell environment.
- `python -m pip install -e ".[dev]"`: install the package and pytest before development; tests rely on the installed package, not path injection.
- `python -m sa_cli --help`: inspect commands; `sa-cli` and `python main.py` remain supported.
- `sa-cli rbw -b 100 1000 --dry-run`: preview without hardware.
- `python -m pytest`: run all tests.
- `python -m pytest tests/integration -q`: check CLI, exports, reliability, and package entry points.
- `python -m pip wheel . --no-deps -w dist`: build the wheel.

## Coding Style & Architecture

Use four-space indentation, `snake_case` functions, `PascalCase` classes, and uppercase constants. Preserve Python 3.8 compatibility and Chinese documentation/help conventions. No formatter is configured.

Keep parsing in CLI modules, calculations in measurements, transport in instruments, and serialization in `report.py`. Reuse `validation.py` and preserve `MeasurementError.partial_results`. Keep requirements files aligned with `pyproject.toml`.

## Testing Guidelines

Use pytest `test_*.py` files and `test_*` functions. Put algorithm/device tests in `tests/unit/`, workflow tests in `tests/integration/`, reusable fakes in `tests/fakes.py`, and fixtures in `tests/conftest.py`.

Mock hardware; cover convergence, timeouts, invalid values, partial exports, and cleanup. Run the full suite for code changes. No coverage threshold is configured. For packaging changes, install the wheel separately and verify commands and bundled JSON outside the repository.

## Configuration & Instrument Safety

Use `SA_CLI_SG_ADDR`, `SA_CLI_SA_ADDR`, and `SA_CLI_DATA_DIR` for overrides. Load bundled defaults through `importlib.resources`; preserve package-data declarations when changing JSON assets.

Wrap measurement calls in `visa_session`, which owns RF shutdown and resource release. Inject waits through `sleep`; never modify global sleep state. Preserve sweep synchronization and original exceptions during cleanup.

## Commit & Pull Request Guidelines

Use Chinese summaries with prefixes `feat(cli):`, `fix:`, or `refactor:`. PRs should explain changes and validation. Update `README.md` for changed commands, defaults, or installation behavior.
