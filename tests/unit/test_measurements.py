"""测量算法的单元测试：使用模拟滤波器形状驱动 _find_edge 收敛。"""

from sa_cli.measurements import common, bandwidth

import math

import pytest

from sa_cli import config
from sa_cli import measurements
from tests.fakes import FakeResourceManager, FakeVisaResource
from sa_cli.instruments import Instrument
from sa_cli.measurements.bandwidth import _find_edge
from sa_cli.measurements import (MeasurementError, cal_bw60,
                          cal_linear_scale, cal_log_scale, cal_rbw,
                          cal_rbw_switch, cal_ssb_phase_noise, cal_sweep_width)


class ShapeSA(FakeVisaResource):
    """模拟滤波器：delta = depth * (1 - (offset/(rbw/2))^2)，offset=rbw/2 处 delta=0。"""

    def __init__(self, carrier, rbw, depth=3.0):
        super().__init__()
        self.carrier = carrier
        self.rbw = rbw
        self.depth = depth
        self.current_freq = carrier

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?":
            offset = self.current_freq - self.carrier
            rel = (offset / (self.rbw / 2)) ** 2
            return str(self.depth * (1 - rel))
        return super().query(command)


class ShapeSG(FakeVisaResource):
    def __init__(self, sa):
        super().__init__()
        self.sa = sa

    def write(self, command):
        if command.startswith(":FREQuency:CW "):
            self.sa.current_freq = float(command.split()[-1])
        super().write(command)


def make_pair(carrier, rbw):
    sa_res = ShapeSA(carrier, rbw)
    sg_res = ShapeSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: None)


# ---------- OPC 等待 ----------

def test_wait_opc_returns_true_when_complete():
    sg, sa = make_pair(50e6, 100)
    assert common._wait_opc(sa) is True


def test_wait_sweep_toggles_single_and_continuous():
    sg, sa = make_pair(50e6, 100)
    common._wait_sweep(sa, min_sleep=0.0)
    writes = sa.instr.writes
    assert ":INITiate:CONTinuous OFF" in writes
    assert ":INITiate:IMMediate" in writes
    assert ":INITiate:CONTinuous ON" in writes


def test_opc_done_false_on_non_numeric():
    sg, sa = make_pair(50e6, 100)
    sa.instr.responses["*OPC?"] = "OK"   # responses 优先于 *OPC? 特判
    assert common._opc_done(sa) is False


# ---------- _find_edge ----------

def test_find_edge_converges_near_3db_point():
    carrier, rbw = 50e6, 100
    sg, sa = make_pair(carrier, rbw)
    f_left = _find_edge(sg, sa, carrier, rbw, -1, "左")
    f_right = _find_edge(sg, sa, carrier, rbw, 1, "右")

    assert carrier - rbw < f_left < carrier
    assert carrier < f_right < carrier + rbw
    measured = f_right - f_left
    assert 0.7 * rbw < measured < 1.3 * rbw


def test_find_edge_final_delta_within_tolerance():
    carrier, rbw = 50e6, 100
    sg, sa = make_pair(carrier, rbw)
    f = _find_edge(sg, sa, carrier, rbw, 1, "右")
    sa_res = sa.instr
    assert sa_res.current_freq == f
    delta = float(sa_res.query(":CALCulate:MARKer1:Y?"))
    assert abs(delta) <= 0.5


def test_find_edge_tight_thresholds_for_3db():
    """3dB(RBW) 测量使用收紧阈值：粗搜 0.1 dB，精调 0.05 dB。"""
    carrier, rbw = 50e6, 100
    sg, sa = make_pair(carrier, rbw)
    f = _find_edge(sg, sa, carrier, rbw, 1, "右",
                   coarse_threshold=0.1, fine_threshold=0.05)
    delta = float(sa.instr.query(":CALCulate:MARKer1:Y?"))
    assert abs(delta) <= 0.05


class FailingReadSA(ShapeSA):
    """marker Y 读取持续/暂时抛错，用于验证 _find_edge 失败处理。"""

    def __init__(self, carrier, rbw, fail_forever=True):
        super().__init__(carrier, rbw)
        self.fail_forever = fail_forever
        self.fail_remaining = 2 if not fail_forever else 0
        self.fail_count = 0

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?":
            if self.fail_forever or self.fail_remaining > 0:
                self.fail_count += 1
                if not self.fail_forever:
                    self.fail_remaining -= 1
                raise OSError("simulated marker read failure")
        return super().query(command)


