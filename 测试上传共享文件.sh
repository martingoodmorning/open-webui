#!/bin/bash
# 测试上传共享文件接口

echo "=========================================="
echo "  测试上传共享文件接口"
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

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://localhost:8080/api/v1/auths/signin" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

if [ "$HTTP_CODE" != "200" ]; then
    echo "❌ 登录失败 (HTTP $HTTP_CODE)"
    echo "响应: $LOGIN_RESPONSE"
    exit 1
fi

# 提取 token
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ 无法从登录响应中提取 token"
    exit 1
fi

echo "✅ 登录成功！"
echo ""

# 创建测试文件
TEST_FILE="/tmp/test_shared_file_$(date +%s).txt"
echo "这是一个测试共享文件
创建时间: $(date)
用于测试共享文件上传功能" > "$TEST_FILE"

echo "=========================================="
echo "  测试 1: 上传文件到全局共享"
echo "=========================================="

response=$(curl -s -w "\n%{http_code}" \
    -X POST "http://localhost:8080/api/v1/files/shared" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$TEST_FILE" \
    -F "group_id=global" \
    -F "process=false")

http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

echo "HTTP 状态码: $http_code"
echo ""

if [ "$http_code" = "200" ]; then
    echo "✅ 上传成功！"
    echo ""
    echo "响应内容："
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
    
    # 提取文件ID
    file_id=$(echo "$body" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('id', ''))" 2>/dev/null)
    if [ -n "$file_id" ]; then
        echo ""
        echo "📄 文件ID: $file_id"
        echo "   可以用这个ID测试下载和删除接口"
    fi
else
    echo "❌ 上传失败"
    echo "响应: $body"
fi

echo ""
echo "=========================================="
echo "  测试 2: 验证文件是否出现在列表中"
echo "=========================================="

sleep 1  # 等待一下，确保数据已保存

response2=$(curl -s -w "\n%{http_code}" \
    -X GET "http://localhost:8080/api/v1/files/shared?page=1&page_size=20" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

http_code2=$(echo "$response2" | tail -n 1)
body2=$(echo "$response2" | sed '$d')

if [ "$http_code2" = "200" ]; then
    total=$(echo "$body2" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('total', 0))" 2>/dev/null)
    echo "✅ 列表接口调用成功"
    echo "   当前共享文件总数: $total"
    
    if [ "$total" -gt 0 ]; then
        echo ""
        echo "   文件列表："
        echo "$body2" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for i, item in enumerate(data.get('items', [])[:5], 1):
    print(f'   {i}. {item.get(\"filename\", \"N/A\")} (ID: {item.get(\"id\", \"N/A\")[:8]}...) [space_type: {item.get(\"space_type\", \"N/A\")}, space_id: {item.get(\"space_id\", \"N/A\")}]')
" 2>/dev/null || echo "   无法解析文件列表"
    fi
else
    echo "❌ 列表接口调用失败"
    echo "响应: $body2"
fi

# 清理测试文件
rm -f "$TEST_FILE"

echo ""
echo "=========================================="
echo "  测试完成"
echo "=========================================="

