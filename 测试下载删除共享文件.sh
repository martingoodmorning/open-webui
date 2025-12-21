#!/bin/bash
# 测试下载和删除共享文件接口

echo "=========================================="
echo "  测试下载和删除共享文件接口"
echo "=========================================="
echo ""

# 检查后端是否运行
if ! curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
    echo "❌ 后端服务未运行，请先启动：./启动后端.sh"
    exit 1
fi

echo "✅ 后端服务正常运行"
echo ""

# 使用预设账号
EMAIL="${EMAIL:-admin@qq.com}"
PASSWORD="${PASSWORD:-wangsai}"

echo "📝 使用账号: $EMAIL"
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

# 先获取一个共享文件ID（从列表中）
echo "正在获取共享文件列表..."
LIST_RESPONSE=$(curl -s -X GET "http://localhost:8080/api/v1/files/shared?page=1&page_size=1" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

FILE_ID=$(echo "$LIST_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('items', [])
    if items:
        print(items[0].get('id', ''))
    else:
        print('')
except:
    print('')
" 2>/dev/null)

if [ -z "$FILE_ID" ]; then
    echo "❌ 没有找到共享文件，请先上传一个文件"
    echo "   运行: ./测试上传共享文件.sh"
    exit 1
fi

echo "✅ 找到共享文件，ID: ${FILE_ID:0:20}..."
echo ""

echo "=========================================="
echo "  测试 1: 下载共享文件"
echo "=========================================="

DOWNLOAD_DIR="/tmp/shared_file_download_$$"
mkdir -p "$DOWNLOAD_DIR"

response=$(curl -s -w "\n%{http_code}" \
    -X GET "http://localhost:8080/api/v1/files/shared/${FILE_ID}/download?attachment=true" \
    -H "Authorization: Bearer $TOKEN" \
    -o "$DOWNLOAD_DIR/downloaded_file")

http_code=$(echo "$response" | tail -n 1)

echo "HTTP 状态码: $http_code"
echo ""

if [ "$http_code" = "200" ]; then
    echo "✅ 下载成功！"
    if [ -f "$DOWNLOAD_DIR/downloaded_file" ]; then
        file_size=$(stat -f%z "$DOWNLOAD_DIR/downloaded_file" 2>/dev/null || stat -c%s "$DOWNLOAD_DIR/downloaded_file" 2>/dev/null || echo "unknown")
        echo "   文件大小: $file_size 字节"
        echo "   保存位置: $DOWNLOAD_DIR/downloaded_file"
        
        # 显示文件内容（如果是文本文件）
        if file "$DOWNLOAD_DIR/downloaded_file" | grep -q "text"; then
            echo ""
            echo "   文件内容预览："
            head -5 "$DOWNLOAD_DIR/downloaded_file" | sed 's/^/   /'
        fi
    fi
else
    echo "❌ 下载失败"
    echo "响应: $(cat "$DOWNLOAD_DIR/downloaded_file" 2>/dev/null || echo 'N/A')"
fi

echo ""
echo "=========================================="
echo "  测试 2: 删除共享文件"
echo "=========================================="

response2=$(curl -s -w "\n%{http_code}" \
    -X DELETE "http://localhost:8080/api/v1/files/shared/${FILE_ID}" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json")

http_code2=$(echo "$response2" | tail -n 1)
body2=$(echo "$response2" | sed '$d')

echo "HTTP 状态码: $http_code2"
echo ""

if [ "$http_code2" = "200" ]; then
    echo "✅ 删除成功！"
    echo "响应: $body2" | python3 -m json.tool 2>/dev/null || echo "$body2"
    
    # 验证文件是否真的被删除
    echo ""
    echo "验证文件是否已从列表中移除..."
    sleep 1
    
    LIST_RESPONSE2=$(curl -s -X GET "http://localhost:8080/api/v1/files/shared?page=1&page_size=20" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json")
    
    STILL_EXISTS=$(echo "$LIST_RESPONSE2" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    items = data.get('items', [])
    for item in items:
        if item.get('id') == '$FILE_ID':
            print('yes')
            break
    else:
        print('no')
except:
    print('unknown')
" 2>/dev/null)
    
    if [ "$STILL_EXISTS" = "no" ]; then
        echo "✅ 文件已从列表中移除"
    else
        echo "⚠️  文件可能仍在列表中（需要检查）"
    fi
else
    echo "❌ 删除失败"
    echo "响应: $body2"
fi

# 清理下载的临时文件
rm -rf "$DOWNLOAD_DIR"

echo ""
echo "=========================================="
echo "  测试完成"
echo "=========================================="

