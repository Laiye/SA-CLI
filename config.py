#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""默认配置：可通过环境变量覆盖仪器地址，通过 cal_points.json 配置默认校准点。"""

import json
import math
import os

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

# 各校准项目的默认校准点（代码兜底，cal_points.json 优先）
DEFAULT_PHASE_NOISE_OFFSETS = [100, 1000, 10e3, 100e3]
DEFAULT_RBW_LIST = [100, 1000, 3000, 10e3, 30e3, 100e3, 300e3, 1e6]
DEFAULT_BW60_LIST = [100, 1000, 3000, 10e3, 30e3, 100e3, 300e3, 1e6]
DEFAULT_SWEEP_SPANS = [100, 1000, 10e3, 100e3, 1e6, 10e6, 100e6, 1e9]
DEFAULT_LOG_SCALE_1DB_POINTS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
DEFAULT_LOG_SCALE_10DB_POINTS = [10, 20, 30, 40, 50, 60, 70, 80]
DEFAULT_LINEAR_SCALE_POINTS = [4, 8, 12, 16, 20]
DEFAULT_RBW_SWITCH_LIST = [100, 300, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3, 1e6]

_cal_points = None


def data_dir():
    """JSON 指令集 / 校准点所在目录。

    查找顺序：环境变量 SA_CLI_DATA_DIR → 模块所在目录（editable 安装即仓库根）→
    当前工作目录；以目录下存在 spectrum_analyzer.json 判定为数据目录。这样
    `pip install .`（非 editable）时也可通过 SA_CLI_DATA_DIR 或将 JSON 放在工作目录使用。
    """
    env_dir = os.environ.get(DATA_DIR_ENV)
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [env_dir] if env_dir else []
    candidates.extend([module_dir, os.getcwd()])
    for candidate in candidates:
        if os.path.exists(os.path.join(candidate, "spectrum_analyzer.json")):
            return candidate
    return env_dir or module_dir


def _load_cal_points():
    path = os.path.join(data_dir(), CAL_POINTS_FILE)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise ValueError(f"{CAL_POINTS_FILE} 解析错误: {e}")
    if not isinstance(data, dict):
        raise ValueError(f"{CAL_POINTS_FILE} 顶层必须为 JSON 对象")
    return data


def cal_points():
    """读取各校准项目默认校准点（cal_points.json）。"""
    global _cal_points
    if _cal_points is None:
        _cal_points = _load_cal_points()
    return _cal_points


def cal_point_defaults(command, fallback):
    """返回该校准项目的默认校准点：cal_points.json 配置优先，否则用代码兜底。"""
    points = cal_points().get(command)
    return validate_points(fallback if points is None else points, command)


def sg_addr():
    return os.environ.get("SA_CLI_SG_ADDR", DEFAULT_SG_ADDR)


def sa_addr():
    return os.environ.get("SA_CLI_SA_ADDR", DEFAULT_SA_ADDR)


def validate_points(points, name="校准点"):
    """校准点必须为非空、不重复的有限正数列表。"""
    if not isinstance(points, (list, tuple)) or not points:
        raise ValueError(f"{name} 必须为非空数值列表")
    for value in points:
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"{name} 必须包含有限正数: {value!r}")
    if len(set(points)) != len(points):
        raise ValueError(f"{name} 不允许重复校准点")
    return list(points)
