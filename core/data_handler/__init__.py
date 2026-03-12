"""
core.data_handler - 数据处理核心模块
============================================

保持外部 API 不变:
    from core.data_handler import DataHandler
    from core.data_handler import DataWorker
    from core.data_handler import LabelFormat, ScanResult, ...
"""

# 保持 os 在模块级可访问 (测试 monkey-patch 兼容性)
import os  # noqa: F401

from core.data_handler._models import (
    IMAGE_EXTENSIONS,
    LABEL_EXTENSIONS,
    AppliedGeometryOp,
    AugmentConfig,
    AugmentRecipe,
    AugmentResult,
    LabelFormat,
    ModifyAction,
    ScanResult,
    SplitMode,
    SplitResult,
    ValidateResult,
    _get_unique_dir,
)
from core.data_handler._handler import DataHandler
from core.data_handler._worker import DataWorker

__all__ = [
    # 常量
    "IMAGE_EXTENSIONS",
    "LABEL_EXTENSIONS",
    # 数据类型
    "LabelFormat",
    "SplitMode",
    "ModifyAction",
    "ScanResult",
    "SplitResult",
    "AugmentConfig",
    "AugmentRecipe",
    "AppliedGeometryOp",
    "AugmentResult",
    "ValidateResult",
    # 核心类
    "DataHandler",
    "DataWorker",
    # 辅助函数
    "_get_unique_dir",
]
