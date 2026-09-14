"""跨模块测量异常。"""

class MeasurementError(Exception):
    """测量中断；携带已完成校准点的部分结果，便于中途异常时导出。"""

    def __init__(self, message, partial_results=None):
        super().__init__(message)
        self.partial_results = partial_results


