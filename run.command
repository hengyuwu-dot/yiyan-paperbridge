#!/bin/zsh
set -e
setopt NO_BGNICE
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  RUNTIME_PYTHON="${PAPERBRIDGE_PYTHON:-python3.12}"
  if ! command -v "$RUNTIME_PYTHON" >/dev/null 2>&1; then
    echo "源码版需要 Python 3.12；也可以直接安装内置环境的 Mac 安装包。"
    exit 1
  fi
  "$RUNTIME_PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c "import importlib.util; assert all(importlib.util.find_spec(name) for name in ('pymupdf','fastapi','uvicorn','mlx_lm','babeldoc'))" >/dev/null 2>&1; then
  .venv/bin/python -m pip install --cache-dir .cache/pip -r requirements.txt
fi
if .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/status',timeout=1)" >/dev/null 2>&1; then
  open http://127.0.0.1:8765
  exit 0
fi
echo "译研正在启动。请保留此窗口，关闭窗口会停止软件。"
(.venv/bin/python -c "import time,webbrowser; time.sleep(2); webbrowser.open('http://127.0.0.1:8765')") &
exec .venv/bin/python -m uvicorn paperbridge.app:app --host 127.0.0.1 --port 8765 --no-access-log
