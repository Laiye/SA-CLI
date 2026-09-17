"""结果导出与 CLI 入口的测试。"""

from sa_cli.instruments import Instrument
from sa_cli.measurements import common, bandwidth
from sa_cli.instruments import session

import csv
import json

import pytest

from sa_cli import measurements
from sa_cli.report import export_results


def test_export_json(tmp_path):
    path = tmp_path / "out.json"
    export_results(str(path), {
        "command": "rbw",
        "results": [{"rbw_hz": 100, "measured_hz": 100.3}],
    })
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["results"][0]["measured_hz"] == 100.3


def test_export_csv(tmp_path):
    path = tmp_path / "out.csv"
    export_results(str(path), {
        "command": "rbw",
        "results": [
            {"rbw_hz": 100, "measured_hz": 100.3},
            {"rbw_hz": 1000, "measured_hz": 998.5},
        ],
    })
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["rbw_hz"] == "100"
    assert rows[1]["measured_hz"] == "998.5"


def test_export_unsupported_format_raises(tmp_path):
    path = tmp_path / "out.txt"
    with pytest.raises(ValueError):
        export_results(str(path), {"results": [{"a": 1}]})


# ---------- CLI 入口 ----------

class _FakeResource:
    def __init__(self):
        self.timeout = 5000
        self.writes = []
        self.queries = []
        self.cleared = False

    def write(self, command):
        self.writes.append(command)

    def clear(self):
        self.cleared = True

    def query(self, command):
        self.queries.append(command)
        if "MARKer1:Y?" in command or "MARKer1:X?" in command:
            return "0.0"
        if command == "*OPC?":
            return "1"
        return "OK"

    def close(self):
        pass


class _FakeRM:
    def __init__(self):
        self.resource = _FakeResource()
        self.closed = False

    def open_resource(self, address):
        return self.resource

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: None)


def _patch_rm(monkeypatch):
    from sa_cli import instruments
    monkeypatch.setattr(session.pyvisa, "ResourceManager", lambda: _FakeRM())


def test_main_rbw_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "r.csv"
    rc = main.main(["rbw", "--carrier", "50e6", "--rbw-list", "100",
                    "--output", str(out)])
    assert rc == 0
    assert out.exists()
    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and "measured_hz" in rows[0]


