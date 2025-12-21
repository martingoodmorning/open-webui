#!/bin/bash
# 自动登录并测试共享文件接口

echo "=========================================="
echo "  自动登录并测试共享文件接口"
echo "=========================================="
echo ""

# 检查后端是否运行
if ! curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
    echo "❌ 后端服务未运行，请先启动：./启动后端.sh"
    exit 1
fi

echo "✅ 后端服务正常运行"
echo ""

# 使用预设账号（如果需要可以修改）
EMAIL="${EMAIL:-admin@qq.com}"
PASSWORD="${PASSWORD:-wangsai}"

echo "📝 使用账号: $EMAIL"
echo ""

echo ""
echo "正在登录..."

# 登录获取 token
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8080/api/v1/auths/signin" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

# 检查登录是否成功
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8080/api/v1/auths/signin" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ 登录失败 (HTTP $HTTP_CODE)"
    echo "响应: $LOGIN_RESPONSE"
    exit 1
fi

# 提取 token（从响应中提取）
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ 无法从登录响应中提取 token"
    echo "响应: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ 登录成功！"
echo "Token: ${TOKEN:0:20}..."
echo ""

echo "=========================================="
echo "  测试 1: 获取共享文件列表"
echo "=========================================="

response=$(curl -s -w "\n%{http_code}" \
    -X GET "http://localhost:8080/api/v1/files/shared?page=1&page_size=20" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

echo "HTTP 状态码: $http_code"
echo ""

if [ "$http_code" = "200" ]; then
    echo "✅ 接口调用成功！"
    echo ""
    echo "响应内容："
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    
    # 提取文件数量
    total=$(echo "$body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total', 0))" 2>/dev/null)
    items_count=$(echo "$body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('items', [])))" 2>/dev/null)
    
    if [ -n "$total" ]; then
        echo ""
        echo "📊 统计信息："
        echo "   总文件数: $total"
        echo "   当前页文件数: $items_count"
    fi
else
    echo "❌ 接口调用失败"
    echo "响应: $body"
fi

echo ""
echo "=========================================="
echo "  测试 2: 测试权限控制（无效分组）"
echo "=========================================="

response2=$(curl -s -w "\n%{http_code}" \
    -X GET "http://localhost:8080/api/v1/files/shared?group_id=invalid_group_12345" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

http_code2=$(echo "$response2" | tail -n 1)
body2=$(echo "$response2" | sed '$d')

echo "HTTP 状态码: $http_code2"

if [ "$http_code2" = "403" ]; then
    echo "✅ 权限控制正常（正确拒绝了无效分组访问）"
    echo "响应: $body2" | python3 -m json.tool 2>/dev/null || echo "$body2"
elif [ "$http_code2" = "200" ]; then
    echo "⚠️  返回了 200，可能需要检查权限逻辑"
    echo "响应: $body2"
else
    echo "响应: $body2"
fi

echo ""
echo "=========================================="
echo "  测试完成"
echo "=========================================="
echo ""
echo "💡 提示：如果接口返回空列表，这是正常的（因为还没有上传共享文件）"
echo "   下一步可以测试上传接口来添加共享文件"