def make_failing_pair(carrier, rbw, fail_forever=True):
    sa_res = FailingReadSA(carrier, rbw, fail_forever=fail_forever)
    sg_res = ShapeSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa, sa_res


def test_find_edge_aborts_after_consecutive_read_failures():
    """连续读取失败达到上限时中止，不再拿无效数据当"成功"结果。"""
    carrier, rbw = 50e6, 100
    sg, sa, sa_res = make_failing_pair(carrier, rbw, fail_forever=True)
    with pytest.raises(RuntimeError, match="连续 5 次读取失败"):
        _find_edge(sg, sa, carrier, rbw, 1, "右")
    assert sa_res.fail_count == common.MAX_CONSECUTIVE_READ_FAILURES


def test_find_edge_recovers_after_transient_failures():
    """少量瞬时失败后应能恢复并正常收敛。"""
    carrier, rbw = 50e6, 100
    sg, sa, sa_res = make_failing_pair(carrier, rbw, fail_forever=False)
    f = _find_edge(sg, sa, carrier, rbw, 1, "右")
    assert sa_res.fail_count == 2
    assert carrier < f < carrier + rbw


# ---------- 校准函数 ----------

def test_cal_rbw_returns_reasonable_bandwidth():
    carrier, rbw = 50e6, 100
    sg, sa = make_pair(carrier, rbw)
    results = cal_rbw(sa, sg, carrier_freq_hz=carrier, rbw_list=[100])
    assert list(results.keys()) == [100]
    assert results[100] == pytest.approx(rbw, rel=0.3)


def test_cal_bw60_returns_reasonable_bandwidth():
    carrier, rbw = 50e6, 1000
    sg, sa = make_pair(carrier, rbw)
    results = cal_bw60(sa, sg, carrier_freq_hz=carrier, rbw_list=[1000])
    assert results[1000] == pytest.approx(rbw, rel=0.3)


def test_cal_ssb_phase_noise_returns_float():
    sg, sa = make_pair(50e6, 100)
    pn = cal_ssb_phase_noise(sg, sa, 50e6, 100)
    assert isinstance(pn, float)


def test_phase_noise_uses_trace_average():
    sg, sa = make_pair(50e6, 100)
    cal_ssb_phase_noise(sg, sa, 50e6, 100, average_count=8)
    writes = sa.instr.writes
    assert ":AVERage:STATE ON" in writes
    assert ":AVERage:COUNt 8" in writes
    assert ":AVERage:STATE OFF" in writes


def test_phase_noise_skips_average_when_count_one():
    sg, sa = make_pair(50e6, 100)
    cal_ssb_phase_noise(sg, sa, 50e6, 100, average_count=1)
    writes = sa.instr.writes
    assert ":AVERage:STATE ON" not in writes


def test_phase_noise_formula():
    sg, sa = make_pair(50e6, 100)
    pn = cal_ssb_phase_noise(sg, sa, 50e6, 100, average_count=1)
    rbw = 10.0
    expected = 3.0 - 10 * math.log10(rbw)  # 模拟滤波器中心 delta=+3dB
    assert pn == pytest.approx(expected)


# ---------- 扫频宽度 ----------

class SweepSA(FakeVisaResource):
    """理想频标 + 可模拟晶振偏差：marker X 返回 SG 当前频率 + offset。"""

    def __init__(self, offset=0.0):
        super().__init__()
        self.current_freq = 1e9
        self.offset = offset

    def query(self, command):
        if command == ":CALCulate:MARKer1:X?":
            return str(self.current_freq + self.offset)
        return super().query(command)


class SweepSG(FakeVisaResource):
    def __init__(self, sa):
        super().__init__()
        self.sa = sa

    def write(self, command):
        if command.startswith(":FREQuency:CW "):
            self.sa.current_freq = float(command.split()[-1])
        super().write(command)


