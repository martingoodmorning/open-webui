#!/bin/bash
# 启动 Open WebUI 后端（开发模式），在当前终端输出详细日志

set -euo pipefail

PROJECT_ROOT="/home/sai/open-webui"
BACKEND_DIR="$PROJECT_ROOT/backend"
CONDA_ENV="smart-work"

cd "$PROJECT_ROOT"

echo "[启动后端] 使用 conda 环境: ${CONDA_ENV}"
echo "[启动后端] 代码目录: ${BACKEND_DIR}"

# 清理旧的 uvicorn / open_webui 进程，避免端口占用
echo "[启动后端] 清理旧的 uvicorn/open_webui 进程..."
pkill -f "open_webui.main:app" 2>/dev/null || true

echo "[启动后端] 启动后端 (端口: 8080, HF 镜像: https://hf-mirror.com)..."
echo "[启动后端] 日志将输出在当前终端，按 Ctrl+C 停止后端。"
echo "[启动后端] ---------------------------------------------"
echo

# 此时你已经在 smart-work 环境中，因此直接在当前 shell 中运行后端
cd "${BACKEND_DIR}"
export HF_ENDPOINT='https://hf-mirror.com'
export HUGGINGFACE_HUB_BASE_URL='https://hf-mirror.com'
export CORS_ALLOW_ORIGIN='http://localhost:5173;http://localhost:8080'

echo "[后端] 正在启动 uvicorn open_webui.main:app ..."
uvicorn open_webui.main:app \
  --port 8080 \
  --host 0.0.0.0 \
  --forwarded-allow-ips '*' \
  --reload \
  --log-level debug