def test_main_bw60_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "b.json"
    rc = main.main(["bw60", "--carrier", "50e6", "--rbw-list", "1000",
                    "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["results"][0]["bw60_hz"] is not None


def test_main_phase_noise_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    rc = main.main(["phase-noise", "-o", "100", "--output", str(tmp_path / "p.json")])
    assert rc == 0


def test_main_sweep_width_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "s.json"
    rc = main.main(["sweep-width", "-s", "0.5e9", "1e9", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["command"] == "sweep-width"
    assert len(data["results"]) == 2
    assert "delta" in data["results"][0]


def test_main_sweep_width_sw_alias_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    rc = main.main(["sw", "-s", "1.6e9", "2e9", "--output", str(tmp_path / "s2.json")])
    assert rc == 0


def test_main_no_command_prints_help(capsys):
    from sa_cli.cli import main, parser, commands
    rc = main.main([])
    assert rc == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_main_returns_error_on_exception(monkeypatch, caplog):
    import logging

    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(commands, "cal_rbw", boom)
    with caplog.at_level(logging.ERROR):
        rc = main.main(["rbw", "--rbw-list", "100"])
    assert rc == 1
    assert any("程序异常" in record.message for record in caplog.records)


def test_main_verbose_flag_after_subcommand(monkeypatch):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    rc = main.main(["rbw", "--rbw-list", "100", "--verbose"])
    assert rc == 0


def test_main_cli_overrides_config_defaults(monkeypatch, tmp_path):
    """CLI 传入的校准点优先于 cal_points.json 默认值。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "o.json"
    rc = main.main(["rbw", "--rbw-list", "100", "200", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 2


def test_main_rbw_uses_config_default_points(monkeypatch, tmp_path):
    """不传校准点时，使用 cal_points.json 中的默认校准点（rbw 共 8 个）。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "o.json"
    rc = main.main(["rbw", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 8


def test_main_phase_noise_multi_offset(monkeypatch, tmp_path):
    """相位噪声支持多频偏，结果逐条导出。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "p.json"
    rc = main.main(["phase-noise", "-o", "100", "1000", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["results"]) == 2
    assert data["results"][0]["offset_hz"] == 100
    assert data["results"][1]["offset_hz"] == 1000


def test_main_log_scale_end_to_end(monkeypatch, tmp_path):
    """对数刻度 CLI：1 dB/div 模式导出 9 个校准点。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "l.json"
    rc = main.main(["log-scale", "--scale", "1", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["command"] == "log-scale"
    assert len(data["results"]) == 9


def test_main_log_scale_10db_mode(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "l10.json"
    rc = main.main(["log", "--scale", "10", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["scale_db_per_div"] == 10
    assert len(data["results"]) == 8


def test_main_linear_scale_end_to_end(monkeypatch, tmp_path):
    """线性刻度 CLI：默认校准点 4~20 dB 共 5 个。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    original_query = _FakeResource.query
    monkeypatch.setattr(_FakeResource, "query", lambda self, cmd:
                        "0.2236" if "MARKer1:Y?" in cmd else original_query(self, cmd))
    out = tmp_path / "ln.json"
    rc = main.main(["linear-scale", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["command"] == "linear-scale"
    assert len(data["results"]) == 5
    assert "theoretical_mv" in data["results"][0]


# ---------- CLI 参数校验 ----------

def _parse(command, *args):
    from sa_cli.cli import main, parser, commands
    return parser.build_parser().parse_args([command, *args])


def test_parser_rejects_zero_offset():
    with pytest.raises(SystemExit):
        _parse("phase-noise", "--offset", "0")


def test_parser_rejects_negative_carrier():
    with pytest.raises(SystemExit):
        _parse("rbw", "--carrier", "-1e6")


def test_parser_rejects_negative_rbw_in_list():
    with pytest.raises(SystemExit):
        _parse("rbw", "--rbw-list", "100", "-100")


def test_parser_rejects_negative_settle():
    with pytest.raises(SystemExit):
        _parse("linear-scale", "--settle", "-1")


def test_parser_allows_negative_ref_level():
    """参考电平/信号源电平可为负（dBm），不应被校验拒绝。"""
    args = _parse("phase-noise", "--offset", "100", "--ref-level", "-10")
    assert args.ref_level == -10
    args = _parse("sweep-width", "-s", "1e9", "--sg-power", "-30")
    assert args.sg_power == -30


def test_parser_accepts_zero_align_threshold():
    """align-threshold=0 合法（文档化：关闭对中预处理）。"""
    args = _parse("sweep-width", "-s", "1e9", "--align-threshold", "0")
    assert args.align_threshold == 0.0


# ---------- dry-run ----------

def test_main_dry_run_prints_scpi_without_visa(monkeypatch, caplog):
    """dry-run 不创建 VISA ResourceManager，完整跑流程并打印 SCPI 序列。"""
    import logging

    from sa_cli.cli import main, parser, commands
    from sa_cli import instruments
    monkeypatch.setattr(
        session.pyvisa, "ResourceManager",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run 不应创建 ResourceManager")))
    with caplog.at_level(logging.INFO):
        rc = main.main(["rbw", "--rbw-list", "100", "--dry-run"])
    assert rc == 0
    text = caplog.text
    assert "DRY-RUN" in text
    assert ":SYSTem:PRESet" in text      # SA preset
    assert "*RST" in text                 # SG preset
    assert ":BANDwidth:RESolution 100.0" in text


# ---------- 部分结果导出 ----------

def test_main_exports_partial_results_on_interrupt(monkeypatch, tmp_path):
    """中途异常（MeasurementError）时应把已完成点写入 --output 并标记 partial。"""
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)

    def _boom(spec, sig, carrier_freq_hz=None, rbw_list=None):
        raise measurements.MeasurementError(
            "测试中断", partial_results={100: 100.3, 1000: 998.5})

    monkeypatch.setattr(commands, "cal_rbw", _boom)
    out = tmp_path / "partial.json"
    rc = main.main(["rbw", "--rbw-list", "100", "1000", "--output", str(out)])
    assert rc == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["partial"] is True
    assert data["command"] == "rbw"
    assert [r["rbw_hz"] for r in data["results"]] == [100, 1000]
    assert data["results"][0]["measured_hz"] == 100.3


def test_main_no_output_skips_partial_export(monkeypatch, caplog):
    """未指定 --output 时部分结果不落盘，仅记录错误并返回 1。"""
    import logging

    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)

    def _boom(spec, sig, carrier_freq_hz=None, rbw_list=None):
        raise measurements.MeasurementError(
            "测试中断", partial_results={100: 100.3})

    monkeypatch.setattr(commands, "cal_rbw", _boom)
    with caplog.at_level(logging.ERROR):
        rc = main.main(["rbw", "--rbw-list", "100"])
    assert rc == 1
    assert any("测量中断" in r.message for r in caplog.records)


def test_main_shows_point_progress(monkeypatch, caplog):
    """多校准点运行时逐点打印 [i/N] 进度行。"""
    import logging

    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    with caplog.at_level(logging.INFO):
        rc = main.main(["rbw", "--rbw-list", "100", "1000"])
    assert rc == 0
    assert "[1/2] 测量 RBW=100.0 Hz" in caplog.text
    assert "[2/2] 测量 RBW=1000.0 Hz" in caplog.text


# ---------- 分辨力带宽转换影响（JJF1396 6.12）----------

def test_main_rbw_switch_end_to_end(monkeypatch, tmp_path):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    out = tmp_path / "rs.json"
    rc = main.main(["rbw-switch", "-b", "100", "1000", "--output", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["command"] == "rbw-switch"
    assert data["ref_rbw_hz"] == 30000
    assert data["span_ratio"] == 10
    assert data["ref_level_dbm"] == -15
    assert data["sg_power_dbm"] == -20
    assert len(data["results"]) == 2
    assert data["results"][0]["rbw_hz"] == 100
    assert data["results"][0]["span_hz"] == 1000        # S/RBW = 10
    assert data["max_abs_delta_db"] == 0.0              # 假仪器恒返回 0.0
    assert data["max_abs_delta_at_rbw_hz"] == 100


def test_main_rbw_switch_chinese_alias(monkeypatch):
    from sa_cli.cli import main, parser, commands
    _patch_rm(monkeypatch)
    assert main.main(["分辨力带宽转换影响", "-b", "100"]) == 0


def test_parser_rbw_switch_rejects_bad_args():
    with pytest.raises(SystemExit):
        _parse("rbw-switch", "--span-ratio", "0")
    with pytest.raises(SystemExit):
        _parse("rbw-switch", "-b", "0")


def test_parser_rbw_switch_defaults():
    args = _parse("rbw-switch")
    assert args.ref_rbw == 30000
    assert args.span_ratio == 10
    assert args.rbw_list == [100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000]


def test_main_rbw_switch_dry_run_prints_base_and_switched_rbw(monkeypatch, caplog):
    import logging

    from sa_cli.cli import main, parser, commands
    from sa_cli import instruments
    monkeypatch.setattr(
        session.pyvisa, "ResourceManager",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run 不应创建 ResourceManager")))
    with caplog.at_level(logging.INFO):
        rc = main.main(["rbw-switch", "-b", "100", "--dry-run"])
    assert rc == 0
    assert ":BANDwidth:RESolution 30000.0" in caplog.text   # 基准 RBW（6.12.3）
    assert ":BANDwidth:RESolution 100.0" in caplog.text     # 切换点
    assert ":FREQuency:SPAN 1000.0" in caplog.text          # S/RBW = 10


# ---------- 数值后缀（k / M / G）----------

def test_parse_number_helper():
    from sa_cli.cli import main, parser, commands
    assert parser._parse_number("30k") == pytest.approx(30000.0)
    assert parser._parse_number("1K") == pytest.approx(1000.0)
    assert parser._parse_number("2.4G") == pytest.approx(2.4e9)
    assert parser._parse_number("1.5M") == pytest.approx(1.5e6)
    assert parser._parse_number("-20k") == pytest.approx(-20000.0)
    assert parser._parse_number("50e6") == pytest.approx(5e7)      # 科学计数法仍可用
    assert parser._parse_number(" 300 ") == pytest.approx(300.0)


def test_parse_number_helper_rejects_bad_input():
    import argparse

    from sa_cli.cli import main, parser, commands
    for bad in ("", "abc", "100m", "30x", "-"):
        with pytest.raises(argparse.ArgumentTypeError):
            parser._parse_number(bad)


def test_parser_si_suffix_on_lists():
    args = _parse("rbw-switch", "-b", "30k", "1M", "1.5M")
    assert args.rbw_list == [30000.0, 1000000.0, 1500000.0]
    assert _parse("rbw", "-b", "100", "1k").rbw_list == [100.0, 1000.0]


def test_parser_si_suffix_on_carrier_and_span():
    assert _parse("rbw", "-c", "2.4G").carrier == pytest.approx(2.4e9)
    assert _parse("rbw", "-c", "50M").carrier == pytest.approx(50e6)
    assert _parse("sweep-width", "-s", "1G", "1.6G").span == [1e9, 1.6e9]
    assert _parse("linear-scale", "--rbw", "3k").rbw == pytest.approx(3000.0)
    assert _parse("linear-scale", "--tolerance", "0.2").tolerance == pytest.approx(0.2)


def test_parser_si_suffix_on_signed_dbm():
    args = _parse("rbw-switch", "--sg-power", "-20", "--ref-level", "-15")
    assert args.sg_power == -20
    assert args.ref_level == -15
    # 负号 + 后缀需用 --opt=value 形式：argparse 会把 "-0.02k" 当成选项
    assert _parse("rbw-switch", "--sg-power=-0.02k").sg_power == pytest.approx(-20.0)


def test_parser_si_suffix_respects_constraints():
    with pytest.raises(SystemExit):
        _parse("rbw", "-b", "0k")                                  # 正数约束
    with pytest.raises(SystemExit):
        _parse("sweep-width", "-s", "1G", "--align-threshold", "-1k")   # 非负约束
    with pytest.raises(SystemExit):
        _parse("rbw", "-c", "100m")                                # 小写 m 有歧义
    with pytest.raises(SystemExit):
        _parse("rbw", "-b", "30x")                                 # 非法后缀
