"""对数与线性刻度校准。"""
import logging
import math

from sa_cli import config
from . import common

logger = logging.getLogger(__name__)

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
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_vbw(vbw_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_vertical_scale(scale_db_per_div)
    common._wait_sweep(spec_an, min_sleep=2.0)

    # 3. 调整 SG 输出，使峰值 = target_peak_dbm ± tolerance_db
    current_power = sg_power_dbm
    peak = None
    for _ in range(6):
        spec_an.peak_search()
        spec_an.sleep(1)
        peak = spec_an.marker_read_y()
        error = target_peak_dbm - peak
        if abs(error) <= tolerance_db:
            break
        current_power += error
        sig_gen.set_power(current_power)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
    else:
        if not sig_gen.dry_run:
            raise RuntimeError(f"峰值调整未收敛: peak={peak}, error={error}, steps=6")
    logger.info("  峰值调整至 %.2f dBm（SG 电平 %.2f dBm）", peak, current_power)

    # 4. 打开 marker delta，以当前峰值位置为参考
    spec_an.set_marker_delta()
    spec_an.sleep(1)

    # 5. 逐点衰减，记录 marker delta
    def _measure_point(point):
        sig_gen.set_power(current_power - point)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
        delta = spec_an.marker_read_y()
        logger.info("  衰减 %d dB → marker delta = %.3f dB（偏差 %+.3f dB）",
                    point, delta, delta - (-point))
        return delta

    results = common._collect_points(points, _measure_point, "对数刻度校准",
                                     describe=lambda p: f"衰减 {p} dB 读数")
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
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪（垂直刻度线性模式）
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span_hz)
    spec_an.set_rbw(rbw_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_y_scale_type("LIN")
    common._wait_sweep(spec_an, min_sleep=2.0)

    # 3. 调整 SG 电平，使峰值 = target_peak_mv ± tolerance_mv
    current_power = sg_power_dbm
    peak_mv = None
    for _ in range(6):
        spec_an.peak_search()
        spec_an.sleep(1)
        peak_mv = spec_an.marker_read_y() * mv_per_unit
        if abs(peak_mv - target_peak_mv) <= tolerance_mv:
            break
        if peak_mv <= 0:
            current_power += 10
        else:
            current_power += 20 * math.log10(target_peak_mv / peak_mv)
        sig_gen.set_power(current_power)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
    else:
        if not sig_gen.dry_run:
            raise RuntimeError(f"峰值调整未收敛: peak={peak_mv}, error={peak_mv - target_peak_mv}, steps=6")
    logger.info("  峰值调整至 %.3f mV（SG 电平 %.2f dBm）", peak_mv, current_power)

    # 4. 逐点衰减，直接读取 marker 值（改变电平不导致频率偏移，无需重新找峰值）
    def _measure_point(point):
        sig_gen.set_power(current_power - point)
        common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=min(settle_s, 0.5))
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

    results = common._collect_points(points, _measure_point, "线性刻度校准",
                                     describe=lambda p: f"衰减 {p} dB 读数")
    return {"results": results, "adjusted_power_dbm": current_power}
