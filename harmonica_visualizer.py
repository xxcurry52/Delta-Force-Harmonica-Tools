# -*- coding: utf-8 -*-
"""三角洲行动 · 口琴可视化曲谱 — 入口文件（模块化版）

原来 3000+ 行全部在单文件里，现在拆分到 src/ 包：
  src/constants.py    共享常量（按键映射、配色、面板布局等）
  src/config.py       配置读写（带防抖）、路径管理、示例曲谱
  src/song_parser.py  曲谱解析（简谱 + Dr-hydra 格式）
  src/winapi.py       Win32 VK 映射、窗口样式常量
  src/utils.py        共享绘制工具（圆角拼接等）
  src/overlay.py      音符叠加层（主窗口：渲染、输入轮询、演奏逻辑）
  src/panel.py        左侧控制面板（曲谱列表、热键按钮）
  src/sub_panel.py    主面板下方小面板（倍速/方块长度）
  src/editor.py       曲谱编辑器（录音、编辑、保存、导入导出）
  src/main.py          入口：组装各模块、启动 Qt 事件循环

运行方式不变：
  python harmonica_visualizer.py          # 启动
  python harmonica_visualizer.py --selftest  # 诊断
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    main()
