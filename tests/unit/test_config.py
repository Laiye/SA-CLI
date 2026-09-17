"""config.py 的单元测试：默认校准点优先级与 JSON 数据目录解析。"""

import os

from sa_cli import config


def test_cal_point_defaults_from_config():
    assert config.cal_point_defaults("phase-noise", []) == [100, 1000, 10000, 100000]
    assert config.cal_point_defaults("rbw", []) == [
        100, 1000, 3000, 10000, 30000, 100000, 300000, 1000000,
    ]
    assert config.cal_point_defaults("bw60", []) == [
        100, 1000, 3000, 10000, 30000, 100000, 300000, 1000000,
    ]
    assert config.cal_point_defaults("sweep-width", []) == [
        100, 1000, 10000, 100000, 1000000, 10000000, 100000000, 1000000000,
    ]
    assert config.cal_point_defaults("log-scale-1db", []) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert config.cal_point_defaults("log-scale-10db", []) == [10, 20, 30, 40, 50, 60, 70, 80]
    assert config.cal_point_defaults("rbw-switch", []) == [
        100, 300, 1000, 3000, 10000, 30000, 100000, 300000, 1000000,
    ]
    assert config.cal_point_defaults("freq-reading", []) == [
        1000000, 10000000, 100000000, 1000000000, 10000000000, 26500000000,
    ]


def test_cal_point_defaults_fallback_for_unknown_command():
    assert config.cal_point_defaults("unknown-item", [1, 2]) == [1, 2]


def test_packaged_defaults_work_outside_repository(tmp_path, monkeypatch):
    monkeypatch.delenv(config.DATA_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.cal_point_defaults("rbw", []) == config.DEFAULT_RBW_LIST


def test_data_override_updates_between_calls(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path))
    path = tmp_path / "cal_points.json"
    for points in ([123], [456]):
        path.write_text(json.dumps({"rbw": points}), encoding="utf-8")
        assert config.cal_point_defaults("rbw", []) == points


def test_missing_override_points_use_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path))
    assert config.cal_point_defaults("rbw", [100]) == [100]
