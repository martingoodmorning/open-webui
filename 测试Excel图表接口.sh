#!/bin/bash
# 测试共享网盘 Excel 图表接口

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
EMAIL="${EMAIL:-admin@qq.com}"
PASSWORD="${PASSWORD:-wangsai}"

echo "=========================================="
echo "  测试共享网盘 Excel 图表接口"
echo "=========================================="
echo ""

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ 未找到 jq，请先安装 jq 后再运行本脚本"
    exit 1
fi

if ! curl -s "${BASE_URL}/health" > /dev/null 2>&1; then
    echo "❌ 后端服务未运行，请先启动：./启动后端.sh"
    exit 1
fi

echo "✅ 后端服务正常运行 (${BASE_URL})"
echo ""

echo "📝 使用账号: $EMAIL"
echo ""
echo "正在登录..."

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

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('token', ''))" 2>/dev/null || true)

if [ -z "${TOKEN:-}" ]; then
    echo "❌ 无法从登录响应中提取 token"
    exit 1
fi

echo "✅ 登录成功！"
echo ""

echo "=========================================="
echo "  第一步：获取共享文件列表，并过滤出测试 Excel 文件"
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
echo "  第二步：对典型测试文件调用图表接口"
echo "=========================================="
echo ""

echo "$EXCEL_ITEMS" | while read -r item; do
    [ -z "$item" ] && continue

    FILE_ID=$(echo "$item" | jq -r '.id')
    FILENAME=$(echo "$item" | jq -r '.filename')

    echo "▶️  测试文件: $FILENAME"
    echo "    ID: $FILE_ID"

    CONFIG=""

    if [[ "$FILENAME" == *"在外人员统计"* ]]; then
        # 按状态计数，柱状图
        CONFIG='{
  "sheet_name": "在外人员统计",
  "chart_type": "bar",
  "x_field": "状态",
  "y_fields": [],
  "series_field": null,
  "agg": "count",
  "filters": []
}'
    elif [[ "$FILENAME" == *"设备数量统计"* ]]; then
        # 按设备类型统计数量求和
        CONFIG='{
  "sheet_name": "设备数量统计",
  "chart_type": "bar",
  "x_field": "设备类型",
  "y_fields": ["数量"],
  "series_field": null,
  "agg": "sum",
  "filters": []
}'
    else
        echo "    （未为该文件配置专用测试用例，跳过图表测试）"
        echo ""
        continue
    fi

    RESPONSE=$(curl -s -w "\n%{http_code}" \
        -X POST "${BASE_URL}/api/v1/files/shared/${FILE_ID}/excel/chart" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CONFIG")

    HTTP_CODE_CHART=$(echo "$RESPONSE" | tail -n 1)
    BODY_CHART=$(echo "$RESPONSE" | sed '$d')

    echo "    HTTP 状态码: $HTTP_CODE_CHART"

    if [ "$HTTP_CODE_CHART" != "200" ]; then
        echo "    ❌ 图表接口调用失败"
        echo "    响应内容:"
        echo "$BODY_CHART" | jq . 2>/dev/null || echo "    $BODY_CHART"
        echo ""
        continue
    fi

    echo "    ✅ 图表接口调用成功，返回结构摘要："
    echo "$BODY_CHART" | jq -r '
        "      chart_type: \(.chart_type)\n" +
        "      x_field: \(.x_field)\n" +
        "      y_fields: " + (.y_fields | join(", ")) + "\n" +
        "      series 数量: " + ((.series | length) | tostring)
    ' 2>/dev/null || echo "$BODY_CHART"

    echo ""
done

echo "=========================================="
echo "  测试完成"
echo "=========================================="