def make_sweep_pair(offset=0.0):
    sa_res = SweepSA(offset=offset)
    sg_res = SweepSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa


def test_cal_sweep_width_small_span():
    """span ≤ 1 GHz：中心 1 GHz，频点 1 GHz ± 0.4*span。"""
    sg, sa = make_sweep_pair()
    result = cal_sweep_width(sa, sg, span=0.5e9)
    assert result["freq_diff"] == pytest.approx(0.8 * 0.5e9)
    assert result["delta"] == pytest.approx(0, abs=1e-9)
    assert result["corrected_width"] == pytest.approx(0.5e9)


def test_cal_sweep_width_large_span():
    """span > 1 GHz：中心 span/2，频点 0.1*span 与 0.9*span。"""
    sg, sa = make_sweep_pair()
    result = cal_sweep_width(sa, sg, span=2e9)
    assert result["center"] == pytest.approx(1e9)
    assert result["f1"] == pytest.approx(0.2e9)
    assert result["f2"] == pytest.approx(1.8e9)
    assert result["freq_diff"] == pytest.approx(1.6e9)
    assert result["delta"] == pytest.approx(0, abs=1e-9)
    assert result["corrected_width"] == pytest.approx(2e9)


def test_cal_sweep_width_small_span_applies_alignment_and_rbw():
    """小 span 启用峰值对中预处理，并设置 RBW=span/20 分辨两个峰值。"""
    sg, sa = make_sweep_pair(offset=500.0)  # 模拟晶振偏差 500 Hz
    result = cal_sweep_width(sa, sg, span=1000,
                             align_threshold=1e5, align_span=1e6)
    assert result["freq_diff"] == pytest.approx(800)
    assert result["delta"] == pytest.approx(0, abs=1e-9)
    assert result["aligned_center"] == pytest.approx(1e9 + 500.0)
    writes = sa.instr.writes
    assert ":BANDwidth:RESolution 50.0" in writes


def test_cal_sweep_width_tiny_span_zoom_windows():
    """10 Hz span：对中窗口应逐级缩至 1000×→100×→10×span（10000/1000/100 Hz），
    再在测量 span=10 Hz 下最终对中。"""
    sg, sa = make_sweep_pair(offset=30.0)
    result = cal_sweep_width(sa, sg, span=10,
                             align_threshold=1e5, align_span=1e3)
    writes = sa.instr.writes
    spans = [float(w.split()[-1]) for w in writes if w.startswith(":FREQuency:SPAN ")]
    for expected in (10000.0, 1000.0, 100.0, 10.0):
        assert any(abs(s - expected) < 1e-6 for s in spans), f"缺少窗口 span={expected}"
    # 对中前必须先设置中心频率（preset 后非 1 GHz，否则宽窗口搜不到峰值）
    centers = [w for w in writes if w.startswith(":FREQuency:CENTer ")]
    assert centers and float(centers[0].split()[-1]) == pytest.approx(1e9)
    assert result["freq_diff"] == pytest.approx(8)   # 0.8×10 Hz
    assert result["aligned_center"] == pytest.approx(1e9 + 30.0)


def test_cal_sweep_width_large_span_skips_alignment():
    """大 span 不做对中、不设 RBW。"""
    sg, sa = make_sweep_pair(offset=500.0)
    result = cal_sweep_width(sa, sg, span=2e9,
                             align_threshold=1e5, align_span=1e6)
    assert result["aligned_center"] is None
    writes = sa.instr.writes
    assert not any(":BANDwidth:RESolution" in w for w in writes)


def test_cal_sweep_width_alignment_disabled_when_threshold_zero():
    """align_threshold=0 时关闭对中预处理。"""
    sg, sa = make_sweep_pair()
    result = cal_sweep_width(sa, sg, span=1000, align_threshold=0)
    assert result["aligned_center"] is None
    writes = sa.instr.writes
    assert not any(":BANDwidth:RESolution" in w for w in writes)


def test_sweep_width_slow_span_uses_long_settle(monkeypatch):
    """span ≤ 100 Hz 时等待波形稳定用 4 s，其余用 2 s。"""
    calls = []
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: calls.append(s))
    sg, sa = make_sweep_pair()
    cal_sweep_width(sa, sg, span=10, align_threshold=1e5, align_span=1e3)
    assert 4.0 in calls


