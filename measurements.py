#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测量算法：单边带相位噪声、RBW 验证、-60dB 带宽。"""

import logging
import math
import time

import config

logger = logging.getLogger(__name__)

# 模块级别名，便于测试中替换为 no-op，避免真实等待
_sleep = time.sleep


def disable_sleeps():
    """关闭真实等待（--dry-run 时调用），避免模拟流程按真实时长空等。"""
    global _sleep
    _sleep = lambda _s: None


def enable_sleeps():
    """恢复真实等待。"""
    global _sleep
    _sleep = time.sleep


class MeasurementError(Exception):
    """测量中断；携带已完成校准点的部分结果，便于中途异常时导出。"""

    def __init__(self, message, partial_results=None):
        super().__init__(message)
        self.partial_results = partial_results


def _fmt_duration(seconds):
    """秒数 → “X分Y秒”/“Y秒” 的可读文本。"""
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{minutes}分{secs:02d}秒"
    return f"{secs}秒"


class PointProgress:
    """多校准点测量的进度与 ETA：begin(i, label) 在每点开始前打印
    “[i/N] label（已用 X · 预计剩余 Y）”，耗时按已完成点的平均用时估算。"""

    def __init__(self, total):
        self.total = total
        self._start = time.monotonic()

    def begin(self, index, label):
        elapsed = time.monotonic() - self._start
        completed = index - 1
        if completed > 0:
            avg_per_point = elapsed / completed
            remaining = self.total - completed
            eta = avg_per_point * remaining
            logger.info("\n[%d/%d] %s（已用 %s · 预计剩余 %s）",
                        index, self.total, label,
                        _fmt_duration(elapsed), _fmt_duration(eta))
        else:
            logger.info("\n[%d/%d] %s", index, self.total, label)


# 小 span 波形更新慢：span ≤ 该值时用更长的稳定等待
SLOW_SPAN_LIMIT = 100.0
SLOW_SPAN_SETTLE = 4.0
FAST_SPAN_SETTLE = 2.0

# *OPC? 等待：轮询间隔与超时上限
OPC_POLL_S = 0.1
OPC_TIMEOUT_S = 60.0     # 频谱仪单次扫描 OPC 上限（与 VISA 超时一致）
SG_OPC_TIMEOUT_S = 15.0  # 信号源频率/电平稳定 OPC 上限

# _find_edge 连续读取失败上限：超过即中止，避免拿无效数据当"成功"结果返回
MAX_CONSECUTIVE_READ_FAILURES = 5


def _settle_time(span):
    """小 span（≤ 100 Hz）扫描慢，返回较长稳定等待；其余返回常规等待。"""
    if span <= SLOW_SPAN_LIMIT:
        return SLOW_SPAN_SETTLE
    return FAST_SPAN_SETTLE


def _opc_done(instr):
    """*OPC? 返回 1 视为操作完成；I/O 异常或非数值返回视为未完成。"""
    try:
        return float(instr.opc()) == 1.0
    except Exception:
        return False


def _wait_opc(instr, min_sleep=0.0, timeout_s=OPC_TIMEOUT_S):
    """
    等待仪器 *OPC? = 1（挂起操作全部完成）。

    先保底 sleep min_sleep（覆盖 preset 内部校准等 OPC 未跟踪的操作），
    再轮询 *OPC?；超时返回 False 并告警，不抛异常（调用方按原路径继续）。
    """
    if min_sleep > 0:
        _sleep(min_sleep)
    deadline = time.monotonic() + timeout_s
    while not _opc_done(instr):
        if time.monotonic() >= deadline:
            logger.warning("OPC 等待超时（%.0f s）", timeout_s)
            return False
        _sleep(OPC_POLL_S)
    return True


def _wait_sweep(spec_an, min_sleep=0.0, timeout_s=OPC_TIMEOUT_S):
    """
    等待频谱仪完成一次扫描：切单次扫描 → 触发 :INITiate:IMMediate → *OPC?，
    结束后恢复连续扫描。连续扫描模式下 *OPC? 语义不可靠，必须用单次扫描模式。
    """
    try:
        spec_an.set_sweep_single()
        spec_an.init_sweep()
        return _wait_opc(spec_an, min_sleep=min_sleep, timeout_s=timeout_s)
    except Exception as e:
        logger.warning("等待扫描完成失败: %s", e)
        _sleep(1.0)
        return False
    finally:
        try:
            spec_an.set_sweep_cont()
        except Exception:
            pass


