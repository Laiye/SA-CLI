"""命令行参数声明与解析。"""
import argparse

from sa_cli import config
from sa_cli.validation import finite_float, validate_levels

# 数值后缀：k/K=1e3、M=1e6、G=1e9（小写 m 与"毫"歧义，不接受）
_SI_PREFIXES = {"k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "g": 1e9}


def _parse_number(text):
    """解析数值参数：支持 k/K/M/G 后缀与科学计数法。

    例如 30k → 30000、2.4G → 2.4e9、1.5M → 1.5e6、50e6 → 5e7；
    也接受 -20k 这类带符号写法。小写 m 因易与"毫"混淆而拒绝，兆请写 M。
    """
    raw = str(text).strip()
    if not raw:
        raise argparse.ArgumentTypeError("空数值")
    multiplier = 1.0
    last = raw[-1]
    if last in _SI_PREFIXES:
        multiplier = _SI_PREFIXES[last]
        raw = raw[:-1]
    elif last == "m":
        raise argparse.ArgumentTypeError(
            f"不支持小写 'm'（易与毫混淆），兆请写 'M': {text!r}")
    try:
        return finite_float(float(raw) * multiplier)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"无法解析为数值（支持 30k / 2.4M / 1G / 50e6 写法）: {text!r}") from None


def _positive_float(text):
    """argparse type：必须为正数（频率、列表校准点等），支持 k/M/G 后缀。"""
    value = _parse_number(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"必须为正数: {text!r}")
    return value


def _nonneg_float(text):
    """argparse type：不能为负数（衰减、等待时间等），支持 k/M/G 后缀。"""
    value = _parse_number(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"不能为负数: {text!r}")
    return value


def _any_float(text):
    """argparse type：可正可负的数值（参考电平 / 信号源电平 dBm），支持 k/M/G 后缀。"""
    return _parse_number(text)


