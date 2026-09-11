#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SA-CLI: 频谱分析仪 & 信号发生器 CLI 控制与测量工具。"""

import argparse
import logging
import sys

import config
import measurements
from instruments import visa_session
from measurements import (MeasurementError, cal_bw60, cal_linear_scale,
                          cal_log_scale, cal_rbw, cal_rbw_switch,
                          cal_ssb_phase_noise, cal_sweep_width)
from report import export_results

logger = logging.getLogger(__name__)


def setup_logging(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def _positive_float(text):
    """argparse type：必须为正数（频率、列表校准点等）。"""
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"必须为正数: {text!r}")
    return value


def _nonneg_float(text):
    """argparse type：不能为负数（衰减、等待时间等）。"""
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"不能为负数: {text!r}")
    return value


def _add_instrument_args(parser):
    parser.add_argument(
        "--sg-addr", type=str, default=config.sg_addr(),
        help=f"信号发生器 VISA 地址（默认 {config.DEFAULT_SG_ADDR}，可用环境变量 SA_CLI_SG_ADDR 覆盖）",
    )
    parser.add_argument(
        "--sa-addr", type=str, default=config.sa_addr(),
        help=f"频谱分析仪 VISA 地址（默认 {config.DEFAULT_SA_ADDR}，可用环境变量 SA_CLI_SA_ADDR 覆盖）",
    )


def _add_output_arg(parser):
    parser.add_argument(
        "--output", type=str, default=None,
        help="导出测量结果到文件（.json 或 .csv）",
    )