def _init_signal_gen(sig_gen, power_dbm, freq_hz=None, preset_s=2.0, settle_s=0.5):
    """信号源初始化：preset →（可选载波频率）→ 电平 → RF on，*OPC? 等待就绪。

    preset_s: preset 后的保底等待（覆盖内部校准等 OPC 未跟踪的操作）；
    settle_s: RF on 后的保底等待。
    """
    sig_gen.preset()
    _wait_opc(sig_gen, min_sleep=preset_s, timeout_s=SG_OPC_TIMEOUT_S)
    sig_gen.mod_off()
    if freq_hz is not None:
        sig_gen.set_freq(freq_hz)
    sig_gen.set_power(power_dbm)
    sig_gen.rf_on()
    _wait_opc(sig_gen, min_sleep=settle_s, timeout_s=SG_OPC_TIMEOUT_S)


def _init_spec_an(spec_an, preset_s=3.0):
    """频谱仪初始化：preset 并等待就绪（*OPC? 轮询）。"""
    spec_an.preset()
    _wait_opc(spec_an, min_sleep=preset_s)


def _collect_points(points, measure_one, action, describe=None):
    """逐点执行 measure_one(point) 并收集结果；每点开始前打印进度/ETA
    （describe(point) 提供该点的说明文本），任一点失败抛 MeasurementError
    并携带已完成点的部分结果（point → 值的映射）。"""
    results = {}
    progress = PointProgress(len(points))
    for i, point in enumerate(points, start=1):
        try:
            label = describe(point) if describe else f"{action}点 {point}"
            progress.begin(i, label)
            results[point] = measure_one(point)
        except MeasurementError:
            raise
        except Exception as e:
            raise MeasurementError(
                f"{action}失败于校准点 {point}（已完成 {len(results)}/{len(points)} 点）: {e}",
                partial_results=results,
            ) from e
    return results


def cal_ssb_phase_noise(sig_gen, spec_an, carrier_freq_hz, offset_hz,
                        ref_level_dbm=0, atten_db=10, average_count=8):
    """
    单边带相位噪声测量 (dBc/Hz)

    先测载波功率，再将频偏点移至 center 做零扫宽（Span=0）测量，
    通过 VBW=10Hz 与可选的 Trace 平均降噪，±两侧各测一次，
    取噪声更差的一侧（Δ 绝对值较小）计算相位噪声。
    """
    span = 100 * offset_hz
    rbw = 0.1 * offset_hz
    use_average = bool(average_count) and average_count > 1

    # 1. 配置信号源
    _init_signal_gen(sig_gen, power_dbm=0, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪，测量载波功率
    _init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span)
    spec_an.set_rbw(rbw)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    _wait_sweep(spec_an, min_sleep=2.0)
    spec_an.peak_search()
    _sleep(0.5)
    carrier_power = spec_an.marker_read_y()
    logger.info("  载波功率: %.2f dBm", carrier_power)

    # 3. 零扫宽测量 ± 频偏处噪声功率
    def _measure_offset(side_name, sign):
        # 将频偏点移至 center
        spec_an.set_marker_normal()
        _sleep(1.0)
        spec_an.peak_search()
        _sleep(3.0)
        spec_an.set_marker_delta()
        _sleep(2.0)
        spec_an.marker_set_x(sign * offset_hz)
        _sleep(2.0)
        spec_an.set_marker_to_center()         # center = 载波 ± 频偏
        _sleep(2.0)

        # 零扫宽，VBW 降噪 + Trace 平均后读取
        spec_an.set_span(0)
        spec_an.set_rbw(rbw)
        spec_an.set_vbw(10)                    # VBW=10Hz 降噪
        if use_average:
            spec_an.set_average_count(average_count)
            spec_an.set_trace_average_on()
            _sleep(2.0)                        # 等待平均窗口填充
        _wait_sweep(spec_an, min_sleep=1.0)    # 等本次扫描完成后再读数

        delta = spec_an.marker_read_y()
        logger.info("  %s侧 %d Hz 偏移: Δ=%.2f dB", side_name, offset_hz, delta)

        # 恢复
        if use_average:
            spec_an.set_trace_average_off()
        spec_an.set_vbw_auto()                 # VBW 改回自动
        spec_an.set_center_freq(carrier_freq_hz)
        _sleep(1.0)
        spec_an.set_span(span)
        _wait_sweep(spec_an, min_sleep=2.0)
        return delta

    delta_pos = _measure_offset("正", 1)
    delta_neg = _measure_offset("负", -1)

    # 取绝对值较小的一侧（噪声更差的一侧）作为 ΔL
    if abs(delta_pos) <= abs(delta_neg):
        delta_l = delta_pos
        side = "正"
    else:
        delta_l = delta_neg
        side = "负"
    logger.info("  选用%s侧 ΔL = %.2f dB", side, delta_l)

    # 4. 计算相位噪声
    phase_noise = delta_l - 10 * math.log10(rbw)
    logger.info("相位噪声 @ %d Hz 偏移 (Span=0, RBW=%.1f Hz): %.2f dBc/Hz",
                offset_hz, rbw, phase_noise)
    sig_gen.rf_off()
    return phase_noise


