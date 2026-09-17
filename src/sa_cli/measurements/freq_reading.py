#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""频率读数校准：读数以频谱仪 marker 显示值为准。"""

import logging

from sa_cli import config
from sa_cli.errors import MeasurementError
from sa_cli.validation import validate_points

from . import common

logger = logging.getLogger(__name__)


def _fmt_hz(value):
    """频率的可读文本（用于进度与日志）。"""
    if value >= 1e9:
        return f"{value / 1e9:g} GHz"
    if value >= 1e6:
        return f"{value / 1e6:g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:g} kHz"
    return f"{value:g} Hz"


def spans_for(freq_hz):
    """按规范选取三个扫频宽度。

    1 MHz 频率点 → 0.01 / 0.1 / 1 MHz；10 MHz 频率点 → 0.1 / 1 / 10 MHz；
    其余（≥100 MHz）频率点 → 1 / 10 / 100 MHz。
    """
    if freq_hz <= 1e6:
        return list(config.FREQ_READING_SPANS_LOW)
    if freq_hz <= 10e6:
        return list(config.FREQ_READING_SPANS_MID)
    return list(config.FREQ_READING_SPANS_HIGH)


def display_resolution(span_hz, points_count):
    """显示分辨力 = span / (Points - 1)（采样点 1001 时即 span/1000）。"""
    if points_count < 2:
        raise ValueError("采样点数必须 ≥ 2")
    return span_hz / (points_count - 1)


def to_displayed(reading_hz, center_hz, span_hz, resolution_hz):
    """把指令读数按显示分辨力量化到显示栅格。

    栅格原点为扫频起点 center - span/2，仪器显示分辨力与采样点数一致时，
    显示值只能落在栅格点上（相邻点间隔即分辨力）。
    """
    left_edge = center_hz - span_hz / 2
    steps = round((reading_hz - left_edge) / resolution_hz)
    return left_edge + steps * resolution_hz


def cal_freq_reading(spec_an, sig_gen, freq_list=None, ref_level_dbm=None,
                     sg_power_dbm=None, points_count=None, settle_s=0.5):
    """
    频率读数校准。

    每个校准频率点：
    1. 频谱仪中心频率 = 校准频率点，参考电平 0 dBm；
    2. 信号源输出频率 = 校准频率点，电平 -1 dBm，输出开启；
    3. 依次设置三个扫频宽度（见 spans_for），peak search 后读取 marker 频率读数；
    4. 仪器采样点数 Points（默认 1001）决定显示分辨力 span/(Points-1)：指令读数的
       分辨力与显示不一致，因此先把读数按该分辨力量化到显示栅格，再与标称频率比较。

    返回 {(freq_hz, span_hz): {"reading_hz", "displayed_hz", "error_hz",
          "raw_error_hz", "relative_ppm", "resolution_hz"}}；
    error_hz 基于显示值（结论以此为准），raw_error_hz 为指令读数与标称频率之差。
    """
    if freq_list is None:
        freq_list = config.DEFAULT_FREQ_READING_FREQS
    freq_list = validate_points(freq_list, "校准频率点")
    if ref_level_dbm is None:
        ref_level_dbm = config.DEFAULT_FREQ_READING_REF_LEVEL
    if sg_power_dbm is None:
        sg_power_dbm = config.DEFAULT_FREQ_READING_SG_POWER
    if points_count is None:
        points_count = config.DEFAULT_SWEEP_POINTS
    if points_count < 2:
        raise ValueError("采样点数必须 ≥ 2")

    plan = [(freq, span) for freq in freq_list for span in spans_for(freq)]

    # 1. 配置信号源（首点频率、-1 dBm、输出开启）
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=freq_list[0])

    # 2. 配置频谱仪（参考电平 0 dBm、marker 置普通模式）
    common._init_spec_an(spec_an)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_marker_normal()

    results = {}
    progress = common.PointProgress(len(plan))
    current_freq = freq_list[0]
    for index, (freq_hz, span_hz) in enumerate(plan, start=1):
        label = f"频率 {_fmt_hz(freq_hz)}，扫频宽度 {_fmt_hz(span_hz)}"
        try:
            progress.begin(index, label)
            if freq_hz != current_freq:
                sig_gen.set_freq(freq_hz)
                common._wait_opc(sig_gen, min_sleep=0.2, timeout_s=common.SG_OPC_TIMEOUT_S)
                current_freq = freq_hz
            spec_an.set_center_freq(freq_hz)
            spec_an.set_span(span_hz)
            spec_an.set_sweep_points(points_count)
            common._wait_sweep(spec_an, min_sleep=settle_s)
            spec_an.peak_search()
            spec_an.sleep(0.3)
            reading = spec_an.marker_read_x()
        except MeasurementError:
            raise
        except Exception as e:
            raise MeasurementError(
                f"频率读数测量失败于 {label}（已完成 {len(results)}/{len(plan)} 点）: {e}",
                partial_results=results,
            ) from e

        resolution = display_resolution(span_hz, points_count)
        displayed = to_displayed(reading, freq_hz, span_hz, resolution)
        error = displayed - freq_hz
        results[(freq_hz, span_hz)] = {
            "reading_hz": reading,
            "displayed_hz": displayed,
            "error_hz": error,
            "raw_error_hz": reading - freq_hz,
            "relative_ppm": error / freq_hz * 1e6,
            "resolution_hz": resolution,
        }
        logger.info("  marker 读数 %.1f Hz → 显示 %.1f Hz（分辨力 %.1f Hz，偏差 %+.1f Hz）",
                    reading, displayed, resolution, error)

    return results
