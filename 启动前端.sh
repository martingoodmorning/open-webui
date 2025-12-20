#!/bin/bash
# 启动 Open WebUI 前端（开发模式）

set -e

PROJECT_ROOT="/home/sai/open-webui"

cd "$PROJECT_ROOT"

echo "[启动前端] 加载 nvm..."
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

echo "[启动前端] 切换到 Node.js 22..."
nvm use 22 >/dev/null

echo "[启动前端] 启动前端 (npm run dev, 端口: 5173)..."
echo "[启动前端] 日志将输出在当前终端，按 Ctrl+C 停止前端。"
echo

NODE_ENV=development npm run dev


