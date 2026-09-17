"""控制台表格渲染的单元测试。"""

from sa_cli.cli.table import display_width, render_table


def test_display_width_counts_cjk_as_two():
    assert display_width("abc") == 3
    assert display_width("频率") == 4
    assert display_width("RBW (Hz)") == 8


def test_render_table_aligns_columns():
    table = render_table(["a", "bb"], [["1", "x"]])
    lines = table.splitlines()
    assert lines[0] == "| a | bb |"
    assert lines[1] == "|---|----|"
    assert lines[2] == "| 1 | x  |"


def test_render_table_right_alignment():
    table = render_table(["n"], [["1"], ["100"]], aligns=["right"])
    lines = table.splitlines()
    assert lines[0] == "|   n |"
    assert lines[1] == "|-----|"
    assert lines[2] == "|   1 |"
    assert lines[3] == "| 100 |"


def test_render_table_cjk_header_keeps_pipe_alignment():
    """中文表头按 2 列宽计算，表头与数据行的管道位置一致。"""
    table = render_table(["频率", "Span"], [["1 MHz", "1 kHz"]])
    lines = table.splitlines()
    assert display_width(lines[0]) == display_width(lines[2])
    assert lines[1].count("|") == 3


def test_render_table_without_rows():
    table = render_table(["a"], [])
    assert table.splitlines() == ["| a |", "|---|"]


def test_render_table_pads_to_widest_cell():
    table = render_table(["x"], [["1"], ["12345"]], aligns=["right"])
    lines = table.splitlines()
    assert lines[0] == "|     x |"
    assert lines[2] == "|     1 |"
    assert lines[3] == "| 12345 |"