def test_sweep_width_fast_span_uses_short_settle(monkeypatch):
    calls = []
    monkeypatch.setattr(Instrument, "sleep", lambda self, s: calls.append(s))
    sg, sa = make_sweep_pair()
    cal_sweep_width(sa, sg, span=1000, align_threshold=1e5, align_span=1e6)
    assert 4.0 not in calls
    assert 2.0 in calls


# ---------- 对数刻度 ----------

class LogSA(FakeVisaResource):
    """模拟对数刻度：正常模式返回 SG 电平，delta 模式返回电平差。"""

    def __init__(self):
        super().__init__()
        self.current_power = -1.0
        self.delta_ref = None

    def write(self, command):
        if command == ":CALCulate:MARKer1:MODE DELTa":
            self.delta_ref = self.current_power
        super().write(command)

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?":
            if self.delta_ref is not None:
                return str(self.current_power - self.delta_ref)
            return str(self.current_power)
        return super().query(command)


class LogSG(FakeVisaResource):
    def __init__(self, sa):
        super().__init__()
        self.sa = sa

    def write(self, command):
        if command.startswith(":POWer:AMPLitude "):
            self.sa.current_power = float(command.split()[-1])
        super().write(command)


def make_log_pair():
    sa_res = LogSA()
    sg_res = LogSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa


def test_cal_log_scale_1db_mode():
    """1 dB/div：默认校准点 1~9，marker delta 应等于 -p。"""
    sg, sa = make_log_pair()
    result = cal_log_scale(sa, sg, scale_db_per_div=1)
    assert result["scale_db_per_div"] == 1
    assert list(result["results"].keys()) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    for point, delta in result["results"].items():
        assert delta == pytest.approx(-point)


def test_cal_log_scale_10db_mode():
    """10 dB/div：默认校准点 10~80。"""
    sg, sa = make_log_pair()
    result = cal_log_scale(sa, sg, scale_db_per_div=10)
    assert result["scale_db_per_div"] == 10
    assert list(result["results"].keys()) == [10, 20, 30, 40, 50, 60, 70, 80]
    for point, delta in result["results"].items():
        assert delta == pytest.approx(-point)


def test_cal_log_scale_adjusts_peak_to_zero():
    """峰值应被迭代调整至 0 dB（SG 电平从 -1 升到 0）。"""
    sg, sa = make_log_pair()
    cal_log_scale(sa, sg, scale_db_per_div=1)
    assert sa.instr.delta_ref == pytest.approx(0.0)


def test_cal_log_scale_custom_points():
    sg, sa = make_log_pair()
    result = cal_log_scale(sa, sg, scale_db_per_div=1, points=[1, 3, 5])
    assert list(result["results"].keys()) == [1, 3, 5]
    assert result["results"][3] == pytest.approx(-3)


def test_cal_log_scale_invalid_scale_raises():
    sg, sa = make_log_pair()
    with pytest.raises(ValueError):
        cal_log_scale(sa, sg, scale_db_per_div=5)


# ---------- 线性刻度 ----------

class LinSA(FakeVisaResource):
    """理想线性刻度：marker Y 返回电压 V = sqrt(0.05*10^(P/10))（0 dBm → 0.2236 V）。"""

    def __init__(self, return_mv=False):
        super().__init__()
        self.current_power = -1.0
        self.return_mv = return_mv

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?":
            v = math.sqrt(0.05 * 10 ** (self.current_power / 10.0))
            return str(v * 1000 if self.return_mv else v)
        return super().query(command)


class LinSG(FakeVisaResource):
    def __init__(self, sa):
        super().__init__()
        self.sa = sa

    def write(self, command):
        if command.startswith(":POWer:AMPLitude "):
            self.sa.current_power = float(command.split()[-1])
        super().write(command)


def make_lin_pair(return_mv=False):
    sa_res = LinSA(return_mv=return_mv)
    sg_res = LinSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa


