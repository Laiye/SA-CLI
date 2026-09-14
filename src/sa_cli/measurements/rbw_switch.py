"""分辨力带宽转换影响测量。"""
import logging

from sa_cli import config
from . import common

logger = logging.getLogger(__name__)

def cal_rbw_switch(spec_an, sig_gen, carrier_freq_hz=config.DEFAULT_CARRIER, rbw_list=None,
                   ref_rbw=config.DEFAULT_RBW_SWITCH_REF,
                   span_ratio=config.DEFAULT_SPAN_RATIO,
                   ref_level_dbm=config.DEFAULT_RBW_SWITCH_REF_LEVEL,
                   atten_db=config.DEFAULT_ATTEN,
                   sg_power_dbm=config.DEFAULT_RBW_SWITCH_SG_POWER,
                   settle_s=0.5):
    """
    分辨力带宽转换影响（JJF1396 6.12）。

    图 5 连接：信号源射频输出 → 频谱分析仪射频输入。
    6.12.2 信号源频率 = 频谱仪校准信号频率，电平 -20 dBm；
    6.12.3 频谱仪中心频率 = 校准信号频率，参考电平 -15 dBm，输入衰减 10 dB，
           RBW = 30 kHz，扫频宽度 = S/RBW × RBW（S/RBW 取 5~10），VBW/扫描时间自动；
    6.12.4 打开峰值标记，再打开标记增量功能（在基准 RBW 的峰值上建立 Δ 参考）；
    6.12.5 改变 RBW，同时以固定 S/RBW 比率改变扫频宽度，记录标记增量峰值；
    6.12.6 按附录 A 表 A.11 逐个 RBW 重复上述切换。

    每次切换后用 peak_search 把增量标记移到当前峰值，读得的 marker Y 即
    “标记增量峰值”：理想情况下切换 RBW 不改变幅度，Δ 应为 0 dB，偏差即转换影响。

    返回 {rbw_hz: delta_db}。基准 RBW 自身那一行应接近 0 dB（自参考校验点）。
    """
    if rbw_list is None:
        rbw_list = config.DEFAULT_RBW_SWITCH_LIST

    # 6.12.2 配置信号源（频率 = 校准信号频率，电平 -20 dBm）
    common._init_signal_gen(sig_gen, power_dbm=sg_power_dbm, freq_hz=carrier_freq_hz)

    # 6.12.3 频谱仪基准状态：RBW = ref_rbw，Span = S/RBW × RBW
    common._init_spec_an(spec_an)
    spec_an.set_center_freq(carrier_freq_hz)
    spec_an.set_ref_level(ref_level_dbm)
    spec_an.set_attenuation(atten_db)
    spec_an.set_vbw_auto()                    # 视频带宽自动（扫描时间保持自动耦合）
    spec_an.set_rbw(ref_rbw)
    spec_an.set_span(span_ratio * ref_rbw)
    common._wait_sweep(spec_an, min_sleep=1.0)

    # 6.12.4 峰值标记 → 标记增量：Δ 参考建立在基准 RBW 的峰值电平上
    spec_an.peak_search()
    spec_an.sleep(0.5)
    spec_an.set_marker_delta()
    spec_an.sleep(0.5)

    def _measure_point(rbw):
        # 6.12.5 改变 RBW，同时按固定 S/RBW 改变扫频宽度
        spec_an.set_rbw(rbw)
        spec_an.set_span(span_ratio * rbw)
        common._wait_sweep(spec_an, min_sleep=settle_s)
        spec_an.peak_search()                 # 增量标记移到当前峰值 → 标记增量峰值
        spec_an.sleep(0.3)
        delta = spec_an.marker_read_y()
        logger.info("  RBW %s Hz（Span %.0f Hz）→ 标记增量峰值 %.3f dB",
                    rbw, span_ratio * rbw, delta)
        return delta

    results = common._collect_points(rbw_list, _measure_point, "分辨力带宽转换影响",
                                     describe=lambda rbw: f"切换到 RBW={rbw} Hz")
    return results


