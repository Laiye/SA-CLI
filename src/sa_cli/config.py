#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""默认配置：可通过环境变量覆盖仪器地址，通过 cal_points.json 配置默认校准点。"""

import json
import os
from importlib import resources

from sa_cli.validation import validate_points

CAL_POINTS_FILE = "cal_points.json"
DATA_DIR_ENV = "SA_CLI_DATA_DIR"

DEFAULT_SG_ADDR = "GPIB0::19::INSTR"
DEFAULT_SA_ADDR = "GPIB0::18::INSTR"

DEFAULT_PN_CARRIER = 1e9
DEFAULT_CARRIER = 50e6
DEFAULT_REF_LEVEL = 0
DEFAULT_ATTEN = 10
DEFAULT_AVERAGE_COUNT = 8
DEFAULT_SG_POWER = -1
DEFAULT_ALIGN_THRESHOLD = 1e5
DEFAULT_ALIGN_SPAN = 1e6

# 分辨力带宽转换影响（JJF1396 6.12）默认参数
DEFAULT_RBW_SWITCH_REF = 30e3      # 基准 RBW（6.12.3 规定 30 kHz）
DEFAULT_SPAN_RATIO = 10.0          # 扫频宽度 / RBW 比率（6.12.3 规定 5~10）
DEFAULT_RBW_SWITCH_REF_LEVEL = -15  # 参考电平 (dBm)
DEFAULT_RBW_SWITCH_SG_POWER = -20   # 信号源电平 (dBm)

# 频率读数（以频谱仪 marker 显示值为准）默认参数
DEFAULT_FREQ_READING_REF_LEVEL = 0   # 参考电平 (dBm)
DEFAULT_FREQ_READING_SG_POWER = -1   # 信号源输出电平 (dBm)
DEFAULT_SWEEP_POINTS = 1001          # 采样点数 Points（显示分辨力 = span/(Points-1)）
# 各频率点对应的三个扫频宽度 (Hz)
FREQ_READING_SPANS_LOW = [10e3, 100e3, 1e6]    # 1 MHz 点：0.01 / 0.1 / 1 MHz
FREQ_READING_SPANS_MID = [100e3, 1e6, 10e6]    # 10 MHz 点：0.1 / 1 / 10 MHz
FREQ_READING_SPANS_HIGH = [1e6, 10e6, 100e6]   # ≥100 MHz 点：1 / 10 / 100 MHz

# 参考电平校准（以 -10 dBm 为参考点）默认参数
DEFAULT_REF_LEVEL_POINTS = [-10, 0, 10, -20, -30, -40, -50, -60, -70]
DEFAULT_REF_LEVEL_REFERENCE = -10.0       # 参考点 (dBm)
DEFAULT_REF_LEVEL_CARRIER = 50e6          # 校准信号频率 (Hz)
DEFAULT_REF_LEVEL_SPAN = 10e3             # 扫频宽度 (Hz)
DEFAULT_REF_LEVEL_RBW = 1e3               # 分辨力带宽 (Hz)
DEFAULT_REF_LEVEL_VBW = 30                # 视频带宽 (Hz)
DEFAULT_REF_LEVEL_VSCALE = 1              # 垂直刻度 (dB/div)
DEFAULT_REF_LEVEL_SG_POWER = -11.0        # 信号源初始输出电平 (dBm)
DEFAULT_REF_LEVEL_TOLERANCE = 0.5         # 参考建立容差 (dB)
DEFAULT_REF_LEVEL_MAX_SG_POWER = 10.0     # 信号源输出安全上限 (dBm)
DEFAULT_REF_LEVEL_AVERAGE_BELOW = -55.0   # 低于该参考电平时启用平均 (dBm)
DEFAULT_REF_LEVEL_STEP_DELAY = 1.0        # 两台仪器调整之间的间隔 (s)

