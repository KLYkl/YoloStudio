"""
config.py - 全局配置管理器 (单例模式)
============================================

职责:
    - 管理应用程序的全局配置状态
    - 提供线程安全的配置读写
    - 自动持久化配置到 JSON 文件

架构要点:
    - 使用双重检查锁定 (Double-Checked Locking) 实现线程安全单例
    - 配置文件存储在用户目录: ~/.yolostudio/config.json
    - 支持默认值回退机制
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any, Optional


class AppConfig:
    """
    应用程序全局配置管理器 (线程安全单例)
    
    使用方式:
        config = AppConfig()
        config.set("last_open_path", "/path/to/folder")
        path = config.get("last_open_path", default="")
        config.save()
    
    Attributes:
        CONFIG_DIR: 配置文件存储目录
        CONFIG_FILE: 配置文件完整路径
    """
    
    _instance: Optional[AppConfig] = None
    _lock: threading.Lock = threading.Lock()
    
    # 配置文件路径
    CONFIG_DIR: Path = Path.home() / ".yolostudio"
    CONFIG_FILE: Path = CONFIG_DIR / "config.json"
    
    # 默认配置值
    _defaults: dict[str, Any] = {
        "last_open_path": "",
        "window_width": 1280,
        "window_height": 800,
        "yolo_version": "v11",
        "theme": "dark",
        "language": "zh_CN",
    }
    
    def __new__(cls) -> AppConfig:
        """
        双重检查锁定实现线程安全单例
        
        Returns:
            AppConfig: 全局唯一的配置管理器实例
        """
        if cls._instance is None:
            with cls._lock:
                # 二次检查，防止并发创建
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """初始化配置管理器 (仅在首次创建时执行)"""
        # 防止重复初始化
        if self._initialized:
            return
        
        self._data: dict[str, Any] = {}
        self._data_lock: threading.Lock = threading.Lock()
        self._initialized = True
        
        # 自动加载配置
        self.load()
    
    def load(self) -> None:
        """
        从 JSON 文件加载配置
        
        如果配置文件不存在，将使用默认值并创建新文件
        """
        with self._data_lock:
            if self.CONFIG_FILE.exists():
                try:
                    with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"[警告] 配置文件损坏: {e}")
                    backup = self.CONFIG_FILE.with_suffix(".json.bak")
                    if backup.exists():
                        try:
                            with open(backup, "r", encoding="utf-8") as f:
                                self._data = json.load(f)
                            print("[警告] 已从备份文件恢复配置")
                        except (json.JSONDecodeError, IOError):
                            self._data = self._defaults.copy()
                            print("[警告] 备份也已损坏，使用默认配置")
                    else:
                        self._data = self._defaults.copy()
                        print("[警告] 无备份可用，使用默认配置")
            else:
                # 首次运行，初始化默认配置
                self._data = self._defaults.copy()
                self._ensure_config_dir()
                self._save_internal()
    
    def save(self) -> None:
        """将当前配置持久化到 JSON 文件"""
        with self._data_lock:
            self._ensure_config_dir()
            self._save_internal()
    
    def _save_internal(self) -> None:
        """内部保存方法 (不加锁，由调用者负责加锁)"""
        try:
            if self.CONFIG_FILE.exists():
                backup = self.CONFIG_FILE.with_suffix(".json.bak")
                shutil.copy2(self.CONFIG_FILE, backup)
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[错误] 配置文件保存失败: {e}")
    
    def _ensure_config_dir(self) -> None:
        """确保配置目录存在"""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项的值
        
        Args:
            key: 配置项名称
            default: 键不存在时的默认值 (优先使用 _defaults 中的值)
        
        Returns:
            配置值，如果不存在则返回默认值
        """
        with self._data_lock:
            if key in self._data:
                return self._data[key]
            # 回退到预定义默认值
            if key in self._defaults:
                return self._defaults[key]
            return default
    
    def set(self, key: str, value: Any, auto_save: bool = False) -> None:
        """
        设置配置项的值
        
        Args:
            key: 配置项名称
            value: 配置值
            auto_save: 是否立即保存到文件
        """
        with self._data_lock:
            self._data[key] = value
            if auto_save:
                self._save_internal()
    
    def get_all(self) -> dict[str, Any]:
        """
        获取所有配置项的副本
        
        Returns:
            配置字典的深拷贝
        """
        with self._data_lock:
            return self._data.copy()
    
    def reset_to_defaults(self) -> None:
        """重置所有配置为默认值"""
        with self._data_lock:
            self._data = self._defaults.copy()
            self._save_internal()
