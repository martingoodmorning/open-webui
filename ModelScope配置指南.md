# ModelScope 大模型配置指南

## 配置说明

Open WebUI 支持 OpenAI 兼容的 API，ModelScope 的 API 是兼容的，可以通过环境变量配置。

### 环境变量配置

您提供的配置：
- `LLM_BASE_URL=https://api-inference.modelscope.cn/v1/`
- `LLM_MODEL=Qwen/Qwen2.5-VL-72B-Instruct`
- `LLM_API_KEY=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb`

需要转换为 Open WebUI 的环境变量：
- `OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1`
- `OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb`
- `ENABLE_OPENAI_API=True`（默认已启用）

**注意**：URL 末尾不要有斜杠 `/`

## 配置方法

### 方法一：使用环境变量文件（推荐）

在项目根目录创建 `.env` 文件：

```bash
# ModelScope API 配置
OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1
OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb
ENABLE_OPENAI_API=True
```

### 方法二：在启动命令中设置环境变量

#### Docker 方式
```bash
docker run -d -p 3000:8080 \
  -e OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1 \
  -e OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb \
  -e ENABLE_OPENAI_API=True \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

#### Docker Compose 方式
在 `docker-compose.yaml` 中添加环境变量：

```yaml
services:
  open-webui:
    environment:
      - OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1
      - OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb
      - ENABLE_OPENAI_API=True
```

#### 本地开发方式
```bash
export OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1
export OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb
export ENABLE_OPENAI_API=True
```

### 方法三：通过 Web UI 配置（推荐用于生产环境）

1. 启动 Open WebUI
2. 登录管理员账户
3. 进入 **Settings** → **Connections** → **OpenAI**
4. 配置：
   - **API Base URLs**: `https://api-inference.modelscope.cn/v1`
   - **API Keys**: `ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb`
   - 启用 OpenAI API

## 模型配置

模型名称 `Qwen/Qwen2.5-VL-72B-Instruct` 需要在 Web UI 中选择，或者在 API 调用时指定。

### 在 Web UI 中使用模型

1. 启动 Open WebUI 后，进入聊天界面
2. 点击模型选择器
3. 如果模型未自动发现，可以手动输入模型名称：`Qwen/Qwen2.5-VL-72B-Instruct`
4. 或者在 **Settings** → **Connections** → **OpenAI** 中配置模型列表

## 运行前端（开发模式）

### 前置要求

- Node.js 18.13.0 - 22.x.x
- npm >= 6.0.0

### 步骤

1. **安装依赖**
```bash
npm install
```

2. **配置后端 API 地址**

前端默认连接到 `http://localhost:8080`，如果需要修改，可以：

- 创建 `.env` 文件（前端）：
```bash
VITE_BACKEND_URL=http://localhost:8080
```

- 或者在 `src/lib/constants.ts` 中修改

3. **启动后端**（如果还没有运行）

```bash
# 方式一：使用 pip 安装
pip install open-webui
open-webui serve

# 方式二：使用 Docker
docker run -d -p 8080:8080 \
  -e OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1 \
  -e OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb \
  -v open-webui:/app/backend/data \
  --name open-webui-backend \
  ghcr.io/open-webui/open-webui:main
```

4. **启动前端开发服务器**

```bash
npm run dev
```

前端将在 `http://localhost:5173` 启动（或使用 `npm run dev:5050` 在端口 5050 启动）

### 前端开发命令

```bash
# 开发模式（默认端口 5173）
npm run dev

# 开发模式（指定端口 5050）
npm run dev:5050

# 构建生产版本
npm run build

# 预览生产构建
npm run preview

# 代码检查
npm run check

# 代码格式化
npm run format

# 运行测试
npm run test:frontend
```

## 完整开发环境设置

### 1. 后端开发环境

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .

# 设置环境变量
export OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1
export OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb

# 启动后端
open-webui dev
```

后端运行在：`http://localhost:8080`

### 2. 前端开发环境

```bash
# 在项目根目录
npm install

# 启动前端
npm run dev
```

前端运行在：`http://localhost:5173`

### 3. 访问应用

打开浏览器访问：`http://localhost:5173`

## 验证配置

### 检查 API 连接

1. 登录 Open WebUI
2. 进入 **Settings** → **Connections** → **OpenAI**
3. 查看配置是否正确
4. 尝试获取模型列表，应该能看到 ModelScope 的模型

### 测试模型

1. 在聊天界面选择模型 `Qwen/Qwen2.5-VL-72B-Instruct`
2. 发送一条测试消息
3. 检查是否正常响应

## 常见问题

### 1. 模型列表为空

- 检查 API Base URL 是否正确（不要有末尾斜杠）
- 检查 API Key 是否正确
- 查看后端日志确认 API 调用是否成功

### 2. 前端无法连接后端

- 确认后端是否在运行（`http://localhost:8080`）
- 检查 CORS 配置
- 查看浏览器控制台的错误信息

### 3. API 调用失败

- 检查网络连接
- 验证 API Key 是否有效
- 查看后端日志获取详细错误信息

## 生产环境部署

### Docker Compose 完整配置示例

```yaml
services:
  open-webui:
    build:
      context: .
      dockerfile: Dockerfile
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    volumes:
      - open-webui:/app/backend/data
    ports:
      - "3000:8080"
    environment:
      - OPENAI_API_BASE_URLS=https://api-inference.modelscope.cn/v1
      - OPENAI_API_KEYS=ms-30c52a2c-5f77-4d20-9604-a6d9a6bed1cb
      - ENABLE_OPENAI_API=True
    restart: unless-stopped

volumes:
  open-webui: {}
```

启动：
```bash
docker-compose up -d
```

访问：`http://localhost:3000`

## 安全建议

1. **不要将 API Key 提交到 Git**
   - 使用 `.env` 文件并添加到 `.gitignore`
   - 或使用环境变量想

2. **使用环境变量管理敏感信息**
   - 生产环境使用 Docker secrets 或 Kubernetes secrets

3. **定期轮换 API Key**
   - 定期更新 API Key 以提高安全性

## 参考

- Open WebUI 官方文档：https://docs.openwebui.com/
- ModelScope API 文档：https://modelscope.cn/
- 项目 GitHub：https://github.com/open-webui/open-webui