# 输入衰减器转换影响（以 10 dB 输入衰减为参考点）默认参数
DEFAULT_ATTEN_POINTS = [10, 20, 30, 40, 50, 60, 70]   # 输入衰减校准点 (dB)
DEFAULT_ATTEN_REF_POINT = 10.0            # 参考点输入衰减 (dB)
DEFAULT_ATTEN_CARRIER = 50e6              # 校准信号频率 (Hz)
DEFAULT_ATTEN_SPAN = 500.0                # 扫频宽度 (Hz)
DEFAULT_ATTEN_RBW = 1e3                   # 分辨力带宽 (Hz)
DEFAULT_ATTEN_VSCALE = 1                  # 垂直显示刻度 (dB/div)
DEFAULT_ATTEN_REF_LEVEL = -60.0           # 参考点参考电平 (dBm)
DEFAULT_ATTEN_SG_POWER = -62.0            # 信号源初始输出电平 (dBm)
DEFAULT_ATTEN_TOLERANCE = 0.5             # 参考建立容差 (dB)
DEFAULT_ATTEN_MAX_SG_POWER = 10.0         # 信号源输出安全上限 (dBm)
DEFAULT_ATTEN_AVERAGE_COUNT = 10          # 迹线平均次数
DEFAULT_ATTEN_STEP_DELAY = 1.0            # 衰减/参考电平调整与信号源调整之间的间隔 (s)

# 各校准项目的默认校准点（代码兜底，cal_points.json 优先）
DEFAULT_PHASE_NOISE_OFFSETS = [100, 1000, 10e3, 100e3]
DEFAULT_RBW_LIST = [100, 1000, 3000, 10e3, 30e3, 100e3, 300e3, 1e6]
DEFAULT_BW60_LIST = [100, 1000, 3000, 10e3, 30e3, 100e3, 300e3, 1e6]
DEFAULT_SWEEP_SPANS = [100, 1000, 10e3, 100e3, 1e6, 10e6, 100e6, 1e9]
DEFAULT_LOG_SCALE_1DB_POINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
DEFAULT_LOG_SCALE_10DB_POINTS = [10, 20, 30, 40, 50, 60, 70, 80]
DEFAULT_LINEAR_SCALE_POINTS = [4, 8, 12, 16, 20]
DEFAULT_RBW_SWITCH_LIST = [100, 300, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3, 1e6]
DEFAULT_FREQ_READING_FREQS = [1e6, 10e6, 100e6, 1000e6, 10000e6, 26500e6]

def open_data(filename):
    """打开显式路径、环境变量目录或随包分发的数据；不依赖工作目录。"""
    filename = os.fspath(filename)
    if os.path.isabs(filename):
        return open(filename, "r", encoding="utf-8")
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return open(os.path.join(override, filename), "r", encoding="utf-8")
    if hasattr(resources, "files"):
        return resources.files("sa_cli.data").joinpath(filename).open("r", encoding="utf-8")
    return resources.open_text("sa_cli.data", filename, encoding="utf-8")


def _load_cal_points():
    try:
        with open_data(CAL_POINTS_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"{CAL_POINTS_FILE} 解析错误: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"{CAL_POINTS_FILE} 顶层必须为 JSON 对象")
    return data


_PACKAGED_CAL_POINTS = None


def cal_points():
    """读取各校准项目默认校准点（cal_points.json）。

    未设置 SA_CLI_DATA_DIR 时缓存随包分发的内容，避免构造解析器时为每个命令
    重复解析（一次 --help 会查询多个命令的默认点）；设置了覆盖目录时每次实时
    读取，保证运行期修改配置文件立即生效。
    """
    global _PACKAGED_CAL_POINTS
    if os.environ.get(DATA_DIR_ENV):
        return _load_cal_points()
    if _PACKAGED_CAL_POINTS is None:
        _PACKAGED_CAL_POINTS = _load_cal_points()
    return _PACKAGED_CAL_POINTS


def cal_point_defaults(command, fallback, validate=validate_points):
    """返回该校准项目的默认校准点：cal_points.json 配置优先，否则用代码兜底。

    validate 用于校验点列表（默认要求有限正数；参考电平等含 0/负值的项目
    可传入 validate_levels）。
    """
    points = cal_points().get(command)
    return validate(fallback if points is None else points, command)


def sg_addr():
    return os.environ.get("SA_CLI_SG_ADDR", DEFAULT_SG_ADDR)


def sa_addr():
    return os.environ.get("SA_CLI_SA_ADDR", DEFAULT_SA_ADDR)