def _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, direction, label,
               coarse_step_factor=1, settle_time_s=0.1,
               fine_step_divisor=200,
               coarse_threshold=1.0, fine_threshold=0.5):
    """
    两阶段逼近滤波边沿（公用）。
    Phase 1 — 粗搜：大步向外走，直到 delta ≤ coarse_threshold
    Phase 2 — 精调：delta>0 继续向外，delta<0 回退，|delta| ≤ fine_threshold 收敛

    coarse_step_factor: 粗搜步长倍率（3dB 用 1，60dB 用 1.5）
    fine_step_divisor:  精调步长 = rbw / divisor（3dB 用 200，60dB 用 100）
    settle_time_s:      每次调频后等待信号稳定的时间
    coarse_threshold:   粗搜停止阈值（3dB 用 0.1 dB，60dB 用 1.0 dB）
    fine_threshold:     精调收敛阈值（3dB 用 0.05 dB，60dB 用 0.5 dB）
    """
    max_steps = 200

    # ---- Phase 1: 粗搜 ----
    step = rbw / 20 * coarse_step_factor
    freq = carrier_freq_hz
    consecutive_failures = 0
    for i in range(max_steps):
        test_freq = freq + direction * step
        sig_gen.set_freq(test_freq)
        _wait_opc(sig_gen, min_sleep=0.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=settle_time_s)
        try:
            delta = spec_an.marker_read_y()
        except Exception as e:
            consecutive_failures += 1
            logger.warning("粗搜 %s侧读取失败: %s，尝试恢复（第 %d 次连续失败）",
                           label, e, consecutive_failures)
            spec_an.clear_status()
            if consecutive_failures >= MAX_CONSECUTIVE_READ_FAILURES:
                raise RuntimeError(
                    f"{label}侧粗搜连续 {consecutive_failures} 次读取失败，中止搜索"
                ) from e
            continue
        consecutive_failures = 0
        freq = test_freq
        if delta > coarse_threshold:
            continue
        logger.info("  粗搜 %s侧: %.1f Hz (delta=%.3f, %d 步)", label, freq, delta, i + 1)
        break
    else:
        logger.warning("  %s侧粗搜未收敛（%.1f Hz）", label, freq)

    # ---- Phase 2: 精调 ----
    step = rbw / fine_step_divisor
    consecutive_failures = 0
    for i in range(max_steps):
        try:
            delta = spec_an.marker_read_y()
        except Exception as e:
            consecutive_failures += 1
            logger.warning("精调 %s侧读取失败: %s，尝试恢复（第 %d 次连续失败）",
                           label, e, consecutive_failures)
            spec_an.clear_status()
            if consecutive_failures >= MAX_CONSECUTIVE_READ_FAILURES:
                raise RuntimeError(
                    f"{label}侧精调连续 {consecutive_failures} 次读取失败，中止搜索"
                ) from e
            continue
        consecutive_failures = 0
        if abs(delta) <= fine_threshold:
            logger.info("  精调 %s侧收敛: %.1f Hz (delta=%.3f)", label, freq, delta)
            return freq
        if delta > 0:
            freq += direction * step          # 还需向外
        else:
            freq -= direction * step          # 跨过了，回退
        sig_gen.set_freq(freq)
        _wait_opc(sig_gen, min_sleep=0.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=settle_time_s)
    logger.warning("  %s侧精调结束: %.1f Hz", label, freq)
    return freq


