from sa_cli.instruments import Instrument
from sa_cli.measurements import common, bandwidth
import argparse
import csv
from unittest.mock import Mock

import pytest

from sa_cli import config
from sa_cli.cli import main, parser, commands
from sa_cli import measurements
from sa_cli import report
from tests.fakes import build_instrument


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e999", "1e308G"])
def test_nonfinite_cli_values_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError):
        parser._parse_number(value)


@pytest.mark.parametrize("points", [[], [0], [-1], [True], ["100"], [float("nan")],
                                         [float("inf")], [100, 100.0], "100"])
def test_invalid_config_points_rejected(monkeypatch, points):
    monkeypatch.setattr(config, "cal_points", lambda: {"rbw": points})
    with pytest.raises(ValueError):
        config.cal_point_defaults("rbw", [100])


@pytest.mark.parametrize("value", ["nan", "inf", "1e999"])
def test_nonfinite_instrument_readings_rejected(value):
    instrument, _, _ = build_instrument("spectrum_analyzer.json",
                                       {":CALCulate:MARKer1:Y?": value})
    with pytest.raises(ValueError):
        instrument.marker_read_y()


def test_opc_deadline_caps_io_and_restores_timeout(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(common.time, "monotonic", lambda: now[0])
    instrument = Mock()
    instrument.instr.timeout = 60000
    observed = []

    def query():
        observed.append(instrument.instr.timeout)
        now[0] += 1
        return 0

    instrument.opc.side_effect = query
    with pytest.raises(TimeoutError):
        common._wait_opc(instrument, timeout_s=1)
    assert observed == [1000]
    assert instrument.instr.timeout == 60000


def test_sweep_failure_stops_before_read_and_restores_mode(monkeypatch):
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: None)
    sg, sa = Mock(), Mock()
    sa.instr.timeout = 60000
    sg.instr.timeout = 15000
    sg.opc.return_value = 1
    sa.opc.side_effect = OSError("disconnected")
    with pytest.raises(RuntimeError, match="OPC"):
        bandwidth._find_edge(sg, sa, 50e6, 100, 1, "right")
    sa.marker_read_y.assert_not_called()
    sa.set_sweep_cont.assert_called_once()
    assert sa.instr.timeout == 60000


@pytest.mark.parametrize("delta,phase", [(10, "粗搜"), (-10, "精调")])
def test_nonconvergent_edge_is_rejected(monkeypatch, delta, phase):
    monkeypatch.setattr(common, "_wait_opc", lambda *a, **k: True)
    monkeypatch.setattr(common, "_wait_sweep", lambda *a, **k: True)
    sg, sa = Mock(), Mock()
    sa.marker_read_y.return_value = delta
    with pytest.raises(RuntimeError, match=phase):
        bandwidth._find_edge(sg, sa, 50e6, 100, 1, "right")


@pytest.mark.parametrize("calibrate", [measurements.cal_linear_scale, measurements.cal_log_scale])
def test_peak_alignment_failure_stops_measurement(monkeypatch, calibrate):
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: None)
    monkeypatch.setattr(common, "_wait_opc", lambda *a, **k: True)
    monkeypatch.setattr(common, "_wait_sweep", lambda *a, **k: True)
    sg, sa = Mock(), Mock()
    sg.dry_run = False
    sa.marker_read_y.return_value = -10
    with pytest.raises(RuntimeError, match="未收敛"):
        calibrate(sa, sg, points=[4])
    assert sa.marker_read_y.call_count == 6


def test_timeout_preserves_completed_points():
    def measure(point):
        if point == 200:
            raise TimeoutError("OPC")
        return 1
    with pytest.raises(measurements.MeasurementError) as error:
        common._collect_points([100, 200], measure, "rbw")
    assert error.value.partial_results == {100: 1}


def test_csv_preserves_partial_and_summary(tmp_path):
    path = tmp_path / "partial.csv"
    report.export_results(path, {"command": "rbw", "partial": True,
                                "carrier_hz": 50e6, "max_abs_delta_db": 0.2,
                                "results": [{"rbw_hz": 100}]})
    with path.open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["partial"] == "True"
    assert row["carrier_hz"] == "50000000.0"
    assert row["max_abs_delta_db"] == "0.2"


@pytest.mark.parametrize("extension,data", [("json", {"bad": object()}),
                                          ("csv", {"results": [{"a": 1}, {"b": 2}]})])
def test_failed_export_preserves_old_file(tmp_path, extension, data):
    path = tmp_path / ("result." + extension)
    path.write_text("previous", encoding="utf-8")
    with pytest.raises((TypeError, ValueError)):
        report.export_results(path, data)
    assert path.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("argv", [["rbw", "--output", "bad.txt"],
                                   ["rbw", "-b", "100", "100"]])
def test_invalid_options_do_not_connect(monkeypatch, argv):
    session = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(commands, "visa_session", session)
    assert main.main(argv) == 1
    session.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_dry_run_does_not_change_subsequent_wait_strategy(monkeypatch, fail):
    from sa_cli.instruments import visa_session
    from tests.fakes import FakeResourceManager
    calls = []
    def dispatch(args, *, sleep=None):
        with visa_session("sg", "sa", rm=FakeResourceManager(),
                          dry_run=args.dry_run, sleep=sleep) as (sg, sa):
            sg.sleep(2)
            sa.sleep(3)
            if args.dry_run and fail:
                raise RuntimeError("failure")
        return 0
    monkeypatch.setattr(commands, "_dispatch", dispatch)
    assert main.main(["rbw", "--dry-run"], sleep=calls.append) == int(fail)
    assert calls == []
    assert main.main(["rbw"], sleep=calls.append) == 0
    assert calls == [2, 3]
