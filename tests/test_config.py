#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py 的单元测试：默认校准点优先级与 JSON 数据目录解析。"""

import os

import config


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


def test_cal_point_defaults_fallback_for_unknown_command():
    assert config.cal_point_defaults("unknown-item", [1, 2]) == [1, 2]


# ---------- JSON 数据目录 ----------

def test_data_dir_defaults_to_module_dir():
    assert config.data_dir() == os.path.dirname(os.path.abspath(config.__file__))


def test_data_dir_env_override(tmp_path, monkeypatch):
    (tmp_path / "spectrum_analyzer.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(config.DATA_DIR_ENV, str(tmp_path))
    assert config.data_dir() == str(tmp_path)


def test_data_dir_falls_back_to_cwd(tmp_path, monkeypatch):
    """模块目录无 JSON 时（非 editable 安装场景）回退到当前工作目录。"""
    monkeypatch.delenv(config.DATA_DIR_ENV, raising=False)
    module_dir = tmp_path / "no-json-here"
    module_dir.mkdir()
    monkeypatch.setattr(config, "__file__", str(module_dir / "config.py"))
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "spectrum_analyzer.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(workdir)
    assert config.data_dir() == str(workdir)


def test_data_dir_fallback_when_no_json_anywhere(tmp_path, monkeypatch):
    """所有候选目录都没有 JSON 时，返回模块目录以便报出明确错误。"""
    monkeypatch.delenv(config.DATA_DIR_ENV, raising=False)
    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    monkeypatch.setattr(config, "__file__", str(module_dir / "config.py"))
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()
    monkeypatch.chdir(empty_cwd)
    assert config.data_dir() == str(module_dir)