def cal_rbw(spec_an, sig_gen, carrier_freq_hz=config.DEFAULT_CARRIER, rbw_list=None):
    """
    分辨力带宽 (RBW) 准确性验证

    方法：信号源功率先降 3dB 做 peak → delta 参考，
    再恢复功率（delta≈+3dB），调频率使 SA 滤波器衰减 3dB（delta≈0），
    找到 -3dB 点，两侧频率差即为实测 RBW。
    """
    if rbw_list is None:
        rbw_list = config.DEFAULT_RBW_LIST

    _init_signal_gen(sig_gen, power_dbm=-21, freq_hz=carrier_freq_hz,
                     preset_s=0.0, settle_s=3.0)

    def _measure_point(rbw):
        # 批量下发配置，最后一次性等待扫描完成（替代逐条 sleep）
        spec_an.preset()
        spec_an.set_ref_level(-20)
        spec_an.set_vertical_scale(1)
        spec_an.set_center_freq(carrier_freq_hz)
        spec_an.set_span(3 * rbw)
        spec_an.set_rbw(rbw)
        spec_an.set_detector_mode_sample()
        _wait_sweep(spec_an, min_sleep=2.0)

        # 参考：SG=-24 dBm，peak search → delta 参考
        sig_gen.set_power(-24)
        sig_gen.set_freq(carrier_freq_hz)
        _wait_opc(sig_gen, min_sleep=1.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=0.5)
        spec_an.peak_search()
        spec_an.set_marker_delta()
        # 恢复 SG 到 -21 dBm（+3dB），等待 trace 稳定
        sig_gen.set_power(-21)
        sig_gen.set_freq(carrier_freq_hz)
        _wait_opc(sig_gen, min_sleep=1.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=1.0)

        # 查找 -3dB 点（公用 _find_edge），阈值收紧：粗搜 0.1 dB，精调 0.05 dB
        f_left = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, -1, "左",
                            coarse_threshold=0.1, fine_threshold=0.05)

        # 测完一侧，SG 回到载波，避免残留数据影响另一侧
        sig_gen.set_freq(carrier_freq_hz)
        _wait_opc(sig_gen, min_sleep=1.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=0.5)

        f_right = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, 1, "右",
                             coarse_threshold=0.1, fine_threshold=0.05)

        measured_bw = f_right - f_left
        error_pct = 100 * (measured_bw - rbw) / rbw
        logger.info("  设定 %s Hz，实测 3dB 带宽 = %.1f Hz (误差 %+.1f%%)",
                    rbw, measured_bw, error_pct)
        return measured_bw

    try:
        results = _collect_points(rbw_list, _measure_point, "RBW 校准",
                                  describe=lambda rbw: f"测量 RBW={rbw} Hz")
    except Exception:
        sig_gen.rf_off()
        raise
    sig_gen.rf_off()
    return results


