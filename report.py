#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测量结果导出工具（.json / .csv）。"""

import csv
import json
import logging
import os

logger = logging.getLogger(__name__)


def export_results(output_path, data):
    """按扩展名导出测量结果（.json / .csv），不支持其他格式时报错。"""
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    elif ext == ".csv":
        _export_csv(output_path, data)
    else:
        raise ValueError(f"不支持的输出格式: {ext}（请使用 .json 或 .csv）")
    logger.info("结果已导出: %s", output_path)


def _export_csv(output_path, data):
    rows = _csv_rows(data)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _csv_rows(data):
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        rows = data["results"]
    elif isinstance(data, list):
        rows = data
    else:
        rows = [data]
    if not rows or not isinstance(rows[0], dict):
        raise ValueError("CSV 导出需要 dict 行数据（请传入 results 列表或 dict 列表）")
    return rows
