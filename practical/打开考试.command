#!/bin/zsh
EXAM_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
if [ -n "${PYTHON_BIN:-}" ]; then
  : # Respect an explicitly selected Python executable.
elif [ -x "$EXAM_DIR/../.venv/bin/python" ]; then
  PYTHON_BIN="$EXAM_DIR/../.venv/bin/python"
else
  PYTHON_BIN="python3"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python，并确保 python3 在 PATH 中。"
  exit 1
fi
exec "$PYTHON_BIN" "$EXAM_DIR/start_jupyter.py"