def test_cal_linear_scale_ideal_volts():
    """理想线性刻度：Vm 应等于理论 Vn，且切换为线性模式。"""
    sg, sa = make_lin_pair()
    result = cal_linear_scale(sa, sg)
    assert list(result["results"].keys()) == [4, 8, 12, 16, 20]
    assert ":DISPlay:WINDow:TRACe:Y:SCALe:SPACing LIN" in sa.instr.writes
    for point, vals in result["results"].items():
        # 目标 223.6 mV 非精确 0 dBm，收敛后 SG 电平约有 ±0.001 dB 残差
        assert vals["measured_mv"] == pytest.approx(vals["theoretical_mv"], abs=0.1)
        assert abs(vals["relative_error_pct"]) < 0.05


def test_cal_linear_scale_adjusts_peak_to_target():
    """峰值应被迭代调整至 223.6 mV（SG 电平收敛至 ~0 dBm）。"""
    sg, sa = make_lin_pair()
    result = cal_linear_scale(sa, sg)
    assert abs(result["adjusted_power_dbm"]) < 0.01


def test_cal_linear_scale_mv_factor():
    """marker 直接返回 mV 时，mv_per_unit=1 应同样成立。"""
    sg, sa = make_lin_pair(return_mv=True)
    result = cal_linear_scale(sa, sg, mv_per_unit=1.0)
    for point, vals in result["results"].items():
        assert vals["measured_mv"] == pytest.approx(vals["theoretical_mv"], abs=0.1)


def test_cal_linear_scale_custom_points():
    sg, sa = make_lin_pair()
    result = cal_linear_scale(sa, sg, points=[4, 12, 20])
    assert list(result["results"].keys()) == [4, 12, 20]
    assert result["results"][20]["measured_mv"] == pytest.approx(22.36, rel=1e-3)


def test_cal_linear_scale_relative_error_formula():
    """相对误差 = (Vm-Vn)/223.6 × 100%。"""
    sg, sa = make_lin_pair()
    result = cal_linear_scale(sa, sg, points=[4, 20])
    for point, vals in result["results"].items():
        expected = (vals["measured_mv"] - vals["theoretical_mv"]) / 223.6 * 100.0
        assert vals["relative_error_pct"] == pytest.approx(expected)


class FailBelowThresholdLinSA(LinSA):
    """SG 电平低于 -7 dBm（衰减点 ≥ 8 dB）时 marker 读取抛错。"""

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?" and self.current_power < -7.0:
            raise OSError("simulated linear read failure")
        return super().query(command)


def test_cal_linear_scale_carries_partial_results_on_failure():
    """中途某点失败时应抛 MeasurementError 并携带已完成点的部分结果。"""
    sa_res = FailBelowThresholdLinSA()
    sg_res = LinSG(sa_res)
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    with pytest.raises(MeasurementError) as ei:
        cal_linear_scale(sa, sg)
    # 默认校准点 [4,8,12,16,20]：第 2 点（8 dB）失败，已完成点只有 4 dB
    assert set(ei.value.partial_results.keys()) == {4}


# ---------- 进度 / ETA ----------

def test_fmt_duration():
    assert common._fmt_duration(0) == "0秒"
    assert common._fmt_duration(5) == "5秒"
    assert common._fmt_duration(65) == "1分05秒"
    assert common._fmt_duration(3.7) == "4秒"   # 四舍五入


def test_point_progress_first_point_no_eta(caplog):
    progress = common.PointProgress(3)
    with caplog.at_level("INFO"):
        progress.begin(1, "校准点 A")
    assert "[1/3] 校准点 A" in caplog.text
    assert "预计剩余" not in caplog.text


def test_point_progress_second_point_has_eta(caplog):
    progress = common.PointProgress(3)
    with caplog.at_level("INFO"):
        progress.begin(1, "校准点 A")
        caplog.clear()
        progress.begin(2, "校准点 B")
    assert "[2/3] 校准点 B（已用 " in caplog.text
    assert "预计剩余" in caplog.text


# ---------- 分辨力带宽转换影响（JJF1396 6.12）----------

