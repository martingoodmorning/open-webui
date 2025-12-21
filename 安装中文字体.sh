#!/bin/bash
# 安装中文字体支持（开发环境）

set -e

echo "安装中文字体支持..."

# 更新包列表
sudo apt-get update

# 安装中文字体包
sudo apt-get install -y \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fontconfig

# 刷新字体缓存
echo "刷新字体缓存..."
sudo fc-cache -fv

# 验证安装
echo ""
echo "检查中文字体安装情况："
fc-list :lang=zh | head -5 || echo "未找到中文字体"

echo ""
echo "中文字体安装完成！"

