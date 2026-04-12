"""
i18n.py - 轻量级国际化支持
============================================

职责:
    - 提供全局翻译函数 t()
    - 管理语言切换 (LanguageManager 单例)
    - 从 resources/lang/ 加载语言文件

使用方式:
    from utils.i18n import t

    label = QLabel(t("app_title"))
    text = t("processed_frames", count=100)
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

_logger = logging.getLogger(__name__)

# 当前语言的翻译字典 (模块级全局)
_current: dict[str, str] = {}

# 当前语言代码
_current_lang: str = "zh_CN"


def t(key: str, **kwargs: Any) -> str:
    """获取当前语言的翻译文本

    Args:
        key: 翻译键名
        **kwargs: 命名参数, 用于文本插值 (对应翻译中的 {name} 占位符)

    Returns:
        翻译后的文本; 若 key 不存在则原样返回 key

    Examples:
        t("start")                          # -> "开始" / "Start"
        t("processed_frames", count=100)    # -> "已处理: 100 帧"
    """
    text = _current.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


class LanguageManager:
    """语言管理器 (单例)"""

    _instance: Optional[LanguageManager] = None

    SUPPORTED = {
        "zh_CN": "中文",
        "en_US": "English",
    }

    def __init__(self) -> None:
        self._lang: str = "zh_CN"

    @classmethod
    def instance(cls) -> LanguageManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def current_language(self) -> str:
        return self._lang

    def load(self, lang: str) -> bool:
        """加载指定语言

        Args:
            lang: 语言代码, 如 "zh_CN" / "en_US"

        Returns:
            是否加载成功
        """
        global _current, _current_lang

        if lang not in self.SUPPORTED:
            _logger.warning(f"Unsupported language: {lang}")
            return False

        module_name = f"resources.lang.{lang}"
        try:
            mod = importlib.import_module(module_name)
            importlib.reload(mod)
        except ModuleNotFoundError:
            _logger.error(f"Language file not found: {module_name}")
            return False

        translations = getattr(mod, "TRANSLATIONS", None)
        if not isinstance(translations, dict):
            _logger.error(f"Invalid language file: {module_name}")
            return False

        _current.clear()
        _current.update(translations)
        _current_lang = lang
        self._lang = lang
        _logger.info(f"Language loaded: {lang} ({len(_current)} keys)")
        return True

    def switch(self, lang: str) -> bool:
        """切换语言并保存到配置

        Args:
            lang: 目标语言代码

        Returns:
            是否切换成功
        """
        if not self.load(lang):
            return False

        from config import AppConfig
        config = AppConfig()
        config.set("language", lang, auto_save=True)
        return True

    def get_next_language(self) -> str:
        """获取下一个语言 (用于循环切换)"""
        langs = list(self.SUPPORTED.keys())
        idx = langs.index(self._lang) if self._lang in langs else 0
        return langs[(idx + 1) % len(langs)]


def init_language() -> None:
    """初始化语言 (应用启动时调用一次)"""
    from config import AppConfig
    config = AppConfig()
    lang = config.get("language", "zh_CN")
    mgr = LanguageManager.instance()
    if not mgr.load(lang):
        mgr.load("zh_CN")
