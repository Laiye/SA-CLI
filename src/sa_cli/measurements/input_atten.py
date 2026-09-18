#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入衰减器转换影响校准：以 10 dB 输入衰减为参考点核对各衰减档的幅度读数。"""

import logging

from sa_cli import config
from sa_cli.errors import MeasurementError
from sa_cli.validation import validate_attenuations

from . import common

logger = logging.getLogger(__name__)


def cal_input_atten(spec_an, sig_gen, attens=None,
                    carrier_freq_hz=config.DEFAULT_ATTEN_CARRIER,
                    span_hz=config.DEFAULT_ATTEN_SPAN,
                    rbw_hz=config.DEFAULT_ATTEN_RBW,
                    vscale_db=config.DEFAULT_ATTEN_VSCALE,
                    ref_level_dbm=config.DEFAULT_ATTEN_REF_LEVEL,
                    ref_atten_db=config.DEFAULT_ATTEN_REF_POINT,
                    sg_power_dbm=config.DEFAULT_ATTEN_SG_POWER,
                    tolerance_db=config.DEFAULT_ATTEN_TOLERANCE,
                    max_sg_power_dbm=config.DEFAULT_ATTEN_MAX_SG_POWER,
                    average_count=config.DEFAULT_ATTEN_AVERAGE_COUNT,
                    step_delay_s=config.DEFAULT_ATTEN_STEP_DELAY,
                    settle_s=0.5):
    """
    输入衰减器转换影响校准（10 dB 输入衰减为参考点）。

    频谱仪：中心频率 = 校准信号频率（默认 50 MHz）、扫频宽度 500 Hz、RBW 1 kHz、
    垂直刻度 1 dB/div、参考电平 -60 dBm、迹线平均（默认 10 次）、手动输入衰减；
    信号源：输出频率 = 校准信号频率、初始输出约 -62 dBm。

    1. 建立参考：峰值读数应约为信号源初始电平 ±容差（默认 0.5 dB），否则微调
       信号源直至满足，并记录实际设置值 S0（后续一律按实际 S0 计算，不固定用
       -62 dBm）；以当前峰值打开 Delta 标记（Δ 读数应为 0）；
    2. 逐点：参考电平 Lref = ref_level + (A - ref_atten)、信号源 S = S0 + (A - ref_atten)，
       理论 Δ = A - ref_atten；稳定后**不做 peak search**，直接读取 Delta 标记读数 ΔLm，
       误差 = ΔLm - 理论 Δ；
    3. 调整顺序（保护频谱仪输入）：衰减升高时先加输入衰减 → 再抬高参考电平 →
       最后加信号源输出；衰减降低时先降信号源输出 → 再降低参考电平 → 最后减
       输入衰减；频谱仪侧调整与信号源调整之间间隔 step_delay_s（默认 1 s）；
    4. 每次改变设置后填满平均窗口再读数，保证读数取自当前设置；
    5. 安全：任一需要的信号源输出超过 max_sg_power_dbm 即中止。

    结束后频谱仪保持手动衰减（不恢复自动衰减），信号源关闭 RF。
    返回 {A: {"ref_level_dbm", "sg_power_dbm", "s0_dbm", "expected_delta_db",
              "measured_delta_db", "error_db"}}。
    """
    attens = validate_attenuations(
        config.DEFAULT_ATTEN_POINTS if attens is None else attens, "输入衰减")
    if average_count < 1:
        raise ValueError("平均次数必须 ≥ 1")
    ref_atten_db = float(ref_atten_db)

    # 1. 频谱仪与信号源初始设置（手动衰减档，避免改参考电平时被自动衰减改写）
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_vertical_scale(vscale_db)
    spec_an.set_attenuation_auto_off()
    spec_an.set_attenuation(ref_atten_db)
    spec_an.set_ref_level(ref_level_dbm)
    if average_count > 1:
        spec_an.set_average_count(average_count)
        spec_an.set_trace_average_on()

    def _settle_average(min_sleep=settle_s):
        """等一次扫描并按平均次数填满平均窗口，使读数取自当前设置。"""
        common._wait_sweep(spec_an, min_sleep=min_sleep)
        for _ in range(max(0, average_count - 1)):
            common._wait_sweep(spec_an, min_sleep=0.0)

    _settle_average(min_sleep=1.0)

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
        _settle_average(min_sleep=min(settle_s, 0.5))
    else:
        if not sig_gen.dry_run:
            sig_gen.rf_off()
            raise MeasurementError(
                f"参考建立未收敛: 峰值读数 {peak} dBm，"
                f"目标 {sg_power_dbm} dBm ±{tolerance_db} dB")
    s0_dbm = current_power
    logger.info("  参考建立: 输入衰减 %g dB / 参考电平 %g dBm，峰值读数 %.3f dBm → "
                "信号源实际设置 S0 = %.3f dBm", ref_atten_db, ref_level_dbm, peak, s0_dbm)

    spec_an.set_marker_delta()      # Δ 参考 = 当前峰值（Delta 读数应为 0）
    spec_an.sleep(0.5)

    def _set_attenuation(atten):
        spec_an.set_attenuation(atten)
        common._wait_sweep(spec_an, min_sleep=settle_s)

    def _set_ref_level(level):
        spec_an.set_ref_level(level)
        common._wait_sweep(spec_an, min_sleep=settle_s)

    def _set_sg_power(power):
        sig_gen.set_power(power)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)

    def _pause():
        """频谱仪侧调整与信号源调整之间的间隔，避免同时切换导致读数未稳定。"""
        if step_delay_s > 0:
            spec_an.sleep(step_delay_s)

    results = {}
    progress = common.PointProgress(len(attens))
    current_atten = ref_atten_db
    current_level = ref_level_dbm
    current_power = s0_dbm
    for index, atten in enumerate(attens, start=1):
        label = f"输入衰减 {atten:g} dB"
        try:
            progress.begin(index, label)
            delta = atten - ref_atten_db
            level = ref_level_dbm + delta
            power = s0_dbm + delta
            if power > max_sg_power_dbm:
                raise MeasurementError(
                    f"输入衰减 {atten:g} dB 需要信号源输出 {power:.2f} dBm，"
                    f"超过安全上限 {max_sg_power_dbm:.2f} dBm")

            # 衰减升高：先加输入衰减 → 再抬高参考电平 → 最后加信号源输出；
            # 衰减降低：先降信号源输出 → 再降低参考电平 → 最后减输入衰减
            if atten > current_atten:
                _set_attenuation(atten)
                _set_ref_level(level)
                _pause()
                _set_sg_power(power)
            elif atten < current_atten:
                _set_sg_power(power)
                _pause()
                _set_ref_level(level)
                _set_attenuation(atten)
            elif level != current_level or power != current_power:
                # 同一衰减档下仅参考电平/信号源变化（非默认点表时可能出现）
                if level > current_level:
                    _set_ref_level(level)
                    _pause()
                    _set_sg_power(power)
                else:
                    _set_sg_power(power)
                    _pause()
                    _set_ref_level(level)
            current_atten, current_level, current_power = atten, level, power

            _settle_average()
            spec_an.sleep(0.3)
            measured = spec_an.marker_read_y()      # Delta 标记直接读数（不做 peak search）
        except MeasurementError:
            sig_gen.rf_off()
            raise
        except Exception as e:
            sig_gen.rf_off()
            raise MeasurementError(
                f"输入衰减 {atten:g} dB 测量失败（已完成 {len(results)}/{len(attens)} 点）: {e}",
                partial_results=results,
            ) from e

        error_db = measured - delta
        results[atten] = {
            "atten_db": atten,
            "ref_level_dbm": level,
            "sg_power_dbm": power,
            "s0_dbm": s0_dbm,
            "expected_delta_db": delta,
            "measured_delta_db": measured,
            "error_db": error_db,
        }
        logger.info("  衰减 %g dB（Lref %+g dBm，S = %.2f dBm）→ Δ = %+.2f dB，"
                    "ΔLm = %+.3f dB（误差 %+.3f dB）",
                    atten, level, power, delta, measured, error_db)

    if average_count > 1:
        spec_an.set_trace_average_off()
    sig_gen.rf_off()
    return results
