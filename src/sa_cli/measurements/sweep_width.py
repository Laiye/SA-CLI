"""扫频宽度测量与峰值对中。"""
import logging

from . import common

logger = logging.getLogger(__name__)

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
        common._wait_sweep(spec_an, min_sleep=2.0)   # 等窗口扫描完成再找峰
        spec_an.peak_search()
        spec_an.sleep(1)
        spec_an.set_marker_to_center()
        spec_an.sleep(1)


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
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm)

    # 2. 配置频谱仪
    common._init_spec_an(spec_an)
    spec_an.set_ref_level(ref_level_dbm)

    # 3. 小 span 预处理：按 span 比例逐级缩小窗口对中，抵消晶振频率偏差
    aligned_center = None
    if span < align_threshold:
        _align_peak_to_center(spec_an, sig_gen, center, span, align_span)
        spec_an.set_span(span)
        spec_an.set_rbw(max(1.0, span / 20))
        common._wait_sweep(spec_an, min_sleep=common._settle_time(span))
        # 在测量 span 下最终对中，保证峰值位于中心
        spec_an.peak_search()
        spec_an.sleep(1)
        spec_an.set_marker_to_center()
        spec_an.sleep(1)
        aligned_center = spec_an.marker_read_x()
        logger.info("  晶振偏差预处理: 逐级对中至 10×span，最终显示中心 %.2f Hz（与标称中心偏差 %+.1f Hz）",
                    aligned_center, aligned_center - center)
    else:
        spec_an.set_center_freq(center)
        spec_an.set_span(span)
        common._wait_sweep(spec_an, min_sleep=2.0)

    # 4. 依次置信号源频率，用 marker 读取显示频率
    def _read_display_freq(sg_freq):
        sig_gen.set_freq(sg_freq)
        common._wait_opc(sig_gen, min_sleep=0.0, timeout_s=common.SG_OPC_TIMEOUT_S)
        common._wait_sweep(spec_an, min_sleep=common._settle_time(span))
        spec_an.peak_search()
        spec_an.sleep(1)
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


