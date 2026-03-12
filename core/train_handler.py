"""
train_handler.py - 模型训练核心逻辑
============================================

职责:
    - 管理 YOLO 训练进程 (QProcess)
    - 检测 Conda 环境
    - 发射训练日志信号

架构要点:
    - 使用 QProcess 隔离训练进程，避免 UI 冻结
    - 高频日志 (raw_output) → 终端监视器
    - 低频事件 (system_msg) → 全局日志
"""

from __future__ import annotations

import locale
import os
import shlex
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Signal


def _decode_subprocess_output(data: bytes | str | None) -> str:
    """Decode command output without relying on the process locale."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data

    encodings: list[str] = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred.lower() not in {enc.lower() for enc in encodings}:
        encodings.append(preferred)
    if sys.platform == "win32" and "gbk" not in {enc.lower() for enc in encodings}:
        encodings.append("gbk")

    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode("utf-8", errors="replace")


class TrainManager(QObject):
    """
    训练管理器
    
    使用 QProcess 在独立进程中运行 YOLO 训练，
    通过信号实时发送训练输出。
    
    Signals:
        raw_output(str): 训练进程的原始输出 (高频，终端显示)
        system_msg(str, str): 系统事件消息 (低频，全局日志)
        finished(): 训练进程结束
    """
    
    # 信号定义
    raw_output = Signal(str)          # 原始输出 → 终端
    system_msg = Signal(str, str)     # 系统消息 (msg, level) → 全局日志
    finished = Signal()               # 训练结束
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化训练管理器"""
        super().__init__(parent)
        
        self._process: Optional[QProcess] = None
        self._is_running = False
    
    @property
    def is_running(self) -> bool:
        """返回训练是否正在运行"""
        return self._is_running
    
    def detect_conda_envs(self) -> list[tuple[str, str]]:
        """
        扫描系统中的 Conda 环境
        
        方法 A (主要): 使用 `conda env list` 命令获取所有环境
        方法 B (回退): 扫描常见目录查找环境
        
        Returns:
            环境列表，每项为 (env_name, python_path) 元组
        """
        import subprocess
        
        envs = {}  # 使用 dict 去重: {python_path: env_name}
        python_name = "python.exe" if sys.platform == "win32" else "python"
        
        # ========== 方法 A: 使用 conda env list ==========
        try:
            result = subprocess.run(
                ["conda", "env", "list"],
                capture_output=True,
                text=False,
                timeout=10,
                shell=(sys.platform == "win32"),
            )
            
            if result.returncode == 0:
                stdout = _decode_subprocess_output(result.stdout)
                for line in stdout.strip().splitlines():
                    # 跳过注释行和空行
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # 解析环境路径 (格式: "env_name   /path/to/env" 或 "env_name * /path/to/env")
                    parts = line.split()
                    if len(parts) >= 2:
                        # 环境名是第一个元素，路径通常是最后一个元素
                        env_name = parts[0]
                        env_path = Path(parts[-1])
                        
                        # 验证目录存在
                        if not env_path.is_dir():
                            continue
                        
                        # 构建 python 路径
                        if sys.platform == "win32":
                            python_path = env_path / python_name
                        else:
                            python_path = env_path / "bin" / python_name
                        
                        if python_path.exists():
                            envs[str(python_path)] = env_name
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # conda 命令失败，继续使用方法 B
            pass
        
        # ========== 方法 B: 扫描常见目录 (回退/补充) ==========
        if sys.platform == "win32":
            # Windows: 扫描更多位置
            search_roots = [
                Path.home() / "anaconda3" / "envs",
                Path.home() / "miniconda3" / "envs",
                Path.home() / ".conda" / "envs",
                Path("C:/ProgramData/anaconda3/envs"),
                Path("C:/ProgramData/miniconda3/envs"),
                # 扫描其他驱动器
                Path("D:/anaconda3/envs"),
                Path("D:/miniconda3/envs"),
                Path("E:/anaconda3/envs"),
            ]
        else:
            # Linux / macOS
            search_roots = [
                Path.home() / "anaconda3" / "envs",
                Path.home() / "miniconda3" / "envs",
                Path.home() / ".conda" / "envs",
                Path("/opt/anaconda3/envs"),
                Path("/opt/miniconda3/envs"),
            ]
        
        for search_dir in search_roots:
            if not search_dir.exists():
                continue
            
            try:
                for env_dir in search_dir.iterdir():
                    if not env_dir.is_dir():
                        continue
                    
                    # 构建 python 路径
                    if sys.platform == "win32":
                        python_path = env_dir / python_name
                    else:
                        python_path = env_dir / "bin" / python_name
                    
                    if python_path.exists():
                        python_path_str = str(python_path)
                        # 如果路径不存在，使用目录名作为环境名
                        if python_path_str not in envs:
                            envs[python_path_str] = env_dir.name
            except PermissionError:
                continue
        
        # 添加当前 Python
        current_python = sys.executable
        if current_python not in envs:
            # 尝试从路径推断环境名
            current_path = Path(current_python)
            # 查找 envs 目录以获取环境名，格式通常为 .../envs/env_name/...
            parts = current_path.parts
            if "envs" in parts:
                idx = parts.index("envs")
                if idx + 1 < len(parts):
                    envs[current_python] = parts[idx + 1]
                else:
                    envs[current_python] = "当前环境"
            else:
                envs[current_python] = "当前环境"
        
        # 转为元组列表: [(env_name, python_path), ...]
        result_list = [(name, path) for path, name in sorted(envs.items(), key=lambda x: x[1])]
        
        # 当前 Python 放在最前面
        for i, (name, path) in enumerate(result_list):
            if path == current_python:
                result_list.insert(0, result_list.pop(i))
                break
        
        return result_list
    
    def start_training(self, command_str: str, work_dir: str) -> bool:
        """
        启动训练进程
        
        Args:
            command_str: 完整的命令字符串 (用户可编辑)
            work_dir: 工作目录
        
        Returns:
            是否成功启动
        """
        if self._is_running:
            self.system_msg.emit("训练已在运行中", "warning")
            return False
        
        # 创建进程
        self._process = QProcess(self)
        self._process.setWorkingDirectory(work_dir)
        
        # 连接信号
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)
        
        # 启动进程
        self.system_msg.emit(f"启动训练: {command_str[:100]}...", "info")
        self.system_msg.emit(f"工作目录: {work_dir}", "info")
        
        if sys.platform == "win32":
            # Windows: 尝试激活 conda 环境后运行
            # 从命令中提取 python 路径并推断环境名
            env_name = self._extract_env_name(command_str)
            
            if env_name:
                # 使用 conda activate 激活环境
                # 构建: conda activate env_name && python -m ultralytics ...
                # 需要从原始命令中移除 python 路径，只保留后续参数
                train_args = self._extract_train_args(command_str)
                if train_args:
                    full_cmd = f'conda activate {env_name} && python {train_args}'
                    self.system_msg.emit(f"激活环境: {env_name}", "info")
                else:
                    full_cmd = command_str
            else:
                # 无法推断环境名，使用原始命令
                full_cmd = command_str
            
            self._process.setProgram("cmd.exe")
            self._process.setArguments(["/c", full_cmd])
        else:
            # Unix: 解析命令并直接运行
            try:
                args = shlex.split(command_str)
            except ValueError as e:
                self.system_msg.emit(f"命令解析失败: {e}", "error")
                return False
            self._process.setProgram(args[0])
            self._process.setArguments(args[1:])
        
        self._process.start()
        
        if not self._process.waitForStarted(5000):
            self.system_msg.emit("训练进程启动失败", "error")
            return False
        
        self._is_running = True
        self.system_msg.emit("训练已开始", "info")
        return True
    
    def _extract_env_name(self, command_str: str) -> Optional[str]:
        """
        从命令字符串中提取 Conda 环境名
        
        命令格式: "D:/Anaconda/envs/yolodo/python.exe" -m ultralytics ...
        或: D:/Anaconda/envs/yolodo/python.exe -m ultralytics ...
        
        Returns:
            环境名 (如 "yolodo") 或 None
        """
        import re
        
        # 匹配带引号或不带引号的 python 路径
        # 格式: .../envs/ENV_NAME/python.exe 或 .../envs/ENV_NAME/bin/python
        pattern = r'["\']?([^"\']+?)[/\\]envs[/\\]([^/\\"\']+)[/\\](?:bin[/\\])?python(?:\.exe)?["\']?'
        match = re.search(pattern, command_str, re.IGNORECASE)
        
        if match:
            return match.group(2)  # 返回环境名
        
        return None
    
    def _extract_train_args(self, command_str: str) -> Optional[str]:
        """
        从命令字符串中提取训练参数 (去除 python 路径)
        
        命令格式: "D:/.../python.exe" -m ultralytics train model=...
        返回: -m ultralytics train model=...
        """
        import re
        
        # 移除开头的 python 解释器路径
        # 匹配: "path/to/python.exe" 或 path/to/python.exe
        pattern = r'^["\']?[^"\']*?python(?:\.exe)?["\']?\s+'
        result = re.sub(pattern, '', command_str, count=1, flags=re.IGNORECASE)
        
        return result.strip() if result != command_str else None
    
    def stop_training(self) -> None:
        """停止训练进程"""
        if not self._is_running or self._process is None:
            self.system_msg.emit("没有正在运行的训练", "warning")
            return
        
        self.system_msg.emit("正在停止训练...", "warning")
        
        # 强制终止
        self._process.kill()
        self._process.waitForFinished(3000)
        
        self._is_running = False
        self.system_msg.emit("训练已停止", "warning")
    
    def _on_stdout(self) -> None:
        """处理标准输出"""
        if self._process is None:
            return
        
        data = self._process.readAllStandardOutput()
        text = _decode_subprocess_output(bytes(data))
        if text.strip():
            self.raw_output.emit(text)
    
    def _on_stderr(self) -> None:
        """处理标准错误"""
        if self._process is None:
            return
        
        data = self._process.readAllStandardError()
        text = _decode_subprocess_output(bytes(data))
        if text.strip():
            self.raw_output.emit(text)
    
    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        """处理进程结束"""
        self._is_running = False
        
        if exit_status == QProcess.ExitStatus.NormalExit:
            if exit_code == 0:
                self.system_msg.emit("训练完成 ✓", "info")
            else:
                self.system_msg.emit(f"训练结束 (退出码: {exit_code})", "warning")
        else:
            self.system_msg.emit("训练异常终止", "error")
        
        self.finished.emit()
    
    def _on_error(self, error: QProcess.ProcessError) -> None:
        """处理进程错误"""
        error_msgs = {
            QProcess.ProcessError.FailedToStart: "进程启动失败",
            QProcess.ProcessError.Crashed: "进程崩溃",
            QProcess.ProcessError.Timedout: "进程超时",
            QProcess.ProcessError.WriteError: "写入错误",
            QProcess.ProcessError.ReadError: "读取错误",
            QProcess.ProcessError.UnknownError: "未知错误",
        }
        msg = error_msgs.get(error, "未知错误")
        self.system_msg.emit(f"进程错误: {msg}", "error")
