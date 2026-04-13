"""
camera_scanner.py - 设备扫描器
============================================

职责:
    - 扫描系统可用摄像头
    - 扫描可用屏幕/显示器
    - 测试 RTSP 网络摄像头连接

架构要点:
    - 纯静态方法，无需实例化
    - 扫描操作可能耗时，建议在子线程调用
"""

from __future__ import annotations

from typing import Optional

import cv2

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


class DeviceScanner:
    """
    设备扫描器
    
    提供摄像头和屏幕的扫描功能。
    所有方法均为静态方法，可直接调用。
    
    Example:
        cameras = DeviceScanner.scan_cameras()
        screens = DeviceScanner.scan_screens()
        is_ok = DeviceScanner.test_rtsp("rtsp://<camera-host>:554/stream")
    """
    
    @staticmethod
    def scan_cameras(max_devices: int = 5) -> list[dict]:
        """
        扫描本地可用摄像头
        
        Args:
            max_devices: 最大扫描设备数量
            
        Returns:
            摄像头列表，每项包含 {id: int, name: str}
            
        Note:
            此方法会逐个尝试打开摄像头，可能耗时较长
        """
        cameras = []
        
        # 临时禁用 OpenCV 日志以抑制警告
        import os
        original_log_level = os.environ.get("OPENCV_LOG_LEVEL", "")
        os.environ["OPENCV_LOG_LEVEL"] = "ERROR"
        
        try:
            for i in range(max_devices):
                try:
                    # 使用通用后端而非 DirectShow，以减少 Windows 上的警告日志
                    cap = cv2.VideoCapture(i, cv2.CAP_ANY)
                    if cap is not None and cap.isOpened():
                        # 尝试读取一帧以验证摄像头确实可用
                        ret, _ = cap.read()
                        if ret:
                            cameras.append({
                                "id": i,
                                "name": f"摄像头 {i}"
                            })
                        cap.release()
                except Exception:
                    # 忽略单个摄像头的扫描错误
                    pass
        finally:
            # 恢复原始日志级别
            if original_log_level:
                os.environ["OPENCV_LOG_LEVEL"] = original_log_level
            elif "OPENCV_LOG_LEVEL" in os.environ:
                del os.environ["OPENCV_LOG_LEVEL"]
        
        return cameras
    
    @staticmethod
    def scan_screens() -> list[dict]:
        """
        扫描可用屏幕/显示器
        
        Returns:
            屏幕列表，每项包含 {id: int, name: str, width: int, height: int}
            
        Note:
            需要安装 mss 库，否则返回空列表
        """
        if not MSS_AVAILABLE:
            return []
        
        screens = []
        try:
            with mss.mss() as sct:
                # monitors[0] 是所有屏幕的合并，从 [1] 开始是单独屏幕
                for i, monitor in enumerate(sct.monitors[1:], start=1):
                    screens.append({
                        "id": i,
                        "name": f"屏幕 {i} ({monitor['width']}x{monitor['height']})",
                        "width": monitor["width"],
                        "height": monitor["height"],
                        "left": monitor["left"],
                        "top": monitor["top"],
                    })
        except Exception:
            pass
        return screens
    
    @staticmethod
    def test_rtsp(url: str, timeout_ms: int = 5000) -> tuple[bool, Optional[str]]:
        """
        测试 RTSP 地址是否可连接
        
        Args:
            url: RTSP 地址 (如 rtsp://<host>:<port>/stream)
            timeout_ms: 超时时间 (毫秒)
            
        Returns:
            (成功与否, 错误信息或None)
        """
        if not url or not url.strip():
            return False, "地址不能为空"
        
        try:
            cap = cv2.VideoCapture(url)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
            
            if not cap.isOpened():
                return False, "无法打开流"
            
            # 尝试读取一帧验证
            ret, _ = cap.read()
            cap.release()
            
            if not ret:
                return False, "无法读取视频帧"
            
            return True, None
            
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_video_info(source: str | int) -> Optional[dict]:
        """
        获取视频源信息
        
        Args:
            source: 视频文件路径、摄像头 ID 或 RTSP 地址
            
        Returns:
            视频信息字典 {width, height, fps} 或 None
        """
        try:
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                return None
            
            info = {
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
            }
            cap.release()
            return info
            
        except Exception:
            return None
