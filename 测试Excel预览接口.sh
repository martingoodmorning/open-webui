#!/bin/bash
# 测试共享网盘 Excel/CSV 预览接口

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
EMAIL="${EMAIL:-admin@qq.com}"
PASSWORD="${PASSWORD:-wangsai}"

echo "=========================================="
echo "  测试共享网盘 Excel/CSV 预览接口"
echo "=========================================="
echo ""

# 检查依赖
if ! command -v jq >/dev/null 2>&1; then
    echo "❌ 未找到 jq，请先安装 jq 后再运行本脚本"
    exit 1
fi

# 检查后端是否运行
if ! curl -s "${BASE_URL}/health" > /dev/null 2>&1; then
    echo "❌ 后端服务未运行，请先启动：./启动后端.sh"
    exit 1
fi

echo "✅ 后端服务正常运行 (${BASE_URL})"
echo ""

echo "📝 使用账号: $EMAIL"
echo ""
echo "正在登录..."

# 登录获取 token
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/v1/auths/signin" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/v1/auths/signin" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ 登录失败 (HTTP $HTTP_CODE)"
    echo "响应: $LOGIN_RESPONSE"
    exit 1
fi

# 提取 token
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('token', ''))" 2>/dev/null || true)

if [ -z "${TOKEN:-}" ]; then
    echo "❌ 无法从登录响应中提取 token"
    exit 1
fi

echo "✅ 登录成功！"
echo ""

echo "=========================================="
echo "  第一步：获取共享文件列表，并过滤出 Excel/CSV"
echo "=========================================="
echo ""

LIST_RESPONSE=$(curl -s -X GET "${BASE_URL}/api/v1/files/shared?page=1&page_size=100" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

if [ -z "$LIST_RESPONSE" ]; then
    echo "❌ 获取共享文件列表失败（响应为空）"
    exit 1
fi

TOTAL=$(echo "$LIST_RESPONSE" | jq -r '.total // 0' 2>/dev/null || echo "0")
echo "当前共享文件总数: $TOTAL"
echo ""

# 过滤出 Excel/CSV 文件
EXCEL_ITEMS=$(echo "$LIST_RESPONSE" | jq -c '.items[] | select(.filename | test("\\.(xlsx|xlsb|xls|csv)$"))' 2>/dev/null || true)

if [ -z "$EXCEL_ITEMS" ]; then
    echo "⚠️  未在共享文件列表中找到任何 Excel/CSV 文件"
    echo "   请确认已经上传：在外人员统计.xlsx / 设备数量统计.xlsx 等，然后重试"
    exit 1
fi

echo "找到以下 Excel/CSV 文件："
echo "$EXCEL_ITEMS" | jq -r '"  - " + .filename + " (ID: " + .id + ")"'
echo ""

echo "=========================================="
echo "  第二步：调用 /files/shared/{file_id}/excel/preview 接口"
echo "=========================================="
echo ""

echo "$EXCEL_ITEMS" | while read -r item; do
    [ -z "$item" ] && continue

    FILE_ID=$(echo "$item" | jq -r '.id')
    FILENAME=$(echo "$item" | jq -r '.filename')

    echo "▶️  测试文件: $FILENAME"
    echo "    ID: $FILE_ID"

    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X GET "${BASE_URL}/api/v1/files/shared/${FILE_ID}/excel/preview?max_rows=10" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Accept: application/json")

    HTTP_CODE_PREVIEW=$(echo "$RESPONSE" | tail -n 1)
    BODY_PREVIEW=$(echo "$RESPONSE" | sed '$d')

    echo "    HTTP 状态码: $HTTP_CODE_PREVIEW"

    if [ "$HTTP_CODE_PREVIEW" != "200" ]; then
        echo "    ❌ 预览接口调用失败"
        echo "    响应内容:"
        echo "$BODY_PREVIEW" | jq . 2>/dev/null || echo "    $BODY_PREVIEW"
        echo ""
        continue
    fi

    echo "    ✅ 预览接口调用成功，结构摘要："
    echo "$BODY_PREVIEW" | jq -r '
        .sheets[] |
        "      Sheet: \(.name)\n" +
        "        总行数: \(.total_rows), 是否截断: \(.truncated)\n" +
        "        列: " + ([.columns[].name] | join(", ")) + "\n" +
        "        示例行数: " + ((.sample_rows | length) | tostring)
    ' 2>/dev/null || echo "$BODY_PREVIEW"

    echo ""
done

echo "=========================================="
echo "  测试完成"
echo "=========================================="

