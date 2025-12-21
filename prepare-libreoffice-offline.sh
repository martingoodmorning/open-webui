#!/bin/bash
# 准备 LibreOffice 离线安装包
# 用于 Docker 离线部署

set -e

# 检测 Ubuntu 版本
if [ -f /etc/os-release ]; then
    . /etc/os-release
    VERSION=$VERSION_ID
    CODENAME=$VERSION_CODENAME
else
    echo "无法检测 Ubuntu 版本，使用默认值 22.04"
    VERSION="22.04"
    CODENAME="jammy"
fi

PACKAGE_DIR="libreoffice-offline-ubuntu${VERSION}"
OUTPUT_FILE="libreoffice-offline-ubuntu${VERSION}.tar.gz"

echo "=========================================="
echo "准备 LibreOffice 离线安装包"
echo "Ubuntu 版本: $VERSION ($CODENAME)"
echo "=========================================="

# 检查是否有 root 权限
if [ "$EUID" -ne 0 ]; then 
    echo "提示: 某些操作可能需要 sudo 权限"
fi

# 创建目录
if [ -d "$PACKAGE_DIR" ]; then
    echo "清理旧目录..."
    rm -rf "$PACKAGE_DIR"
fi
mkdir -p "$PACKAGE_DIR"
cd "$PACKAGE_DIR"

# 更新包列表
echo "更新包列表..."
sudo apt-get update

# 下载 LibreOffice 主包和中文字体
echo "下载 LibreOffice 主包和中文字体..."
apt-get download libreoffice libreoffice-writer libreoffice-calc libreoffice-impress \
    fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk fonts-noto-cjk-extra 2>/dev/null || \
    sudo apt-get download libreoffice libreoffice-writer libreoffice-calc libreoffice-impress \
    fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk fonts-noto-cjk-extra

# 获取所有依赖
echo "获取依赖列表..."
DEPS=$(apt-cache depends libreoffice libreoffice-writer libreoffice-calc libreoffice-impress \
    fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk fonts-noto-cjk-extra 2>/dev/null | \
    grep -E "Depends|Recommends" | \
    awk '{print $2}' | \
    sort -u | \
    grep -v "^<" | \
    grep -v "^libreoffice" | \
    grep -v "^fonts-")

# 下载依赖包
echo "下载依赖包（这可能需要几分钟）..."
DOWNLOADED=0
FAILED=0
for dep in $DEPS; do
    if [ ! -z "$dep" ] && [ "$dep" != "<none>" ] && [ "$dep" != "libreoffice" ]; then
        if apt-get download "$dep" 2>/dev/null || sudo apt-get download "$dep" 2>/dev/null; then
            DOWNLOADED=$((DOWNLOADED + 1))
        else
            FAILED=$((FAILED + 1))
            echo "警告: 无法下载 $dep"
        fi
    fi
done

echo "下载完成: 成功 $DOWNLOADED 个，失败 $FAILED 个"

# 返回上级目录并打包
cd ..
echo "打包离线安装包..."
tar -czf "$OUTPUT_FILE" "$PACKAGE_DIR"

# 显示结果
echo ""
echo "=========================================="
echo "完成！"
echo "=========================================="
echo "离线安装包: $OUTPUT_FILE"
echo "文件大小: $(du -h $OUTPUT_FILE | cut -f1)"
echo "包含文件数: $(find $PACKAGE_DIR -name '*.deb' | wc -l)"
echo ""
echo "使用方法:"
echo "1. 将 $OUTPUT_FILE 复制到目标服务器"
echo "2. 解压: tar -xzf $OUTPUT_FILE"
echo "3. 在 Dockerfile 中使用离线安装方式"
echo "=========================================="

