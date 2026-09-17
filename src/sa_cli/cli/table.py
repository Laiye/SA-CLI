#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""控制台表格渲染：等宽对齐，兼容中日韩宽字符。"""

import unicodedata


def display_width(text):
    """文本显示宽度：东亚宽/全角字符按 2 列计，其余按 1 列。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
               for char in str(text))


def _pad(text, width, align):
    text = str(text)
    padding = width - display_width(text)
    if padding <= 0:
        return text
    return (" " * padding + text) if align == "right" else (text + " " * padding)


def render_table(headers, rows, aligns=None):
    """渲染管道式表格（表头 + 分隔线 + 数据行）。

    headers: 列标题序列；rows: 行序列（每行长度与 headers 一致）；
    aligns: 每列对齐方式 "left"/"right"（默认全部 left，数值列建议 right）。
    """
    headers = [str(item) for item in headers]
    columns = len(headers)
    if aligns is None:
        aligns = ["left"] * columns
    cells = [[str(cell) for cell in row] for row in rows]
    widths = [display_width(header) for header in headers]
    for row in cells:
        for index in range(columns):
            widths[index] = max(widths[index], display_width(row[index]))

    lines = ["| " + " | ".join(_pad(headers[i], widths[i], aligns[i])
                               for i in range(columns)) + " |",
             "|" + "|".join("-" * (widths[i] + 2) for i in range(columns)) + "|"]
    for row in cells:
        lines.append("| " + " | ".join(_pad(row[i], widths[i], aligns[i])
                                       for i in range(columns)) + " |")
    return "\n".join(lines)