def cal_bw60(spec_an, sig_gen, carrier_freq_hz=config.DEFAULT_CARRIER, rbw_list=None):
    """
    -60 dB 带宽测量。

    方法：SG 先降 60dB（-61 dBm）做 peak → delta 参考，
    再恢复到 -1 dBm（delta≈+60dB），调频率使 SA 滤波器衰减 60dB（delta≈0）。
    通过 VBW 分档降噪，不使用 Trace 平均。
    """
    if rbw_list is None:
        rbw_list = config.DEFAULT_BW60_LIST

    _init_signal_gen(sig_gen, power_dbm=-1, freq_hz=carrier_freq_hz,
                     preset_s=0.0, settle_s=3.0)

    def _measure_point(rbw):
        # 调频后固定等待 1s 兜底，保证 marker 读到新数据
        settle_s = 1.0
        # 批量下发配置，最后一次性等待扫描完成
        spec_an.preset()
        spec_an.set_ref_level(0)
        spec_an.set_vertical_scale(10)
        spec_an.set_center_freq(carrier_freq_hz)
        spec_an.set_span(20 * rbw)
        spec_an.set_rbw(rbw)
        # 视频带宽分档降噪
        if rbw <= 100:
            vbw = 10
        elif rbw <= 10000:
            vbw = 100
        else:
            vbw = 1000
        spec_an.set_vbw(vbw)
        spec_an.set_detector_mode_sample()
        _wait_sweep(spec_an, min_sleep=settle_s)   # 等待第一轮扫频稳定

        # 参考：SG=-61 dBm → peak → delta（弱信号，需足够稳定时间）
        sig_gen.set_power(-61)
        sig_gen.set_freq(carrier_freq_hz)
        _wait_opc(sig_gen, min_sleep=settle_s, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=0.5)
        spec_an.peak_search()
        spec_an.set_marker_delta()
        # 恢复 SG 到 -1 dBm（+60dB），等待 trace 稳定
        sig_gen.set_power(-1)
        sig_gen.set_freq(carrier_freq_hz)      # 确保 SG 回到载波
        _wait_opc(sig_gen, min_sleep=settle_s, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=settle_s)

        f_left = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, -1, "左",
                            coarse_step_factor=1.5, fine_step_divisor=100,
                            settle_time_s=settle_s)

        # 测完一侧，SG 回到载波 + 等待扫频稳定，避免残留数据影响另一侧
        sig_gen.set_freq(carrier_freq_hz)
        _wait_opc(sig_gen, min_sleep=settle_s, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=0.5)

        f_right = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, 1, "右",
                             coarse_step_factor=1.5, fine_step_divisor=100,
                             settle_time_s=settle_s)

        bw = f_right - f_left
        logger.info("  -60 dB 带宽 = %.1f Hz (设定 RBW=%s Hz)", bw, rbw)
        return bw

    try:
        results = _collect_points(rbw_list, _measure_point, "-60 dB 带宽校准",
                                  describe=lambda rbw: f"测量 -60 dB 带宽 (RBW={rbw} Hz)")
    except Exception:
        sig_gen.rf_off()
        raise
    sig_gen.rf_off()
    return results


def cal_rbw_switch(spec_an, sig_gen, carrier_freq_hz=config.DEFAULT_CARRIER, rbw_list=None,
                   ref_rbw=config.DEFAULT_RBW_SWITCH_REF,
                   span_ratio=config.DEFAULT_SPAN_RATIO,
                   ref_level_dbm=config.DEFAULT_RBW_SWITCH_REF_LEVEL,
                   atten_db=config.DEFAULT_ATTEN,
                   sg_power_dbm=config.DEFAULT_RBW_SWITCH_SG_POWER,
                   settle_s=0.5):
    """
    分辨力带宽转换影响（JJF1396 6.12）。

    图 5 连接：信号源射频输出 → 频谱分析仪射频输入。
    6.12.2 信号源频率 = 频谱仪校准信号频率，电平 -20 dBm；
    6.12.3 频谱仪中心频率 = 校准信号频率，参考电平 -15 dBm，输入衰减 10 dB，
           RBW = 30 kHz，扫频宽度 = S/RBW × RBW（S/RBW 取 5~10），VBW/扫描时间自动；
    6.12.4 打开峰值标记，再打开标记增量功能（在基准 RBW 的峰值上建立 Δ 参考）；
    6.12.5 改变 RBW，同时以固定 S/RBW 比率改变扫频宽度，记录标记增量峰值；
    6.12.6 按附录 A 表 A.11 逐个 RBW 重复上述切换。

    每次切换后用 peak_search 把增量标记移到当前峰值，读得的 marker Y 即
    “标记增量峰值”：理想情况下切换 RBW 不改变幅度，Δ 应为 0 dB，偏差即转换影响。

    返回 {rbw_hz: delta_db}。基准 RBW 自身那一行应接近 0 dB（自参考校验点）。
    """
    if rbw_list is None:
        rbw_list = config.DEFAULT_RBW_SWITCH_LIST

    # 6.12.2 配置信号源（频率 = 校准信号频率，电平 -20 dBm）
    _init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 6.12.3 频谱仪基准状态：RBW = ref_rbw，Span = S/RBW × RBW
    _init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_vbw_auto()                    # 视频带宽自动（扫描时间保持自动耦合）
    spec_an.set_rbw(ref_rbw)
    spec_an.set_span(span_ratio * ref_rbw)
    _wait_sweep(spec_an, min_sleep=1.0)

    # 6.12.4 峰值标记 → 标记增量：Δ 参考建立在基准 RBW 的峰值电平上
    spec_an.peak_search()
    _sleep(0.5)
    spec_an.set_marker_delta()
    _sleep(0.5)

    def _measure_point(rbw):
        # 6.12.5 改变 RBW，同时按固定 S/RBW 改变扫频宽度
        spec_an.set_rbw(rbw)
        spec_an.set_span(span_ratio * rbw)
        _wait_sweep(spec_an, min_sleep=settle_s)
        spec_an.peak_search()                 # 增量标记移到当前峰值 → 标记增量峰值
        _sleep(0.3)
        delta = spec_an.marker_read_y()
        logger.info("  RBW %s Hz（Span %.0f Hz）→ 标记增量峰值 %.3f dB",
                    rbw, span_ratio * rbw, delta)
        return delta

    try:
        results = _collect_points(rbw_list, _measure_point, "分辨力带宽转换影响",
                                  describe=lambda rbw: f"切换到 RBW={rbw} Hz")
    except Exception:
        sig_gen.rf_off()
        raise
    sig_gen.rf_off()
    return results


