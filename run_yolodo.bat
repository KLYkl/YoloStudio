@echo off
chcp 65001 >nul
echo ====================================
echo   YoloDo 2.0 启动脚本
echo ====================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: 调用 conda 初始化脚本并激活环境
call conda activate yolodo

:: 检查激活是否成功
if errorlevel 1 (
    echo [错误] 无法激活 conda 环境 'yolodo'
    echo 请确保已安装 Anaconda/Miniconda 并创建了 'yolodo' 环境
    pause
    exit /b 1
)

echo [信息] Conda 环境 'yolodo' 已激活
echo [信息] 正在启动 YoloDo 2.0...
echo.

:: 运行主程序
python main.py

:: 如果程序退出，暂停显示输出（方便查看错误信息）
echo.
echo [信息] 程序已退出
pause
