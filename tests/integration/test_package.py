"""包入口、资源和会话生命周期回归测试。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from sa_cli import config
from sa_cli.cli.main import main
from sa_cli.errors import MeasurementError
from sa_cli.instruments import session


def test_legacy_and_package_entrypoints_match(tmp_path):
    legacy = Path(__file__).resolve().parents[2] / "main.py"
    outputs = []
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("SA_CLI_DATA_DIR", None)
    for index, entry in enumerate(([str(legacy)], ["-m", "sa_cli"])):
        output = tmp_path / f"result{index}.json"
        result = subprocess.run(
            [sys.executable, *entry, "rbw-switch", "-b", "100", "1000",
             "--dry-run", "--output", str(output)],
            cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(json.loads(output.read_text(encoding="utf-8")))
    assert outputs[0] == outputs[1]
    assert len(outputs[0]["results"]) == 2


def test_missing_explicit_data_directory_does_not_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError):
        with config.open_data("spectrum_analyzer.json"):
            pass


def test_measurement_and_cleanup_failure_keep_original_error(monkeypatch):
    sig, spec, rm = Mock(), Mock(), Mock()
    sig.rf_off.side_effect = OSError("RF failure")
    monkeypatch.setattr(session, "SignalGenerator", Mock(return_value=sig))
    monkeypatch.setattr(session, "SpectrumAnalyzer", Mock(return_value=spec))
    failure = MeasurementError("measurement failed", {100: 0.1})
    with pytest.raises(MeasurementError) as caught:
        with session.visa_session("sg", "sa", rm=rm):
            raise failure
    assert caught.value is failure
    assert caught.value.partial_results == {100: 0.1}
    sig.rf_off.assert_called_once()
    sig.close.assert_called_once()
    spec.close.assert_called_once()
    rm.close.assert_called_once()


def test_connection_failure_still_shuts_down_signal_generator(monkeypatch):
    sig, rm = Mock(), Mock()
    monkeypatch.setattr(session, "SignalGenerator", Mock(return_value=sig))
    monkeypatch.setattr(session, "SpectrumAnalyzer", Mock(side_effect=ConnectionError("SA")))
    with pytest.raises(ConnectionError):
        with session.visa_session("sg", "sa", rm=rm):
            pytest.fail("session should not start")
    sig.rf_off.assert_called_once()
    sig.close.assert_called_once()
    rm.close.assert_called_once()


def test_cli_cleans_up_once_after_multiple_points(monkeypatch):
    from tests.integration.test_main import _FakeRM
    rm = _FakeRM()
    monkeypatch.setattr(session.pyvisa, "ResourceManager", lambda: rm)
    assert main(["rbw-switch", "-b", "100", "1000"], sleep=lambda _: None) == 0
    assert rm.resource.writes.count(":OUTPut:STATe OFF") == 1
    assert rm.closed
