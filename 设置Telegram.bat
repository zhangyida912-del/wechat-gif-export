@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
title Telegram 设置

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
  where python >nul 2>nul && set PY=python
)
if not defined PY (
  echo [!] 没找到 Python，正在自动安装，装完请再双击一次本工具 ...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  pause
  exit /b
)
%PY% -m pip install -q --disable-pip-version-check -r requirements.txt
%PY% tg_export.py setup
