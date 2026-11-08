@echo off
chcp 65001 >nul
cd /d %~dp0

if not exist .venv (
    echo 创建 Python 虚拟环境...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo 安装/检查依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if not exist .env (
    copy .env.example .env
    echo 已创建 .env（默认连接 mongodb://localhost:27017/）。
)

echo 检查 MongoDB 连接并初始化数据库...
python scripts\init_database.py

echo 启动食链通 FoodLink：http://localhost:8501
streamlit run 首页.py --server.port 8501

