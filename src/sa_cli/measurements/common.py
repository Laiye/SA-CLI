#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测量同步、逐点执行和进度报告。"""

import logging

from sa_cli.validation import validate_points
import time

from sa_cli.errors import MeasurementError

logger = logging.getLogger(__name__)

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


def _wait_opc(instr, min_sleep=0.0, timeout_s=OPC_TIMEOUT_S):
    """等待完成；超时或通信失败中止，单次 I/O 受剩余预算限制。"""
    if min_sleep > 0:
        instr.sleep(min_sleep)
    deadline = time.monotonic() + timeout_s
    resource = instr.instr
    original_timeout = resource.timeout if resource is not None else None
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"OPC 等待超时（{timeout_s:g} s）")
            if resource is not None:
                budget_ms = max(1, int(remaining * 1000))
                resource.timeout = (budget_ms if original_timeout is None
                                    else min(original_timeout, budget_ms))
            try:
                done = float(instr.opc()) == 1.0
            except Exception as exc:
                raise RuntimeError("OPC 查询失败，停止当前校准点") from exc
            if time.monotonic() >= deadline:
                raise TimeoutError(f"OPC 等待超时（{timeout_s:g} s）")
            if done:
                return True
            instr.sleep(min(OPC_POLL_S, max(0, deadline - time.monotonic())))
    finally:
        if resource is not None:
            resource.timeout = original_timeout


def _wait_sweep(spec_an, min_sleep=0.0, timeout_s=OPC_TIMEOUT_S):
    """
    等待频谱仪完成一次扫描：切单次扫描 → 触发 :INITiate:IMMediate → *OPC?，
    结束后恢复连续扫描。连续扫描模式下 *OPC? 语义不可靠，必须用单次扫描模式。
    """
    try:
        spec_an.set_sweep_single()
        spec_an.init_sweep()
        return _wait_opc(spec_an, min_sleep=min_sleep, timeout_s=timeout_s)
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
    points = validate_points(points)
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


