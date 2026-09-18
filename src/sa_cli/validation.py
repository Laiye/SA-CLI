"""数值与校准点校验。"""
import math

def finite_float(value):
    """转换为有限浮点数，拒绝 NaN、无穷和溢出。"""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("数值必须有限")
    return number


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


def validate_levels(levels, name="参考电平"):
    """电平列表（dBm）：非空、有限、不重复；允许 0 与负值。"""
    if not isinstance(levels, (list, tuple)) or not levels:
        raise ValueError(f"{name} 必须为非空数值列表")
    for value in levels:
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ValueError(f"{name} 必须包含有限数值: {value!r}")
    if len(set(levels)) != len(levels):
        raise ValueError(f"{name} 不允许重复点")
    return list(levels)
