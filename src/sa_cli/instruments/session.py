"""VISA 会话生命周期。"""
import logging
from contextlib import contextmanager

import pyvisa

from .devices import SignalGenerator, SpectrumAnalyzer

logger = logging.getLogger(__name__)


@contextmanager
def visa_session(sg_addr, sa_addr, rm=None, dry_run=False, sleep=None):
    """打开信号源与频谱仪，确保退出时资源被释放；dry_run 时不连接仪器。"""
    rm = rm if dry_run else (rm or pyvisa.ResourceManager())
    sig = None
    spec = None
    try:
        sig = SignalGenerator(sg_addr, rm=rm, dry_run=dry_run, sleep=sleep)
        spec = SpectrumAnalyzer(sa_addr, rm=rm, dry_run=dry_run, sleep=sleep)
        yield sig, spec
    finally:
        if sig:
            try:
                sig.rf_off()   # 兜底：正常/异常退出都确保 RF 输出关闭（dry-run 仅打印）
            except Exception:
                logger.warning("RF 关闭失败", exc_info=True)
            sig.close()
        if spec:
            spec.close()
        if rm:
            try:
                rm.close()
            except Exception:
                pass
