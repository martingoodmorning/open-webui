#!/bin/bash
# 清理所有旧的 Office 文档预览缓存
# 用于修复字体问题导致的错误预览

set -e

PROJECT_ROOT="/home/sai/open-webui"
UPLOAD_DIR="${PROJECT_ROOT}/backend/data/uploads"

echo "=========================================="
echo "清理 Office 文档预览缓存"
echo "=========================================="

if [ ! -d "$UPLOAD_DIR" ]; then
    echo "错误: 上传目录不存在: $UPLOAD_DIR"
    exit 1
fi

# 查找所有预览缓存文件
echo "正在查找预览缓存文件..."
PREVIEW_FILES=$(find "$UPLOAD_DIR" -name "*_preview.pdf" -type f 2>/dev/null || true)

if [ -z "$PREVIEW_FILES" ]; then
    echo "未找到预览缓存文件"
    exit 0
fi

# 统计文件数量
FILE_COUNT=$(echo "$PREVIEW_FILES" | wc -l)
echo "找到 $FILE_COUNT 个预览缓存文件"

# 显示前几个文件
echo ""
echo "示例文件："
echo "$PREVIEW_FILES" | head -5
echo ""

# 确认删除
read -p "是否删除所有预览缓存文件？(y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 删除文件
echo "正在删除预览缓存文件..."
echo "$PREVIEW_FILES" | while read -r file; do
    if [ -f "$file" ]; then
        rm -f "$file"
        echo "已删除: $file"
    fi
done

echo ""
echo "=========================================="
echo "清理完成！"
echo "下次预览时会重新生成正确的预览文件"
echo "=========================================="