def _align_peak_to_center(spec_an, sig_gen, center_freq, span, align_span):
    """
    按 span 成比例缩放的峰值对中校准。

    频谱仪/信号源晶振频率偏差使标称相同频率不落在频谱仪中心，且频谱仪
    对中精度受显示分辨率（窗口/采样点数）限制。对小 span，固定窗口
    （如缩到 10 kHz）不够，必须将校准窗口按 span 的 1000×→100×→10×
    逐级缩小（起窗取 max(1000×span, align_span) 以保证能捕获晶振偏差），
    每级 peak_search + set_marker_to_center，使最终对中精度与待测 span
    相称（例如 span=10 Hz 时窗口缩至 1000/100/10 Hz 量级）。
    """
    start = max(1000 * span, align_span)
    windows = []
    w = start
    while w >= 10 * span:
        windows.append(w)
        w /= 10

    sig_gen.set_freq(center_freq)
    spec_an.set_center_freq(center_freq)
    for window in windows:
        spec_an.set_span(window)
        spec_an.set_rbw(max(1.0, window / 10))
        _wait_sweep(spec_an, min_sleep=2.0)   # 等窗口扫描完成再找峰
        spec_an.peak_search()
        _sleep(1)
        spec_an.set_marker_to_center()
        _sleep(1)


