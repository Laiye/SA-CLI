"""命令分发、测量调用与结果转换。"""
import logging

from sa_cli.validation import validate_points

from sa_cli import config
from sa_cli.measurements.common import PointProgress
from sa_cli.measurements.freq_reading import format_freq
from sa_cli.instruments import visa_session
from sa_cli.measurements import (MeasurementError, cal_bw60, cal_freq_reading,
                                 cal_linear_scale, cal_log_scale, cal_rbw,
                                 cal_rbw_switch, cal_ssb_phase_noise,
                                 cal_sweep_width)
from sa_cli.report import export_results, validate_output_path

logger = logging.getLogger(__name__)

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


def _rows_freq_reading(results, unit=None):
    """原始结果 {(freq, span): {...}} → 导出行（数值字段 + 仪器显示样式文本）。

    文本的单位按标称频率量级选择（unit 可强制）、小数位由显示分辨力决定，例如
    100 MHz 点、分辨力 0.01 MHz → “100.00 MHz”。
    """
    rows = []
    for (freq, span), vals in results.items():
        resolution = vals["resolution_hz"]
        rows.append({
            "freq_hz": freq,
            "freq_text": format_freq(freq, freq, resolution, unit=unit),
            "span_hz": span,
            "span_text": format_freq(span, freq, resolution, unit=unit),
            "reading_hz": vals["reading_hz"],
            "displayed_hz": vals["displayed_hz"],
            "displayed_text": format_freq(vals["displayed_hz"], freq, resolution, unit=unit),
            "error_hz": vals["error_hz"],
            "error_text": format_freq(vals["error_hz"], freq, resolution, signed=True, unit=unit),
            "raw_error_hz": vals["raw_error_hz"],
            "relative_ppm": round(vals["relative_ppm"], 3),
            "resolution_hz": resolution,
            "resolution_text": format_freq(resolution, freq, resolution, unit=unit),
        })
    return rows


def _summarize_freq_reading(rows):
    """结论字段：最大显示偏差（含对应频率/扫频宽度）、最大相对偏差与占分辨力倍数。"""
    if not rows:
        return {}
    worst = max(rows, key=lambda r: abs(r["error_hz"]))
    worst_ppm = max(rows, key=lambda r: abs(r["relative_ppm"]))
    return {
        "max_abs_error_hz": worst["error_hz"],
        "max_abs_error_text": worst["error_text"],
        "max_abs_error_at_freq_hz": worst["freq_hz"],
        "max_abs_error_at_freq_text": worst["freq_text"],
        "max_abs_error_at_span_hz": worst["span_hz"],
        "max_abs_error_at_span_text": worst["span_text"],
        "max_abs_relative_ppm": round(worst_ppm["relative_ppm"], 3),
        "max_error_in_resolution_units": round(
            abs(worst["error_hz"]) / worst["resolution_hz"], 3) if worst["resolution_hz"] else None,
    }


def _dispatch(args, *, sleep=None):
    """会话管理 + 统一导出/部分结果导出的执行骨架。"""
    canonical = _ALIAS_TO_CANONICAL.get(args.command, args.command)
    if args.output:
        validate_output_path(args.output)
    if canonical in ("log-scale", "linear-scale") and args.points is None:
        key = "log-scale-{}db".format(args.scale) if canonical == "log-scale" else canonical
        fallback = (config.DEFAULT_LOG_SCALE_1DB_POINTS if args.scale == 1
                    else config.DEFAULT_LOG_SCALE_10DB_POINTS) if canonical == "log-scale" else config.DEFAULT_LINEAR_SCALE_POINTS
        args.points = config.cal_point_defaults(key, fallback)
    for name in ("offset", "rbw_list", "span", "points", "freq_list"):
        points = getattr(args, name, None)
        if isinstance(points, list):
            validate_points(points, name)
    if getattr(args, "average_count", 0) < 0:
        raise ValueError("平均次数不能为负数")
    cmd = _COMMAND_SPECS[canonical]

    def _export_data(rows, partial=False):
        data = {**cmd["export_meta"](args), "results": rows}
        summarize = cmd.get("summarize")
        if summarize:
            data.update(summarize(rows))
        if partial:
            data["partial"] = True
        return data

    with visa_session(args.sg_addr, args.sa_addr, dry_run=args.dry_run, sleep=sleep) as (sig, spec):
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


@_register_command("freq-reading", aliases=("freq", "频率读数"),
                   export_meta=lambda args: {
                       "command": "freq-reading",
                       "freq_list": args.freq_list,
                       "ref_level_dbm": args.ref_level,
                       "sg_power_dbm": args.sg_power,
                       "points_count": args.points_count,
                       "unit": args.unit,
                   },
                   summarize=_summarize_freq_reading)
def _cmd_freq_reading(sig, spec, args):
    unit = None if args.unit == "auto" else args.unit
    logger.info("\n===== 频率读数准确性验证 =====")
    logger.info("  校准频率点:   %s Hz", args.freq_list)
    logger.info("  参考电平:     %s dBm，信号源电平 %s dBm", args.ref_level, args.sg_power)
    logger.info("  采样点数:     %d（显示分辨力 = span/(Points-1)）", args.points_count)
    logger.info("  显示单位:     %s", "自动（按量级切换）" if unit is None else unit)
    logger.info("  扫频宽度规则: 1 MHz→10k/100k/1M；10 MHz→100k/1M/10M；≥100 MHz→1M/10M/100M")
    logger.info("")
    try:
        results = cal_freq_reading(
            spec, sig,
            freq_list=args.freq_list,
            ref_level_dbm=args.ref_level,
            sg_power_dbm=args.sg_power,
            points_count=args.points_count,
            settle_s=args.settle,
        )
    except MeasurementError as e:
        raise MeasurementError(
            str(e), partial_results=_rows_freq_reading(e.partial_results or {}, unit)) from e

    logger.info("\n===== 测量结果 =====")
    rows = _rows_freq_reading(results, unit)
    for row in rows:
        logger.info("  %s / Span %s → marker 显示 %s（分辨力 %s，偏差 %s）",
                    row["freq_text"], row["span_text"], row["displayed_text"],
                    row["resolution_text"], row["error_text"])
    summary = _summarize_freq_reading(rows)
    if summary:
        logger.info("  最大显示偏差: %s @ %s（Span %s），占分辨力 %.2f 倍",
                    summary["max_abs_error_text"], summary["max_abs_error_at_freq_text"],
                    summary["max_abs_error_at_span_text"],
                    summary["max_error_in_resolution_units"])
        logger.info("  最大相对偏差: %+.3f ppm", summary["max_abs_relative_ppm"])
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
    progress = PointProgress(len(args.offset))
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
    progress = PointProgress(len(args.span))
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


