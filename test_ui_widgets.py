#!/usr/bin/env python
"""测试 YoloStudio UI 部件的示例脚本（从项目根目录运行）"""

import sys
from pathlib import Path

# 添加 qt_capture scripts 目录到路径
scripts_dir = Path(__file__).parent / ".agent" / "skills" / "qt-testing" / "scripts"
sys.path.insert(0, str(scripts_dir))

from qt_capture import capture_widget, init_qt
from PySide6.QtWidgets import QApplication


def test_data_widget():
    """测试数据处理部件"""
    from ui.data_widget import DataWidget
    
    print("正在测试 DataWidget...")
    widget = DataWidget()
    
    # 捕获每个标签页
    tab_names = ["??", "??", "??", "??"]
    paths = []
    
    for i, tab_name in enumerate(tab_names):
        if i < widget.tab_widget.count():
            widget.tab_widget.setCurrentIndex(i)
            QApplication.processEvents()
            path = capture_widget(widget, f"data_widget_tab_{i}_{tab_name}")
            paths.append(path)
            print(f"  ✓ {tab_name} 标签页: {path}")
    
    widget.close()
    return paths


def test_train_widget():
    """测试训练部件"""
    from ui.train_widget import TrainWidget
    
    print("\n正在测试 TrainWidget...")
    widget = TrainWidget()
    path = capture_widget(widget, "train_widget")
    print(f"  ✓ 训练界面: {path}")
    widget.close()
    return [path]


def test_predict_widget():
    """测试预测部件"""
    from ui.predict_widget import PredictWidget
    
    print("\n正在测试 PredictWidget...")
    widget = PredictWidget()
    path = capture_widget(widget, "predict_widget")
    print(f"  ✓ 预测界面: {path}")
    widget.close()
    return [path]


def main():
    """运行所有测试"""
    print("=" * 60)
    print("YoloStudio UI 部件截图测试")
    print("=" * 60)
    
    app = init_qt()
    
    all_paths = []
    
    try:
        # 测试各个部件
        all_paths.extend(test_data_widget())
        all_paths.extend(test_train_widget())
        all_paths.extend(test_predict_widget())
        
        print("\n" + "=" * 60)
        print(f"测试完成！共生成 {len(all_paths)} 个截图")
        print(f"截图目录: scratch/.qt-screenshots/")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
