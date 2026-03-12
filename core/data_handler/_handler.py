"""
_handler.py - DataHandler 主类 (组合所有 Mixin)
============================================
"""

from __future__ import annotations

from core.data_handler._scan import ScanMixin
from core.data_handler._stats import StatsMixin
from core.data_handler._validate import ValidateMixin
from core.data_handler._convert import ConvertMixin
from core.data_handler._modify import ModifyMixin
from core.data_handler._split import SplitMixin
from core.data_handler._augment import AugmentMixin


class DataHandler(
    ScanMixin,
    StatsMixin,
    ValidateMixin,
    ConvertMixin,
    ModifyMixin,
    SplitMixin,
    AugmentMixin,
):
    """
    数据处理核心逻辑 (纯 Python，不依赖 Qt GUI)

    所有耗时方法接收 interrupt_check 参数，用于响应取消请求。

    通过 Mixin 模式组合以下功能:
        - ScanMixin: 数据集扫描
        - StatsMixin: 统计/分类
        - ValidateMixin: 标签验证/解析
        - ConvertMixin: 格式转换
        - ModifyMixin: 标签修改/清理
        - SplitMixin: 数据集划分
        - AugmentMixin: 数据增强 + 几何变换
    """

    def __init__(self) -> None:
        """初始化数据处理器"""
        self._class_mapping: dict[int, str] = {}  # TXT 类别 ID -> 名称映射