class RbwSwitchSA(FakeVisaResource):
    """模拟 RBW 切换的幅度影响：增量模式下 marker Y 返回该 RBW 对应的 Δ。"""

    def __init__(self, deltas=None, default_delta=0.0):
        super().__init__()
        self.deltas = dict(deltas or {})
        self.default_delta = default_delta
        self.current_rbw = None
        self.delta_mode = False
        self.rbws = []
        self.spans = []

    def write(self, command):
        if command.startswith(":BANDwidth:RESolution "):
            self.current_rbw = float(command.split()[-1])
            self.rbws.append(self.current_rbw)
        elif command.startswith(":FREQuency:SPAN "):
            self.spans.append(float(command.split()[-1]))
        elif command == ":CALCulate:MARKer1:MODE DELTa":
            self.delta_mode = True
        elif command == ":CALCulate:MARKer1:MODE POS":
            self.delta_mode = False
        super().write(command)

    def query(self, command):
        if command == ":CALCulate:MARKer1:Y?":
            if self.delta_mode:
                return str(self.deltas.get(self.current_rbw, self.default_delta))
            return str(0.0)
        return super().query(command)


def make_rbw_switch_pair(deltas=None, default_delta=0.0):
    sa_res = RbwSwitchSA(deltas=deltas, default_delta=default_delta)
    sg_res = FakeVisaResource()
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    return sg, sa, sa_res


def test_cal_rbw_switch_records_delta_per_rbw():
    sg, sa, sa_res = make_rbw_switch_pair(
        deltas={100.0: 0.12, 1000.0: -0.35, 10000.0: 0.02})
    results = cal_rbw_switch(sa, sg, rbw_list=[100, 1000, 10000])
    assert list(results.keys()) == [100, 1000, 10000]
    assert results[100] == pytest.approx(0.12)
    assert results[1000] == pytest.approx(-0.35)
    assert results[10000] == pytest.approx(0.02)


def test_cal_rbw_switch_keeps_span_ratio():
    """扫频宽度始终 = S/RBW × RBW：基准点与每个切换点都按同一比率设置。"""
    sg, sa, sa_res = make_rbw_switch_pair()
    cal_rbw_switch(sa, sg, rbw_list=[100, 1000], ref_rbw=30e3, span_ratio=5)
    assert sa_res.spans == [5 * 30e3, 5 * 100, 5 * 1000]
    assert sa_res.rbws[0] == pytest.approx(30e3)          # 先设置基准 RBW（6.12.3）
    assert sa_res.rbws[-2:] == [100.0, 1000.0]


def test_cal_rbw_switch_establishes_delta_reference_once():
    """Δ 参考只在基准状态建立一次，切换过程中不重置。"""
    sg, sa, sa_res = make_rbw_switch_pair()
    cal_rbw_switch(sa, sg, rbw_list=[100, 1000, 10000])
    assert sa_res.writes.count(":CALCulate:MARKer1:MODE DELTa") == 1
    assert sa_res.writes.count(":CALCulate:MARKer1:MODE POS") == 0


def test_cal_rbw_switch_default_ref_rbw():
    sg, sa, sa_res = make_rbw_switch_pair()
    cal_rbw_switch(sa, sg, rbw_list=[1000])
    assert sa_res.rbws[0] == pytest.approx(config.DEFAULT_RBW_SWITCH_REF)   # 30 kHz


class FailOnRbwSA(RbwSwitchSA):
    """指定 RBW 的增量读数抛错，用于验证部分结果。"""

    def __init__(self, fail_rbw):
        super().__init__()
        self.fail_rbw = fail_rbw

    def query(self, command):
        if (command == ":CALCulate:MARKer1:Y?" and self.delta_mode
                and self.current_rbw == self.fail_rbw):
            raise OSError("simulated read failure")
        return super().query(command)


def test_cal_rbw_switch_carries_partial_results_on_failure():
    sa_res = FailOnRbwSA(fail_rbw=1000.0)
    sa_res.deltas = {100.0: 0.1}
    sg_res = FakeVisaResource()
    sa = Instrument("sa", "spectrum_analyzer.json", rm=FakeResourceManager(sa_res))
    sg = Instrument("sg", "signal_generator.json", rm=FakeResourceManager(sg_res))
    with pytest.raises(MeasurementError) as ei:
        cal_rbw_switch(sa, sg, rbw_list=[100, 1000])
    assert set(ei.value.partial_results.keys()) == {100}