def _int_at_least(minimum, label):
    """argparse type 工厂：不小于 minimum 的整数（如采样点数 ≥ 2）。"""
    def _convert(text):
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{label}必须为整数: {text!r}") from None
        if value < minimum:
            raise argparse.ArgumentTypeError(f"{label}不能小于 {minimum}: {text!r}")
        return value

    return _convert


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
    parser = argparse.ArgumentParser(
        prog="sa-cli", description="SA-CLI: 频谱分析仪控制与测量工具",
    )
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
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_REF_LEVEL,
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
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_RBW_SWITCH_REF_LEVEL,
        help="参考电平 (dBm)，默认 -15（规范 6.12.3）",
    )
    rsw.add_argument(
        "--atten", "-a", type=_nonneg_float, default=config.DEFAULT_ATTEN,
        help="输入衰减 (dB)，默认 10（规范 6.12.3）",
    )
    rsw.add_argument(
        "--sg-power", type=_any_float, default=config.DEFAULT_RBW_SWITCH_SG_POWER,
        help="信号源电平 (dBm)，默认 -20（规范 6.12.2）",
    )
    rsw.add_argument(
        "--settle", type=_nonneg_float, default=0.5,
        help="每次切换 RBW 后的稳定等待下限 (s)，默认 0.5",
    )
    _add_instrument_args(rsw)
    _add_output_arg(rsw)

    # ---------- 参考电平 ----------
    rl = subparsers.add_parser(
        "ref-level", aliases=["reflevel", "参考电平"], parents=[common],
        help="参考电平校准（-10 dBm 为参考点）",
    )
    rl.add_argument(
        "--levels", "-l", type=_any_float, nargs="+",
        default=config.cal_point_defaults("ref-level", config.DEFAULT_REF_LEVEL_POINTS,
                                          validate_levels),
        help="参考电平点列表 (dBm)，默认 -10 0 10 -20 -30 -40 -50 -60 -70；默认读取 cal_points.json",
    )
    rl.add_argument(
        "--carrier", "-c", type=_positive_float, default=config.DEFAULT_REF_LEVEL_CARRIER,
        help="校准信号频率 (Hz)，默认 50e6 (50 MHz)",
    )
    rl.add_argument(
        "--span", type=_positive_float, default=config.DEFAULT_REF_LEVEL_SPAN,
        help="扫频宽度 (Hz)，默认 10k",
    )
    rl.add_argument(
        "--rbw", type=_positive_float, default=config.DEFAULT_REF_LEVEL_RBW,
        help="分辨力带宽 (Hz)，默认 1k",
    )
    rl.add_argument(
        "--vbw", type=_positive_float, default=config.DEFAULT_REF_LEVEL_VBW,
        help="视频带宽 (Hz)，默认 30",
    )
    rl.add_argument(
        "--sg-power", type=_any_float, default=config.DEFAULT_REF_LEVEL_SG_POWER,
        help="信号源初始输出电平 (dBm)，默认 -11",
    )
    rl.add_argument(
        "--tolerance", type=_nonneg_float, default=config.DEFAULT_REF_LEVEL_TOLERANCE,
        help="参考建立容差 (dB)，默认 0.5",
    )
    rl.add_argument(
        "--max-sg-power", type=_any_float, default=config.DEFAULT_REF_LEVEL_MAX_SG_POWER,
        help="信号源输出安全上限 (dBm)，默认 10；超过即中止以保护频谱仪输入",
    )
    rl.add_argument(
        "--average-count", type=_int_at_least(1, "平均次数"), default=1,
        help="弱信号点的 trace 平均次数，默认 1（不平均）",
    )
    rl.add_argument(
        "--average-below", type=_any_float, default=config.DEFAULT_REF_LEVEL_AVERAGE_BELOW,
        help="参考电平不高于该值时启用平均 (dBm)，默认 -55",
    )
    rl.add_argument(
        "--settle", type=_nonneg_float, default=0.5,
        help="每次调整后的稳定等待下限 (s)，默认 0.5",
    )
    _add_instrument_args(rl)
    _add_output_arg(rl)

    # ---------- 频率读数 ----------
    fr = subparsers.add_parser(
        "freq-reading", aliases=["freq", "频率读数"], parents=[common],
        help="频率读数准确性验证（marker 显示值为准）",
    )
    fr.add_argument(
        "--freq-list", "-f", type=_positive_float, nargs="+",
        default=config.cal_point_defaults("freq-reading", config.DEFAULT_FREQ_READING_FREQS),
        help="校准频率点列表 (Hz)，默认 1M 10M 100M 1000M 10000M 26500M；默认读取 cal_points.json",
    )
    fr.add_argument(
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_FREQ_READING_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    fr.add_argument(
        "--sg-power", type=_any_float, default=config.DEFAULT_FREQ_READING_SG_POWER,
        help="信号源输出电平 (dBm)，默认 -1",
    )
    fr.add_argument(
        "--points-count", type=_int_at_least(2, "采样点数"), default=config.DEFAULT_SWEEP_POINTS,
        help="频谱仪采样点数 Points，默认 1001（显示分辨力 = span/(Points-1)）",
    )
    fr.add_argument(
        "--settle", type=_nonneg_float, default=0.5,
        help="每个扫频点扫描完成后的稳定等待下限 (s)，默认 0.5",
    )
    fr.add_argument(
        "--unit", choices=["auto", "Hz", "kHz", "MHz", "GHz"], default="auto",
        help="显示单位：auto 按频率量级自动切换（默认），也可强制 Hz/kHz/MHz/GHz",
    )
    _add_instrument_args(fr)
    _add_output_arg(fr)

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
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_REF_LEVEL,
        help="参考电平 (dBm)，默认 0",
    )
    sw.add_argument(
        "--sg-power", type=_any_float, default=config.DEFAULT_SG_POWER,
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
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_REF_LEVEL,
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
        "--sg-power", type=_any_float, default=config.DEFAULT_SG_POWER,
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
        "--ref-level", "-r", type=_any_float, default=config.DEFAULT_REF_LEVEL,
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
        "--sg-power", type=_any_float, default=config.DEFAULT_SG_POWER,
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


