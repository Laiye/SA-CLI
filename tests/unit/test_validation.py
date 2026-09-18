"""validation.py 的单元测试：数值、校准点与电平列表校验。"""

import pytest

from sa_cli.validation import (finite_float, validate_attenuations, validate_levels,
                               validate_points)


def test_validate_levels_allows_zero_and_negative():
    """参考电平等电平列表允许 0 与负值。"""
    assert validate_levels([-10, 0, 10, -70]) == [-10, 0, 10, -70]
    assert validate_levels((-10, -20)) == [-10, -20]


@pytest.mark.parametrize("levels", [
    [], "10", [float("nan")], [float("inf")], [float("-inf")],
    [True], ["-10"], [None], [-10, -10],
])
def test_validate_levels_rejects_invalid(levels):
    with pytest.raises(ValueError):
        validate_levels(levels)


def test_validate_levels_rejects_empty_message():
    with pytest.raises(ValueError, match="非空"):
        validate_levels([])
    with pytest.raises(ValueError, match="重复"):
        validate_levels([-10, -10])


def test_validate_points_still_requires_positive():
    assert validate_points([100, 1000]) == [100, 1000]
    with pytest.raises(ValueError):
        validate_points([0])
    with pytest.raises(ValueError):
        validate_points([-10])
    with pytest.raises(ValueError):
        validate_points([100, 100.0])


def test_validate_attenuations_allows_zero_rejects_negative():
    """输入衰减点允许 0（不衰减），拒绝负数与重复点。"""
    assert validate_attenuations([0, 10, 20]) == [0, 10, 20]
    with pytest.raises(ValueError, match="负数"):
        validate_attenuations([-1, 10])
    with pytest.raises(ValueError, match="重复"):
        validate_attenuations([10, 10])
    with pytest.raises(ValueError, match="非空"):
        validate_attenuations([])


def test_finite_float_rejects_non_finite():
    assert finite_float("1.5") == 1.5
    assert finite_float(2) == 2.0
    for bad in ("nan", "inf", "-inf", "1e999"):
        with pytest.raises(ValueError):
            finite_float(bad)