def cal_sweep_width(spec_an, sig_gen, span, ref_level_dbm=0, sg_power_dbm=-1,
                    align_threshold=1e5, align_span=1e6):
    """
    扫频宽度准确性验证。

    设置两个已知频点，用 marker 读取频谱仪显示的频率并求差值，
    与理论差值 0.8*span 比较：
      span ≤ 1 GHz：中心频率 1 GHz，频点为 1 GHz ± 0.4*span
      span > 1 GHz：中心频率 span/2，频点为 0.1*span 与 0.9*span

    小 span（< align_threshold）先做峰值对中预处理：按 span 的
    1000×→100×→10× 逐级缩小窗口对中，最后在测量 span 下用测量 RBW
    再对中一次，抵消频谱仪/信号源晶振频率偏差并保证峰值位于中心；
    同时设置 RBW = span/20 以分辨两个峰值。

    相对误差 δ = (频率差 - 0.8*span) / (0.8*span)
    被校扫频宽度 = 频率差 / 0.8
    """
    expected_diff = 0.8 * span

    if span <= 1e9:
        center = 1e9
        f1 = center - 0.4 * span
        f2 = center + 0.4 * span
    else:
        center = span / 2
        f1 = 0.1 * span
        f2 = 0.9 * span

    # 1. 配置信号源
    _init_signal_gen(sig_gen, power_dbm=sg_power_dbm)

    # 2. 配置频谱仪
    _init_spec_an(spec_an)
    spec_an.set_ref_level(ref_level_dbm)

    # 3. 小 span 预处理：按 span 比例逐级缩小窗口对中，抵消晶振频率偏差
    aligned_center = None
    if span < align_threshold:
        _align_peak_to_center(spec_an, sig_gen, center, span, align_span)
        spec_an.set_span(span)
        spec_an.set_rbw(max(1.0, span / 20))
        _wait_sweep(spec_an, min_sleep=_settle_time(span))
        # 在测量 span 下最终对中，保证峰值位于中心
        spec_an.peak_search()
        _sleep(1)
        spec_an.set_marker_to_center()
        _sleep(1)
        aligned_center = spec_an.marker_read_x()
        logger.info("  晶振偏差预处理: 逐级对中至 10×span，最终显示中心 %.2f Hz（与标称中心偏差 %+.1f Hz）",
                    aligned_center, aligned_center - center)
    else:
        spec_an.set_center_freq(center)
        spec_an.set_span(span)
        _wait_sweep(spec_an, min_sleep=2.0)

    # 4. 依次置信号源频率，用 marker 读取显示频率
    def _read_display_freq(sg_freq):
        sig_gen.set_freq(sg_freq)
        _wait_opc(sig_gen, min_sleep=0.0, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=_settle_time(span))
        spec_an.peak_search()
        _sleep(1)
        return spec_an.marker_read_x()

    f1_disp = _read_display_freq(f1)
    f2_disp = _read_display_freq(f2)
    freq_diff = f2_disp - f1_disp

    delta = (freq_diff - expected_diff) / expected_diff
    corrected_width = freq_diff / 0.8

    logger.info("  频点1: %.0f Hz → 显示 %.2f Hz", f1, f1_disp)
    logger.info("  频点2: %.0f Hz → 显示 %.2f Hz", f2, f2_disp)
    logger.info("  频率差: %.2f Hz（理论 0.8×span = %.2f Hz）", freq_diff, expected_diff)
    logger.info("  相对误差 δ: %+.2f %%", 100 * delta)
    logger.info("  被校扫频宽度: %.2f Hz", corrected_width)

    sig_gen.rf_off()
    return {
        "span": span,
        "center": center,
        "f1": f1,
        "f2": f2,
        "f1_display": f1_disp,
        "f2_display": f2_disp,
        "freq_diff": freq_diff,
        "delta": delta,
        "corrected_width": corrected_width,
        "aligned_center": aligned_center,
    }


