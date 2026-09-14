"""仪器类型及通信超时配置。"""
from .base import Instrument

class SignalGenerator(Instrument):
    def __init__(self, resource_address, rm=None, dry_run=False, sleep=None):
        super().__init__(resource_address, "signal_generator.json", rm, dry_run=dry_run, sleep=sleep)
        if not dry_run:
            # 频率/电平稳定可能需要数秒，放宽超时到 15 秒（配合 *OPC? 等待）
            self.instr.timeout = 15000


class SpectrumAnalyzer(Instrument):
    def __init__(self, resource_address, rm=None, dry_run=False, sleep=None):
        super().__init__(resource_address, "spectrum_analyzer.json", rm, dry_run=dry_run, sleep=sleep)
        if not dry_run:
            # 频谱仪扫描可能很慢，增加超时到 60 秒
            self.instr.timeout = 60000