def build_parser():
    parser = argparse.ArgumentParser(description="SA-CLI: 频谱分析仪控制与测量工具")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="不连接仪器，打印将发送的 SCPI 命令序列（调试指令集用）",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--verbose", action="store_true", help="输出调试日志")
    common.add_argument(
        "--dry-run", action="store_true",
        help="不连接仪器，打印将发送的 SCPI 命令序列（调试指令集用）",
    )
    subparsers = parser.add_subparsers(dest="command", help="测量命令")

    # ---------- 噪声边带（单边带相位噪声）----------
    pn = subparsers.add_parser(
        "phase-noise", aliases=["pn", "噪声边带"], parents=[common],
        help="单边带相位噪声测量 (dBc/Hz)",
    )
    pn.add_argument(
        "--offset", "-o", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("phase-noise", config.DEFAULT_PHASE_NOISE_OFFSETS),
        help="频偏列表 (Hz)，可传多个，如 100 1000 10E3 100E3；默认读取 cal_points.json",
    )
    pn.add_argument(
        "--carrier", "-c", type=_positive_float, default=config.DEFAULT_PN_CARRIER,
        help="载波频率 (Hz)，默认 1e9 (1 GHz)",
    )
    pn.add_argument(
        "--ref-level", "-r", type=float, default=config.DEFAULT_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    pn.add_argument(
        "--atten", "-a", type=_nonneg_float, default=config.DEFAULT_ATTEN,
        help="衰减 (dB)，默认 10",
    )
    pn.add_argument(
        "--average-count", "-n", type=int, default=config.DEFAULT_AVERAGE_COUNT,
        help="Trace 平均次数，默认 8",
    )
    _add_instrument_args(pn)
    _add_output_arg(pn)

    # ---------- 分辨力带宽 ----------
    rbw = subparsers.add_parser(
        "rbw", aliases=["分辨力带宽"], parents=[common],
        help="分辨力带宽 (RBW) 准确性验证",
    )
    rbw.add_argument(
        "--carrier", "-c", type=_positive_float, default=config.DEFAULT_CARRIER,
        help="载波频率 (Hz)，默认 50e6 (50 MHz)",
    )
    rbw.add_argument(
        "--rbw-list", "-b", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("rbw", config.DEFAULT_RBW_LIST),
        help="待测 RBW 列表 (Hz)，可传多个；默认读取 cal_points.json",
    )
    _add_instrument_args(rbw)
    _add_output_arg(rbw)

    # ---------- -60 dB 带宽 ----------
    bw60 = subparsers.add_parser(
        "bw60", aliases=["带宽60"], parents=[common],
        help="-60 dB 带宽测量",
    )
    bw60.add_argument(
        "--carrier", "-c", type=_positive_float, default=config.DEFAULT_CARRIER,
        help="载波频率 (Hz)，默认 50e6 (50 MHz)",
    )
    bw60.add_argument(
        "--rbw-list", "-b", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("bw60", config.DEFAULT_BW60_LIST),
        help="待测 RBW 列表 (Hz)，可传多个；默认读取 cal_points.json",
    )
    _add_instrument_args(bw60)
    _add_output_arg(bw60)

    # ---------- 分辨力带宽转换影响 ----------
    rsw = subparsers.add_parser(
        "rbw-switch", aliases=["rbw转换影响", "分辨力带宽转换影响"], parents=[common],
        help="分辨力带宽转换影响（JJF1396 6.12）",
    )
    rsw.add_argument(
        "--rbw-list", "-b", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("rbw-switch", config.DEFAULT_RBW_SWITCH_LIST),
        help="待切换的 RBW 列表 (Hz)，可传多个；默认读取 cal_points.json",
    )
    rsw.add_argument(
        "--carrier", "-c", type=_positive_float, default=config.DEFAULT_CARRIER,
        help="校准信号频率 (Hz)，默认 50e6 (50 MHz)",
    )
    rsw.add_argument(
        "--ref-rbw", type=_positive_float, default=config.DEFAULT_RBW_SWITCH_REF,
        help="基准 RBW (Hz)，默认 30k（规范 6.12.3）",
    )
    rsw.add_argument(
        "--span-ratio", type=_positive_float, default=config.DEFAULT_SPAN_RATIO,
        help="扫频宽度 / RBW 比率，默认 10（规范 6.12.3 可取 5~10）",
    )
    rsw.add_argument(
        "--ref-level", "-r", type=float, default=config.DEFAULT_RBW_SWITCH_REF_LEVEL,
        help="参考电平 (dBm)，默认 -15（规范 6.12.3）",
    )
    rsw.add_argument(
        "--atten", "-a", type=_nonneg_float, default=config.DEFAULT_ATTEN,
        help="输入衰减 (dB)，默认 10（规范 6.12.3）",
    )
    rsw.add_argument(
        "--sg-power", type=float, default=config.DEFAULT_RBW_SWITCH_SG_POWER,
        help="信号源电平 (dBm)，默认 -20（规范 6.12.2）",
    )
    rsw.add_argument(
        "--settle", type=_nonneg_float, default=0.5,
        help="每次切换 RBW 后的稳定等待下限 (s)，默认 0.5",
    )
    _add_instrument_args(rsw)
    _add_output_arg(rsw)

    # ---------- 扫频宽度 ----------
    sw = subparsers.add_parser(
        "sweep-width", aliases=["sw", "扫频宽度"], parents=[common],
        help="扫频宽度准确性验证",
    )
    sw.add_argument(
        "--span", "-s", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("sweep-width", config.DEFAULT_SWEEP_SPANS),
        help="待测扫频宽度列表 (Hz)，可传多个校准点；默认读取 cal_points.json",
    )
    sw.add_argument(
        "--ref-level", "-r", type=float, default=config.DEFAULT_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    sw.add_argument(
        "--sg-power", type=float, default=config.DEFAULT_SG_POWER,
        help="信号源电平 (dBm)，默认 -1",
    )
    sw.add_argument(
        "--align-threshold", type=_nonneg_float, default=config.DEFAULT_ALIGN_THRESHOLD,
        help="小 span 峰值对中阈值 (Hz)，span 小于该值启用预处理，默认 100k",
    )
    sw.add_argument(
        "--align-span", type=_nonneg_float, default=config.DEFAULT_ALIGN_SPAN,
        help="对中初始捕获窗口下限 (Hz)，起窗取 max(1000×span, 该值) 后按 1000×→100×→10×span 逐级缩小，默认 1e6",
    )
    _add_instrument_args(sw)
    _add_output_arg(sw)

    # ---------- 对数刻度 ----------
    ls = subparsers.add_parser(
        "log-scale", aliases=["log", "对数刻度"], parents=[common],
        help="对数刻度（垂直刻度）准确性验证",
    )
    ls.add_argument(
        "--scale", type=int, choices=[1, 10], default=1,
        help="垂直刻度模式 (dB/div)：1（1 dB 步进，测 1~9 dB）或 10（10 dB 步进，测 10~80 dB），默认 1",
    )
    ls.add_argument(
        "--carrier", "-c", type=_positive_float, default=50e6,
        help="中心频率 (Hz)，默认 50e6 (50 MHz)",
    )
    ls.add_argument(
        "--points", "-p", type=_positive_float, nargs="+", default=None,
        help="校准点列表 (dB)；默认按模式读取 cal_points.json（1dB: 1~9；10dB: 10~80）",
    )
    ls.add_argument(
        "--ref-level", "-r", type=float, default=config.DEFAULT_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    ls.add_argument(
        "--atten", "-a", type=_nonneg_float, default=config.DEFAULT_ATTEN,
        help="输入衰减 (dB)，默认 10",
    )
    ls.add_argument(
        "--span", type=_positive_float, default=10e3,
        help="扫频宽度 (Hz)，默认 10k",
    )
    ls.add_argument(
        "--rbw", type=_positive_float, default=1e3,
        help="分辨力带宽 (Hz)，默认 1k",
    )
    ls.add_argument(
        "--vbw", type=_positive_float, default=30,
        help="视频带宽 (Hz)，默认 30",
    )
    ls.add_argument(
        "--sg-power", type=float, default=config.DEFAULT_SG_POWER,
        help="信号源电平 (dBm)，默认 -1",
    )
    ls.add_argument(
        "--settle", type=_nonneg_float, default=2.0,
        help="每步衰减后稳定等待 (s)，默认 2",
    )
    _add_instrument_args(ls)
    _add_output_arg(ls)

    # ---------- 线性刻度 ----------
    lin = subparsers.add_parser(
        "linear-scale", aliases=["lin", "线性刻度"], parents=[common],
        help="线性刻度（电压）准确性验证",
    )
    lin.add_argument(
        "--carrier", "-c", type=_positive_float, default=50e6,
        help="中心频率 (Hz)，默认 50e6 (50 MHz)",
    )
    lin.add_argument(
        "--points", "-p", type=_positive_float, nargs="+", default=None,
        help="校准点列表 (dB)，默认读取 cal_points.json（4 8 12 16 20）",
    )
    lin.add_argument(
        "--ref-level", "-r", type=float, default=config.DEFAULT_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    lin.add_argument(
        "--atten", "-a", type=_nonneg_float, default=config.DEFAULT_ATTEN,
        help="输入衰减 (dB)，默认 10",
    )
    lin.add_argument(
        "--span", type=_positive_float, default=10e3,
        help="扫频宽度 (Hz)，默认 10k",
    )
    lin.add_argument(
        "--rbw", type=_positive_float, default=3e3,
        help="分辨力带宽 (Hz)，默认 3k",
    )
    lin.add_argument(
        "--sg-power", type=float, default=config.DEFAULT_SG_POWER,
        help="信号源电平 (dBm)，默认 -1",
    )
    lin.add_argument(
        "--target", type=_positive_float, default=223.6,
        help="线性峰值目标 (mV)，默认 223.6（对应 0 dBm）",
    )
    lin.add_argument(
        "--tolerance", type=_nonneg_float, default=0.2,
        help="峰值容差 (mV)，默认 0.2",
    )
    lin.add_argument(
        "--mv-factor", type=_positive_float, default=1000.0,
        help="marker 读数换算为 mV 的系数，默认 1000（线性刻度返回 V）；若仪器返回 mV 设为 1",
    )
    lin.add_argument(
        "--settle", type=_nonneg_float, default=2.0,
        help="每步衰减后稳定等待 (s)，默认 2",
    )
    _add_instrument_args(lin)
    _add_output_arg(lin)

    return parser


# ======================= 命令注册与统一执行 =======================
# 每个命令注册 run(sig, spec, args) -> 结果行列表、导出附带字段 export_meta(args)，
# 以及可选的 summarize(rows)（结论字段，如最大值/最差点）。
# 中途异常以 MeasurementError 携带已完成点，由 _dispatch 统一导出部分结果。

_COMMAND_SPECS = {}
_ALIAS_TO_CANONICAL = {}


def _register_command(name, aliases=(), export_meta=None, summarize=None):
    """命令注册装饰器：name 为规范名，aliases 为别名（含中文）；
    export_meta 返回导出附带字段，summarize 由结果行计算结论字段。"""

    def _decorator(run_fn):
        _COMMAND_SPECS[name] = {
            "run": run_fn,
            "export_meta": export_meta or (lambda args: {"command": name}),
            "summarize": summarize,
        }
        for alias in aliases:
            _ALIAS_TO_CANONICAL[alias] = name
        return run_fn

    return _decorator


def _rows_rbw(results):
    """原始结果 {rbw: measured} → 导出行（成功与部分结果共用）。"""
    return [
        {"rbw_hz": rbw, "measured_hz": m,
         "error_pct": round(100 * (m - rbw) / rbw, 2)}
        for rbw, m in results.items()
    ]


def _rows_bw60(results):
    return [{"rbw_hz": rbw, "bw60_hz": bw} for rbw, bw in results.items()]


def _rows_log(results):
    """原始结果 {point: delta} → 导出行。"""
    return [
        {"atten_db": point, "expected_db": -point, "marker_delta_db": delta,
         "error_db": round(delta - (-point), 3)}
        for point, delta in results.items()
    ]


def _rows_linear(results):
    """原始结果 {point: vals} → 导出行。"""
    return [
        {"atten_db": point,
         "measured_mv": vals["measured_mv"],
         "theoretical_mv": vals["theoretical_mv"],
         "error_mv": round(vals["measured_mv"] - vals["theoretical_mv"], 3),
         "relative_error_pct": round(vals["relative_error_pct"], 3)}
        for point, vals in results.items()
    ]


def _rows_rbw_switch(results, span_ratio):
    """原始结果 {rbw: delta_db} → 导出行（含该点对应的扫频宽度）。"""
    return [
        {"rbw_hz": rbw, "span_hz": span_ratio * rbw, "delta_db": delta}
        for rbw, delta in results.items()
    ]


def _summarize_rbw_switch(rows):
    """结论字段：转换影响取各切换点 Δ 的最大绝对值。"""
    if not rows:
        return {}
    worst = max(rows, key=lambda r: abs(r["delta_db"]))
    return {
        "max_abs_delta_db": round(abs(worst["delta_db"]), 3),
        "max_abs_delta_at_rbw_hz": worst["rbw_hz"],
    }


def _dispatch(args):
    """会话管理 + 统一导出/部分结果导出的执行骨架。"""
    canonical = _ALIAS_TO_CANONICAL.get(args.command, args.command)
    cmd = _COMMAND_SPECS[canonical]

    def _export_data(rows, partial=False):
        data = {**cmd["export_meta"](args), "results": rows}
        summarize = cmd.get("summarize")
        if summarize:
            data.update(summarize(rows))
        if partial:
            data["partial"] = True
        return data

    with visa_session(args.sg_addr, args.sa_addr, dry_run=args.dry_run) as (sig, spec):
        try:
            rows = cmd["run"](sig, spec, args)
        except MeasurementError as e:
            partial = e.partial_results if e.partial_results is not None else []
            logger.error("测量中断: %s", e)
            if args.output and partial:
                try:
                    export_results(args.output, _export_data(partial, partial=True))
                    logger.info("已导出已完成 %d 个校准点的部分结果: %s",
                                len(partial), args.output)
                except Exception as ex:
                    logger.error("部分结果导出失败: %s", ex)
            return 1
    if args.output:
        export_results(args.output, _export_data(rows))
    return 0


@_register_command("rbw", aliases=("分辨力带宽",),
                   export_meta=lambda args: {"command": "rbw", "carrier_hz": args.carrier,
                                             "rbw_list": args.rbw_list})
def _cmd_rbw(sig, spec, args):
    logger.info("\n===== 分辨力带宽 (RBW) 准确性验证 =====")
    logger.info("  载波频率: %.0f Hz", args.carrier)
    logger.info("  RBW 列表: %s", args.rbw_list)
    logger.info("")
    try:
        results = cal_rbw(spec, sig,
                          carrier_freq_hz=args.carrier,
                          rbw_list=args.rbw_list)
    except MeasurementError as e:
        raise MeasurementError(str(e), partial_results=_rows_rbw(e.partial_results or {})) from e
    logger.info("\n===== 验证结果 =====")
    rows = _rows_rbw(results)
    for row in rows:
        logger.info("  设定 %d Hz → 实测 %.1f Hz (误差 %+.1f%%)",
                    row["rbw_hz"], row["measured_hz"], row["error_pct"])
    return rows


@_register_command("bw60", aliases=("带宽60",),
                   export_meta=lambda args: {"command": "bw60", "carrier_hz": args.carrier,
                                             "rbw_list": args.rbw_list})
def _cmd_bw60(sig, spec, args):
    logger.info("\n===== -60 dB 带宽测量 =====")
    logger.info("  载波频率: %.0f Hz", args.carrier)
    logger.info("  RBW 列表: %s", args.rbw_list)
    logger.info("  降噪方式:  VBW 分档（RBW≤100→10Hz；100<RBW≤10k→100Hz；其余→1kHz）")
    logger.info("")
    try:
        results = cal_bw60(spec, sig,
                           carrier_freq_hz=args.carrier,
                           rbw_list=args.rbw_list)
    except MeasurementError as e:
        raise MeasurementError(str(e), partial_results=_rows_bw60(e.partial_results or {})) from e
    logger.info("\n===== 测量结果 =====")
    rows = _rows_bw60(results)
    for row in rows:
        logger.info("  设定 RBW=%d Hz → -60 dB 带宽: %.1f Hz", row["rbw_hz"], row["bw60_hz"])
    return rows


@_register_command("rbw-switch", aliases=("rbw转换影响", "分辨力带宽转换影响"),
                   export_meta=lambda args: {
                       "command": "rbw-switch",
                       "carrier_hz": args.carrier,
                       "ref_rbw_hz": args.ref_rbw,
                       "span_ratio": args.span_ratio,
                       "ref_level_dbm": args.ref_level,
                       "atten_db": args.atten,
                       "sg_power_dbm": args.sg_power,
                   },
                   summarize=_summarize_rbw_switch)
def _cmd_rbw_switch(sig, spec, args):
    logger.info("\n===== 分辨力带宽转换影响（JJF1396 6.12）=====")
    logger.info("  校准信号频率: %.0f Hz", args.carrier)
    logger.info("  信号源电平:   %s dBm（6.12.2）", args.sg_power)
    logger.info("  参考电平:     %s dBm，输入衰减 %s dB（6.12.3）", args.ref_level, args.atten)
    logger.info("  基准 RBW:     %s Hz，S/RBW = %s（6.12.3）", args.ref_rbw, args.span_ratio)
    logger.info("  待切换 RBW:   %s Hz", args.rbw_list)
    logger.info("")
    try:
        results = cal_rbw_switch(
            spec, sig,
            carrier_freq_hz=args.carrier,
            rbw_list=args.rbw_list,
            ref_rbw=args.ref_rbw,
            span_ratio=args.span_ratio,
            ref_level_dbm=args.ref_level,
            atten_db=args.atten,
            sg_power_dbm=args.sg_power,
            settle_s=args.settle,
        )
    except MeasurementError as e:
        raise MeasurementError(
            str(e), partial_results=_rows_rbw_switch(e.partial_results or {}, args.span_ratio)) from e

    logger.info("\n===== 测量结果 =====")
    rows = _rows_rbw_switch(results, args.span_ratio)
    for row in rows:
        logger.info("  RBW %s Hz（Span %.0f Hz）→ 标记增量峰值 %+.3f dB",
                    row["rbw_hz"], row["span_hz"], row["delta_db"])
    summary = _summarize_rbw_switch(rows)
    if summary:
        logger.info("  分辨力带宽转换影响（max|Δ|）: %.3f dB @ RBW=%s Hz",
                    summary["max_abs_delta_db"], summary["max_abs_delta_at_rbw_hz"])
    return rows


@_register_command("phase-noise", aliases=("pn", "噪声边带"))
def _cmd_phase_noise(sig, spec, args):
    logger.info("\n===== 噪声边带测量 =====")
    logger.info("  载波频率: %.0f Hz", args.carrier)
    logger.info("  频偏列表: %s Hz", args.offset)
    logger.info("  测量模式:  零扫宽 (Span=0)")
    logger.info("  参考电平:  %s dBm", args.ref_level)
    logger.info("  衰减:      %s dB", args.atten)
    logger.info("")

    rows = []
    progress = measurements.PointProgress(len(args.offset))
    for i, offset in enumerate(args.offset, start=1):
        try:
            progress.begin(i, f"频偏 {offset} Hz (RBW={0.1 * offset:.1f} Hz)")
            phase_noise = cal_ssb_phase_noise(
                sig, spec,
                carrier_freq_hz=args.carrier,
                offset_hz=offset,
                ref_level_dbm=args.ref_level,
                atten_db=args.atten,
                average_count=args.average_count,
            )
        except MeasurementError:
            raise
        except Exception as e:
            raise MeasurementError(
                f"噪声边带测量失败于频偏 {offset} Hz"
                f"（已完成 {len(rows)}/{len(args.offset)} 点）: {e}",
                partial_results=rows,
            ) from e
        rows.append({
            "offset_hz": offset,
            "carrier_hz": args.carrier,
            "rbw_hz": 0.1 * offset,
            "phase_noise_dbc_hz": phase_noise,
        })

    logger.info("\n===== 测量结果 =====")
    for row in rows:
        logger.info("  频偏 %d Hz → 相位噪声: %.2f dBc/Hz",
                    row["offset_hz"], row["phase_noise_dbc_hz"])
    return rows


@_register_command("sweep-width", aliases=("sw", "扫频宽度"))
def _cmd_sweep_width(sig, spec, args):
    logger.info("\n===== 扫频宽度准确性验证 =====")
    logger.info("  待测扫频宽度: %s Hz", args.span)
    logger.info("  参考电平:     %s dBm", args.ref_level)
    logger.info("  信号源电平:   %s dBm", args.sg_power)
    logger.info("")

    rows = []
    progress = measurements.PointProgress(len(args.span))
    for i, span in enumerate(args.span, start=1):
        if span <= 1e9:
            label = f"span={span:.0f} Hz（中心 1 GHz，频点 1 GHz ± 0.4×span）"
        else:
            label = f"span={span:.0f} Hz（中心 span/2，频点 0.1×span 与 0.9×span）"
        try:
            progress.begin(i, label)
            result = cal_sweep_width(spec, sig,
                                     span=span,
                                     ref_level_dbm=args.ref_level,
                                     sg_power_dbm=args.sg_power,
                                     align_threshold=args.align_threshold,
                                     align_span=args.align_span)
        except MeasurementError:
            raise
        except Exception as e:
            raise MeasurementError(
                f"扫频宽度测量失败于 span {span} Hz"
                f"（已完成 {len(rows)}/{len(args.span)} 点）: {e}",
                partial_results=rows,
            ) from e
        rows.append({
            "span_hz": span,
            "freq_diff_hz": result["freq_diff"],
            "delta": result["delta"],
            "corrected_width_hz": result["corrected_width"],
        })

    logger.info("\n===== 测量结果 =====")
    for row in rows:
        logger.info("  设定 span=%d Hz → 频率差 %.2f Hz (误差 %+.2f%%)，被校扫频宽度 %.2f Hz",
                    row["span_hz"], row["freq_diff_hz"],
                    100 * row["delta"], row["corrected_width_hz"])
    return rows


@_register_command("log-scale", aliases=("log", "对数刻度"),
                   export_meta=lambda args: {"command": "log-scale",
                                             "scale_db_per_div": args.scale})
def _cmd_log_scale(sig, spec, args):
    logger.info("\n===== 对数刻度准确性验证 =====")
    logger.info("  垂直刻度:   %d dB/div", args.scale)
    logger.info("  中心频率:   %.0f Hz", args.carrier)
    logger.info("  参考电平:   %s dBm", args.ref_level)
    logger.info("  衰减:       %s dB", args.atten)
    logger.info("  span/RBW/VBW: %.0f / %.0f / %.0f Hz", args.span, args.rbw, args.vbw)
    logger.info("  校准点:     %s dB",
                args.points if args.points is not None else "（cal_points.json）")
    logger.info("")

    try:
        result = cal_log_scale(
            spec, sig,
            carrier_freq_hz=args.carrier,
            scale_db_per_div=args.scale,
            points=args.points,
            ref_level_dbm=args.ref_level,
            atten_db=args.atten,
            span_hz=args.span,
            rbw_hz=args.rbw,
            vbw_hz=args.vbw,
            sg_power_dbm=args.sg_power,
            settle_s=args.settle,
        )
    except MeasurementError as e:
        raise MeasurementError(str(e), partial_results=_rows_log(e.partial_results or {})) from e

    logger.info("\n===== 测量结果 =====")
    rows = _rows_log(result["results"])
    for row in rows:
        logger.info("  衰减 %d dB → marker delta %.3f dB（偏差 %+.3f dB）",
                    row["atten_db"], row["marker_delta_db"], row["error_db"])
    return rows


@_register_command("linear-scale", aliases=("lin", "线性刻度"))
def _cmd_linear_scale(sig, spec, args):
    logger.info("\n===== 线性刻度准确性验证 =====")
    logger.info("  中心频率:   %.0f Hz", args.carrier)
    logger.info("  参考电平:   %s dBm", args.ref_level)
    logger.info("  span/RBW:   %.0f / %.0f Hz", args.span, args.rbw)
    logger.info("  峰值目标:   %s mV (±%s mV)", args.target, args.tolerance)
    logger.info("  校准点:     %s dB",
                args.points if args.points is not None else "（cal_points.json）")
    logger.info("")

    try:
        result = cal_linear_scale(
            spec, sig,
            carrier_freq_hz=args.carrier,
            points=args.points,
            ref_level_dbm=args.ref_level,
            atten_db=args.atten,
            span_hz=args.span,
            rbw_hz=args.rbw,
            sg_power_dbm=args.sg_power,
            target_peak_mv=args.target,
            tolerance_mv=args.tolerance,
            mv_per_unit=args.mv_factor,
            settle_s=args.settle,
        )
    except MeasurementError as e:
        raise MeasurementError(str(e),
                               partial_results=_rows_linear(e.partial_results or {})) from e

    logger.info("\n===== 测量结果 =====")
    rows = _rows_linear(result["results"])
    for row in rows:
        logger.info("  衰减 %d dB → Vm %.3f mV / 理论 %.3f mV（相对误差 %+.3f%%）",
                    row["atten_db"], row["measured_mv"], row["theoretical_mv"],
                    row["relative_error_pct"])
    return rows


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0

    if args.dry_run:
        measurements.disable_sleeps()
        logger.info("===== DRY-RUN：不连接仪器，以下为将发送的 SCPI 命令序列 =====")

    try:
        return _dispatch(args)
    except Exception as e:
        logger.error("程序异常: %s", e)
        logger.debug("详细堆栈:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
