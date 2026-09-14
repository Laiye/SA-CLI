"""单边带相位噪声测量。"""
import logging
import math

from . import common

logger = logging.getLogger(__name__)

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
    common._init_signal_gen(sig_gen, power_dbm=0, freq_hz=carrier_freq_hz)

    # 2. 配置频谱仪，测量载波功率
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_span(span)
    spec_an.set_rbw(rbw)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    common._wait_sweep(spec_an, min_sleep=2.0)
    spec_an.peak_search()
    spec_an.sleep(0.5)
    carrier_power = spec_an.marker_read_y()
    logger.info("  载波功率: %.2f dBm", carrier_power)

    # 3. 零扫宽测量 ± 频偏处噪声功率
    def _measure_offset(side_name, sign):
        # 将频偏点移至 center
        spec_an.set_marker_normal()
        spec_an.sleep(1.0)
        spec_an.peak_search()
        spec_an.sleep(3.0)
        spec_an.set_marker_delta()
        spec_an.sleep(2.0)
        spec_an.marker_set_x(sign * offset_hz)
        spec_an.sleep(2.0)
        spec_an.set_marker_to_center()         # center = 载波 ± 频偏
        spec_an.sleep(2.0)

        # 零扫宽，VBW 降噪 + Trace 平均后读取
        spec_an.set_span(0)
        spec_an.set_rbw(rbw)
        spec_an.set_vbw(10)                    # VBW=10Hz 降噪
        if use_average:
            spec_an.set_average_count(average_count)
            spec_an.set_trace_average_on()
            spec_an.sleep(2.0)                        # 等待平均窗口填充
        common._wait_sweep(spec_an, min_sleep=1.0)    # 等本次扫描完成后再读数

        delta = spec_an.marker_read_y()
        logger.info("  %s侧 %d Hz 偏移: Δ=%.2f dB", side_name, offset_hz, delta)

        # 恢复
        if use_average:
            spec_an.set_trace_average_off()
        spec_an.set_vbw_auto()                 # VBW 改回自动
        spec_an.set_center_freq(carrier_freq_hz)
        spec_an.sleep(1.0)
        spec_an.set_span(span)
        common._wait_sweep(spec_an, min_sleep=2.0)
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
    return phase_noise


