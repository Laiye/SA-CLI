#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instrument 基类与 JSON 指令集 schema 的单元测试。"""

import json
import os

import pytest

import config
from conftest import SA_JSON, SG_JSON, build_instrument
from instruments import Instrument, SignalGenerator, SpectrumAnalyzer, visa_session


# ---------- JSON 指令集路径解析 ----------

def test_relative_json_resolved_from_data_dir(tmp_path, monkeypatch):
    """相对 JSON 名称按 config.data_dir() 解析（支持 SA_CLI_DATA_DIR 覆盖）。"""
    (tmp_path / "spectrum_analyzer.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path))
    resolved = Instrument._resolve_json_path("spectrum_analyzer.json")
    assert resolved == os.path.join(str(tmp_path), "spectrum_analyzer.json")


def test_absolute_json_path_kept_as_is():
    assert Instrument._resolve_json_path(SA_JSON) == SA_JSON


# ---------- JSON schema ----------

@pytest.mark.parametrize("json_file", [SA_JSON, SG_JSON])
def test_json_schema(json_file):
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
    actions = data["actions"]
    assert actions
    for name, act in actions.items():
        assert isinstance(act["commands"], list) and act["commands"], name
        args_num = act.get("args_num", 0)
        assert isinstance(args_num, int) and args_num >= 0, name
        assert "query" not in act, f"action '{name}' 含已废弃的 query 字段（应使用 is_query）"
        assert act.get("returns", "float") in ("float", "str"), name
        if act.get("is_query"):
            assert len(act["commands"]) == 1, name


# ---------- 动态方法生成 ----------

def test_actions_generated_from_json():
    instr, _, _ = build_instrument(SA_JSON)
    for name in ["preset", "set_center_freq", "marker_read_y", "peak_search",
                 "set_marker_delta", "init_sweep", "opc"]:
        assert hasattr(instr, name)


def test_write_action_sends_command():
    instr, resource, _ = build_instrument(SA_JSON)
    instr.preset()
    assert resource.writes == [":SYSTem:PRESet"]


def test_write_with_argument_appends_value():
    instr, resource, _ = build_instrument(SA_JSON)
    instr.set_center_freq(1e9)
    assert resource.writes[-1] == ":FREQuency:CENTer 1000000000.0"


def test_set_y_scale_type_log_lin():
    """设置 Y 坐标刻度类型（LOG/LIN）。"""
    instr, resource, _ = build_instrument(SA_JSON)
    instr.set_y_scale_type("LOG")
    assert resource.writes[-1] == ":DISPlay:WINDow:TRACe:Y:SCALe:SPACing LOG"
    instr.set_y_scale_type("LIN")
    assert resource.writes[-1] == ":DISPlay:WINDow:TRACe:Y:SCALe:SPACing LIN"


def test_query_action_returns_float():
    instr, resource, _ = build_instrument(
        SA_JSON, responses={":CALCulate:MARKer1:Y?": -85.21})
    assert instr.marker_read_y() == pytest.approx(-85.21)


def test_query_action_returns_string_when_not_numeric():
    instr, resource, _ = build_instrument(
        SG_JSON, responses={"*IDN?": "Agilent,E4440A,US00000000,1.0"})
    assert instr.idn() == "Agilent,E4440A,US00000000,1.0"


def test_numeric_query_with_garbage_raises():
    """数值查询收到非数值响应时应立即报错（带命令上下文），而非静默透传字符串。"""
    instr, resource, _ = build_instrument(
        SA_JSON, responses={":CALCulate:MARKer1:Y?": "QUERY UNTERMINATED"})
    with pytest.raises(ValueError, match="marker_read_y"):
        instr.marker_read_y()


def test_invalid_returns_field_raises(tmp_path):
    data = {"actions": {"bad": {"commands": [":A?"], "args_num": 0,
                                "is_query": True, "returns": "int"}}}
    path = tmp_path / "bad_returns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="returns"):
        build_instrument(str(path))


def test_wrong_argument_count_raises():
    instr, _, _ = build_instrument(SA_JSON)
    with pytest.raises(TypeError, match="set_center_freq"):
        instr.set_center_freq(1, 2)


def test_query_action_with_multiple_commands_raises(tmp_path):
    data = {"actions": {"bad": {"commands": [":A", ":B"], "args_num": 0, "is_query": True}}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    instr, _, _ = build_instrument(str(path))
    with pytest.raises(ValueError, match="bad"):
        instr.bad()


def test_multi_arg_formatting(tmp_path):
    data = {
        "actions": {
            "set_xy": {"commands": [":XY:{0}:{1} "], "args_num": 2},
            "set_ab": {"commands": [":AB:a={} b={}"], "args_num": 2},
        }
    }
    path = tmp_path / "multi.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    instr, resource, _ = build_instrument(str(path))
    instr.set_xy(1, 2)
    assert resource.writes[-1] == ":XY:1:2 "
    instr.set_ab(10, 20)
    assert resource.writes[-1] == ":AB:a=10 b=20"


# ---------- schema 校验 ----------

def test_missing_commands_raises(tmp_path):
    data = {"actions": {"bad": {"args_num": 0}}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="bad"):
        build_instrument(str(path))


def test_negative_args_num_raises(tmp_path):
    data = {"actions": {"bad": {"commands": [":X "], "args_num": -1}}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="args_num"):
        build_instrument(str(path))


# ---------- 其他 ----------

def test_clear_status_uses_device_clear_and_cls():
    instr, resource, _ = build_instrument(SA_JSON)
    instr.clear_status()
    assert resource.cleared is True       # 调用了 VISA device clear（不再逐字节读阻塞）
    assert "*CLS" in resource.writes


def test_visa_session_closes_resources():
    from conftest import FakeResourceManager, FakeVisaResource
    rm = FakeResourceManager(FakeVisaResource())
    with visa_session("dummy-sg", "dummy-sa", rm=rm) as (sig, spec):
        assert isinstance(sig, SignalGenerator)
        assert isinstance(spec, SpectrumAnalyzer)
    assert rm.closed


def test_visa_session_turns_rf_off_on_exit():
    from conftest import FakeResourceManager, FakeVisaResource
    rm = FakeResourceManager(FakeVisaResource())
    with visa_session("dummy-sg", "dummy-sa", rm=rm):
        pass
    assert ":OUTPut:STATe OFF" in rm.resource.writes


def test_visa_session_rf_off_on_exception():
    from conftest import FakeResourceManager, FakeVisaResource
    rm = FakeResourceManager(FakeVisaResource())
    with pytest.raises(RuntimeError):
        with visa_session("dummy-sg", "dummy-sa", rm=rm) as (sig, spec):
            raise RuntimeError("boom")
    assert ":OUTPut:STATe OFF" in rm.resource.writes


# ---------- dry-run ----------

def test_dry_run_instrument_does_not_connect(caplog):
    """dry_run 仪器不打开 VISA 资源；write 打印 [DRY-RUN]，数值查询返回占位值。"""
    sig = SignalGenerator("no-such-device", dry_run=True)
    assert sig.instr is None
    assert sig.set_freq(1e9) is None            # write 动作不返回
    assert sig.set_power(0) is None
    assert sig.opc() == 1.0                     # OPC 视为立即完成
    assert isinstance(sig.idn(), str)           # 字符串查询返回占位串
    assert sig.close() is None                  # 未连接时 close 安全
    sa = SpectrumAnalyzer("no-such-device", dry_run=True)
    assert sa.marker_read_y() == 0.0            # 数值查询返回占位 0.0


def test_dry_run_logs_scpi_commands(caplog):
    sa = SpectrumAnalyzer("no-such-device", dry_run=True)
    with caplog.at_level("INFO"):
        sa.set_center_freq(1e9)
        sa.preset()
        sa.marker_read_y()
    text = caplog.text
    assert "[DRY-RUN]" in text
    assert ":FREQuency:CENTer 1000000000.0" in text
    assert ":SYSTem:PRESet" in text
    assert ":CALCulate:MARKer1:Y?" in text


def test_visa_session_dry_run_skips_real_rm():
    """dry-run 会话不应创建真实 ResourceManager（传入会抛错的哨兵验证）。"""
    from instruments import pyvisa

    def _boom():
        raise AssertionError("dry-run 不应创建 ResourceManager")

    import instruments as instr_mod
    old = instr_mod.pyvisa.ResourceManager
    instr_mod.pyvisa.ResourceManager = _boom
    try:
        with visa_session("sg", "sa", dry_run=True) as (sig, spec):
            assert isinstance(sig, SignalGenerator)
            assert isinstance(spec, SpectrumAnalyzer)
            assert sig.instr is None and spec.instr is None
    finally:
        instr_mod.pyvisa.ResourceManager = old
    assert pyvisa.ResourceManager is old
