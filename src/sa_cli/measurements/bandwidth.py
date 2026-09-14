"""RBW 与 -60 dB 带宽测量及边沿搜索。"""
import logging

from sa_cli import config
from . import common

logger = logging.getLogger(__name__)

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
        common._wait_opc(sig_gen, min_sleep=0.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=settle_time_s)
        try:
            delta = spec_an.marker_read_y()
        except Exception as e:
            consecutive_failures += 1
            logger.warning("粗搜 %s侧读取失败: %s，尝试恢复（第 %d 次连续失败）",
                           label, e, consecutive_failures)
            spec_an.clear_status()
            if consecutive_failures >= common.MAX_CONSECUTIVE_READ_FAILURES:
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
        raise RuntimeError(f"{label}侧粗搜未收敛: freq={freq}, delta={delta}, steps={max_steps}")

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
            if consecutive_failures >= common.MAX_CONSECUTIVE_READ_FAILURES:
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
        common._wait_opc(sig_gen, min_sleep=0.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=settle_time_s)
    raise RuntimeError(f"{label}侧精调未收敛: freq={freq}, delta={delta}, steps={max_steps}")


def cal_rbw(spec_an, sig_gen, carrier_freq_hz=config.DEFAULT_CARRIER, rbw_list=None):
    """
    分辨力带宽 (RBW) 准确性验证

    方法：信号源功率先降 3dB 做 peak → delta 参考，
    再恢复功率（delta≈+3dB），调频率使 SA 滤波器衰减 3dB（delta≈0），
    找到 -3dB 点，两侧频率差即为实测 RBW。
    """
    if rbw_list is None:
        rbw_list = config.DEFAULT_RBW_LIST

    common._init_signal_gen(sig_gen, power_dbm=-21, freq_hz=carrier_freq_hz,
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
        common._wait_sweep(spec_an, min_sleep=2.0)

        # 参考：SG=-24 dBm，peak search → delta 参考
        sig_gen.set_power(-24)
        sig_gen.set_freq(carrier_freq_hz)
        common._wait_opc(sig_gen, min_sleep=1.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=0.5)
        spec_an.peak_search()
        spec_an.set_marker_delta()
        # 恢复 SG 到 -21 dBm（+3dB），等待 trace 稳定
        sig_gen.set_power(-21)
        sig_gen.set_freq(carrier_freq_hz)
        common._wait_opc(sig_gen, min_sleep=1.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=1.0)

        # 查找 -3dB 点（公用 _find_edge），阈值收紧：粗搜 0.1 dB，精调 0.05 dB
        f_left = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, -1, "左",
                            coarse_threshold=0.1, fine_threshold=0.05)

        # 测完一侧，SG 回到载波，避免残留数据影响另一侧
        sig_gen.set_freq(carrier_freq_hz)
        common._wait_opc(sig_gen, min_sleep=1.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=0.5)

        f_right = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, 1, "右",
                             coarse_threshold=0.1, fine_threshold=0.05)

        measured_bw = f_right - f_left
        error_pct = 100 * (measured_bw - rbw) / rbw
        logger.info("  设定 %s Hz，实测 3dB 带宽 = %.1f Hz (误差 %+.1f%%)",
                    rbw, measured_bw, error_pct)
        return measured_bw

    results = common._collect_points(rbw_list, _measure_point, "RBW 校准",
                                     describe=lambda rbw: f"测量 RBW={rbw} Hz")
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

    common._init_signal_gen(sig_gen, power_dbm=-1, freq_hz=carrier_freq_hz,
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
        common._wait_sweep(spec_an, min_sleep=settle_s)   # 等待第一轮扫频稳定

        # 参考：SG=-61 dBm → peak → delta（弱信号，需足够稳定时间）
        sig_gen.set_power(-61)
        sig_gen.set_freq(carrier_freq_hz)
        common._wait_opc(sig_gen, min_sleep=settle_s, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=0.5)
        spec_an.peak_search()
        spec_an.set_marker_delta()
        # 恢复 SG 到 -1 dBm（+60dB），等待 trace 稳定
        sig_gen.set_power(-1)
        sig_gen.set_freq(carrier_freq_hz)      # 确保 SG 回到载波
        common._wait_opc(sig_gen, min_sleep=settle_s, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=settle_s)

        f_left = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, -1, "左",
                            coarse_step_factor=1.5, fine_step_divisor=100,
                            settle_time_s=settle_s)

        # 测完一侧，SG 回到载波 + 等待扫频稳定，避免残留数据影响另一侧
        sig_gen.set_freq(carrier_freq_hz)
        common._wait_opc(sig_gen, min_sleep=settle_s, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=0.5)

        f_right = _find_edge(sig_gen, spec_an, carrier_freq_hz, rbw, 1, "右",
                             coarse_step_factor=1.5, fine_step_divisor=100,
                             settle_time_s=settle_s)

        bw = f_right - f_left
        logger.info("  -60 dB 带宽 = %.1f Hz (设定 RBW=%s Hz)", bw, rbw)
        return bw

    results = common._collect_points(rbw_list, _measure_point, "-60 dB 带宽校准",
                                     describe=lambda rbw: f"测量 -60 dB 带宽 (RBW={rbw} Hz)")
    return results


