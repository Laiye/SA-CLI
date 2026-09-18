#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参考电平校准：以 -10 dBm 为参考点核对各参考电平下的幅度读数。"""

import logging

from sa_cli import config
from sa_cli.errors import MeasurementError
from sa_cli.validation import validate_levels

from . import common

logger = logging.getLogger(__name__)


def cal_ref_level(spec_an, sig_gen, levels=None,
                  carrier_freq_hz=config.DEFAULT_REF_LEVEL_CARRIER,
                  span_hz=config.DEFAULT_REF_LEVEL_SPAN,
                  rbw_hz=config.DEFAULT_REF_LEVEL_RBW,
                  vbw_hz=config.DEFAULT_REF_LEVEL_VBW,
                  reference_level_dbm=config.DEFAULT_REF_LEVEL_REFERENCE,
                  sg_power_dbm=config.DEFAULT_REF_LEVEL_SG_POWER,
                  tolerance_db=config.DEFAULT_REF_LEVEL_TOLERANCE,
                  max_sg_power_dbm=config.DEFAULT_REF_LEVEL_MAX_SG_POWER,
                  average_count=1,
                  average_below_dbm=config.DEFAULT_REF_LEVEL_AVERAGE_BELOW,
                  step_delay_s=config.DEFAULT_REF_LEVEL_STEP_DELAY,
                  settle_s=0.5):
    """
    参考电平校准（-10 dBm 为参考点）。

    频谱仪：中心频率 = 校准信号频率（默认 50 MHz）、扫频宽度 10 kHz、
    参考电平 -10 dBm、RBW 1 kHz、VBW 30 Hz、垂直刻度 1 dB/div；
    信号源：输出频率 = 校准信号频率、初始输出约 -11 dBm。

    1. 建立参考：峰值标记读数应约为信号源初始电平 ±容差（默认 0.5 dB），
       否则微调信号源直至满足，并记录实际设置值 S0；以当前峰值打开 Delta
       标记（Δ 读数应为 0）；
    2. 逐点：Δ = Lref - (-10)，S = S0 + Δ；**Lref 高于当前参考电平时先设频谱仪
       参考电平再设信号源，低于时先设信号源再设频谱仪**；两次调整之间间隔
       step_delay_s（默认 1 s），避免两台仪器同时切换造成读数未稳定；
       稳定后 peak_search 把 Delta 活动标记移到新峰值，读取 Δmeas；
    3. 弱信号点（Lref ≤ average_below_dbm）在 average_count > 1 时启用 trace 平均
       （逐次触发扫描填满平均窗口）；
    4. 安全：任一需要的信号源输出超过 max_sg_power_dbm 即中止（保护频谱仪输入）。

    返回 {Lref: {"s0_dbm", "sg_power_dbm", "expected_delta_db",
                 "measured_delta_db", "error_db"}}，其中 error_db = Δmeas - Δ。
    """
    levels = validate_levels(
        config.DEFAULT_REF_LEVEL_POINTS if levels is None else levels, "参考电平")
    if average_count < 1:
        raise ValueError("平均次数必须 ≥ 1")

    # 1. 配置信号源与频谱仪
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_vbw(vbw_hz)
    spec_an.set_vertical_scale(config.DEFAULT_REF_LEVEL_VSCALE)
    spec_an.set_ref_level(reference_level_dbm)
    common._wait_sweep(spec_an, min_sleep=1.0)

    # 2. 建立参考：微调信号源使峰值读数 ≈ 初始电平 ±容差，记录实际 S0
    current_power = sg_power_dbm
    peak = None
    for _ in range(6):
        spec_an.peak_search()
        spec_an.sleep(0.5)
        peak = spec_an.marker_read_y()
        error = sg_power_dbm - peak
        if abs(error) <= tolerance_db:
            break
        current_power += error
        if current_power > max_sg_power_dbm:
            sig_gen.rf_off()
            raise MeasurementError(
                f"参考建立需要信号源输出 {current_power:.2f} dBm，"
                f"超过安全上限 {max_sg_power_dbm:.2f} dBm")
        sig_gen.set_power(current_power)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
    else:
        if not sig_gen.dry_run:
            sig_gen.rf_off()
            raise MeasurementError(
                f"参考电平建立未收敛: 峰值读数 {peak} dBm，"
                f"目标 {sg_power_dbm} dBm ±{tolerance_db} dB")
    s0_dbm = current_power
    logger.info("  参考建立: 峰值读数 %.3f dBm → 信号源实际设置 S0 = %.3f dBm", peak, s0_dbm)

    spec_an.set_marker_delta()      # Δ 参考 = 当前峰值（Delta 读数应为 0）
    spec_an.sleep(0.5)

    def _set_ref_level(level):
        spec_an.set_ref_level(level)
        common._wait_sweep(spec_an, min_sleep=settle_s)

    def _set_sg_power(power):
        sig_gen.set_power(power)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)

    def _set_averaging(enabled):
        if enabled:
            spec_an.set_average_count(average_count)
            spec_an.set_trace_average_on()
        else:
            spec_an.set_trace_average_off()

    def _pause():
        """两台仪器调整之间的间隔，避免同时切换导致读数未稳定。"""
        if step_delay_s > 0:
            spec_an.sleep(step_delay_s)

    results = {}
    progress = common.PointProgress(len(levels))
    current_ref_level = reference_level_dbm
    averaging_on = False
    for index, level in enumerate(levels, start=1):
        label = f"参考电平 {level:g} dBm"
        try:
            progress.begin(index, label)
            delta = level - reference_level_dbm
            power = s0_dbm + delta
            if power > max_sg_power_dbm:
                raise MeasurementError(
                    f"参考电平 {level:g} dBm 需要信号源输出 {power:.2f} dBm，"
                    f"超过安全上限 {max_sg_power_dbm:.2f} dBm")

            # 调整顺序：升高参考电平先设频谱仪，降低则先设信号源；
            # 两次调整之间留出间隔（默认 1 s）
            if level > current_ref_level:
                _set_ref_level(level)
                _pause()
                _set_sg_power(power)
            elif level < current_ref_level:
                _set_sg_power(power)
                _pause()
                _set_ref_level(level)
            current_ref_level = level

            # 弱信号点平均（仅在状态变化时切换）
            want_average = average_count > 1 and level <= average_below_dbm
            if want_average != averaging_on:
                _set_averaging(want_average)
                averaging_on = want_average

            common._wait_sweep(spec_an, min_sleep=settle_s)
            if averaging_on:
                for _ in range(average_count - 1):      # 填满平均窗口
                    common._wait_sweep(spec_an, min_sleep=0.0)

            spec_an.peak_search()                       # Delta 活动标记移到新峰值
            spec_an.sleep(0.3)
            measured = spec_an.marker_read_y()
        except MeasurementError:
            sig_gen.rf_off()
            raise
        except Exception as e:
            sig_gen.rf_off()
            raise MeasurementError(
                f"参考电平 {level:g} dBm 测量失败（已完成 {len(results)}/{len(levels)} 点）: {e}",
                partial_results=results,
            ) from e

        error_db = measured - delta
        results[level] = {
            "s0_dbm": s0_dbm,
            "sg_power_dbm": power,
            "expected_delta_db": delta,
            "measured_delta_db": measured,
            "error_db": error_db,
        }
        logger.info("  Lref %+g dBm → S = %.2f dBm，Δ = %+.2f dB，Δmeas = %+.3f dB（误差 %+.3f dB）",
                    level, power, delta, measured, error_db)

    if averaging_on:
        spec_an.set_trace_average_off()
    sig_gen.rf_off()
    return results
