#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测量结果导出工具（.json / .csv）。"""

import csv
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def validate_output_path(output_path):
    """在连接仪器之前校验输出格式和父目录。"""
    ext = os.path.splitext(output_path)[1].lower()
    if ext not in (".json", ".csv"):
        raise ValueError(f"不支持的输出格式: {ext}（请使用 .json 或 .csv）")
    if not os.path.isdir(os.path.dirname(os.path.abspath(output_path))):
        raise ValueError("输出目录不存在")
    if os.path.isdir(output_path):
        raise ValueError("输出路径不能为目录")
    return ext


def export_results(output_path, data):
    """同目录临时文件写入完成后原子替换，失败时保留已有结果。"""
    ext = validate_output_path(output_path)
    fd, temporary = tempfile.mkstemp(prefix=".sa-cli-", dir=os.path.dirname(os.path.abspath(output_path)))
    os.close(fd)
    try:
        if ext == ".json":
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        else:
            _export_csv(temporary, data)
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logger.info("结果已导出: %s", output_path)


def _export_csv(output_path, data):
    rows = _csv_rows(data)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _csv_rows(data):
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        metadata = {key: value for key, value in data.items() if key != "results"}
        metadata.setdefault("partial", False)
        rows = [{**row, **metadata} for row in data["results"]]
    elif isinstance(data, list):
        rows = data
    else:
        rows = [data]
    if not rows or not isinstance(rows[0], dict):
        raise ValueError("CSV 导出需要 dict 行数据（请传入 results 列表或 dict 列表）")
    return rows