def cal_log_scale(spec_an, sig_gen, carrier_freq_hz=50e6, scale_db_per_div=1,
                  points=None, ref_level_dbm=0, atten_db=10, span_hz=10e3,
                  rbw_hz=1e3, vbw_hz=30, sg_power_dbm=-1,
                  target_peak_dbm=0.0, tolerance_db=0.2, settle_s=2.0):
    """
    对数刻度（垂直刻度）准确性验证。

    模式：
      scale_db_per_div=1  ：垂直刻度 1 dB/div，SG 按 1 dB 步进衰减，
                             默认校准点 1~9 dB
      scale_db_per_div=10 ：垂直刻度 10 dB/div，SG 按 10 dB 步进衰减，
                             默认校准点 10~80 dB

    流程：配置频谱仪与信号源 → 迭代调整 SG 电平使峰值 = target（±容差）→
    打开 marker delta → 逐点衰减 SG，记录 marker delta 读数。
    """
    if scale_db_per_div == 1:
        if points is None:
            points = config.cal_point_defaults(
                "log-scale-1db", config.DEFAULT_LOG_SCALE_1DB_POINTS)
    elif scale_db_per_div == 10:
        if points is None:
            points = config.cal_point_defaults(
                "log-scale-10db", config.DEFAULT_LOG_SCALE_10DB_POINTS)
    else:
        raise ValueError(f"不支持的垂直刻度: {scale_db_per_div} dB/div（仅支持 1 或 10）")

    # 1. 配置信号源
    _init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪
    _init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_vbw(vbw_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_vertical_scale(scale_db_per_div)
    _wait_sweep(spec_an, min_sleep=2.0)

    # 3. 调整 SG 输出，使峰值 = target_peak_dbm ± tolerance_db
    current_power = sg_power_dbm
    peak = None
    for _ in range(6):
        spec_an.peak_search()
        _sleep(1)
        peak = spec_an.marker_read_y()
        error = target_peak_dbm - peak
        if abs(error) <= tolerance_db:
            break
        current_power += error
        sig_gen.set_power(current_power)
        _wait_opc(sig_gen, min_sleep=0.2, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
    logger.info("  峰值调整至 %.2f dBm（SG 电平 %.2f dBm）", peak, current_power)

    # 4. 打开 marker delta，以当前峰值位置为参考
    spec_an.set_marker_delta()
    _sleep(1)

    # 5. 逐点衰减，记录 marker delta
    def _measure_point(point):
        sig_gen.set_power(current_power - point)
        _wait_opc(sig_gen, min_sleep=0.2, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
        delta = spec_an.marker_read_y()
        logger.info("  衰减 %d dB → marker delta = %.3f dB（偏差 %+.3f dB）",
                    point, delta, delta - (-point))
        return delta

    try:
        results = _collect_points(points, _measure_point, "对数刻度校准",
                                  describe=lambda p: f"衰减 {p} dB 读数")
    except Exception:
        sig_gen.rf_off()
        raise
    sig_gen.rf_off()
    return {"scale_db_per_div": scale_db_per_div, "results": results}


def cal_linear_scale(spec_an, sig_gen, carrier_freq_hz=50e6, points=None,
                     ref_level_dbm=0, atten_db=10, span_hz=10e3, rbw_hz=3e3,
                     sg_power_dbm=-1, target_peak_mv=223.6, tolerance_mv=0.2,
                     mv_per_unit=1000.0, settle_s=2.0):
    """
    线性刻度（电压）准确性验证。

    0 dBm 在 50Ω 下对应 223.6 mV。先调整信号源电平使频谱仪线性显示峰值
    = target_peak_mv（默认 223.6 mV）± tolerance_mv，再按校准点逐级衰减
    信号源，测量对应峰值电平 Vm（mV），与理论值
    Vn = 1000*sqrt(0.05*10^(-A/10))（mV）比较。

    mv_per_unit：marker 读数换算为 mV 的系数。线性刻度下 marker 通常返回
    V（默认系数 1000）；若仪器直接返回 mV，请传 1。
    """
    if points is None:
        points = config.cal_point_defaults("linear-scale", config.DEFAULT_LINEAR_SCALE_POINTS)

    # 1. 配置信号源
    _init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪（垂直刻度线性模式）
    _init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_y_scale_type("LIN")
    _wait_sweep(spec_an, min_sleep=2.0)

    # 3. 调整 SG 电平，使峰值 = target_peak_mv ± tolerance_mv
    current_power = sg_power_dbm
    peak_mv = None
    for _ in range(6):
        spec_an.peak_search()
        _sleep(1)
        peak_mv = spec_an.marker_read_y() * mv_per_unit
        if abs(peak_mv - target_peak_mv) <= tolerance_mv:
            break
        if peak_mv <= 0:
            current_power += 10
        else:
            current_power += 20 * math.log10(target_peak_mv / peak_mv)
        sig_gen.set_power(current_power)
        _wait_opc(sig_gen, min_sleep=0.2, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
    logger.info("  峰值调整至 %.3f mV（SG 电平 %.2f dBm）", peak_mv, current_power)

    # 4. 逐点衰减，直接读取 marker 值（改变电平不导致频率偏移，无需重新找峰值）
    def _measure_point(point):
        sig_gen.set_power(current_power - point)
        _wait_opc(sig_gen, min_sleep=0.2, timeout_s=SG_OPC_TIMEOUT_S)
        _wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
        vm = spec_an.marker_read_y() * mv_per_unit
        vn = 1000.0 * math.sqrt(0.05 * 10 ** (-point / 10.0))
        rel_err_pct = (vm - vn) / target_peak_mv * 100.0
        logger.info("  衰减 %d dB → Vm = %.3f mV（理论 Vn = %.3f mV，相对误差 %+.3f%%）",
                    point, vm, vn, rel_err_pct)
        return {
            "measured_mv": vm,
            "theoretical_mv": vn,
            "relative_error_pct": rel_err_pct,
        }

    try:
        results = _collect_points(points, _measure_point, "线性刻度校准",
                                  describe=lambda p: f"衰减 {p} dB 读数")
    except Exception:
        sig_gen.rf_off()
        raise
    sig_gen.rf_off()
    return {"results": results, "adjusted_power_dbm": current_power}
