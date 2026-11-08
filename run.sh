#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d ".venv" ]; then
  echo "创建 Python 虚拟环境..."
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate

echo "安装/检查依赖..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "已创建 .env（默认连接 mongodb://localhost:27017/）。"
fi

echo "检查 MongoDB 连接并初始化数据库..."
python scripts/init_database.py || echo "MongoDB 尚未启动，应用仍会启动，但页面会显示连接提示。"

echo "启动食链通 FoodLink：http://localhost:8501"
streamlit run 首页.py --server.port 8501

